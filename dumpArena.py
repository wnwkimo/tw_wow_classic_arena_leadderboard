"""台服經典版競技場天梯資料抓取工具。

從 Blizzard API 抓取排行榜，補上每個角色的職業 / 種族，
輸出成網頁讀取的 data/season_{賽季}_{賽制}_tw_arena.json，並更新 data/manifest.json。

用法範例：
    python dumpArena.py                      # 目前賽季，2v2/3v3/5v5
    python dumpArena.py -s 13 -b 2v2,3v3     # 指定賽季與賽制
    python dumpArena.py -s 10-13             # 賽季範圍
    python dumpArena.py --all-seasons        # API 上所有賽季
    python dumpArena.py --list-seasons       # 只列出可用賽季
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

log = logging.getLogger("dumpArena")

DATA_DIR = Path(__file__).resolve().parent / "data"
DEFAULT_BRACKETS = ["2v2", "3v3", "5v5"]
ALL_BRACKETS = ["2v2", "3v3", "5v5", "rbg"]
RBG_FIRST_SEASON = 9
# 新資料筆數低於舊檔的這個比例時拒絕覆寫（避免賽季結束 API 清空時蓋掉歷史資料）
MIN_KEEP_RATIO = 0.5

RACE_MAP = {
    1: "人類", 2: "獸人", 3: "矮人", 4: "夜精靈", 5: "不死族",
    6: "牛頭人", 7: "地精", 8: "食人妖", 9: "哥布林", 10: "血精靈",
    11: "德萊尼", 24: "熊貓人", 25: "熊貓人", 26: "熊貓人",
}

CLASS_MAP = {
    1: "戰士", 2: "聖騎士", 3: "獵人", 4: "盜賊", 5: "牧師", 6: "死亡騎士",
    7: "薩滿", 8: "法師", 9: "術士", 10: "武僧", 11: "德魯伊",
    12: "惡魔獵人", 13: "喚法師",
}


# ====== 憑證 ======

def read_windows_credential(target_name: str) -> Optional[str]:
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.c_void_p),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        credential_ptr = ctypes.POINTER(CREDENTIAL)()
        if not ctypes.windll.advapi32.CredReadW(target_name, 1, 0, ctypes.byref(credential_ptr)):
            return None
        try:
            credential = credential_ptr.contents
            if not credential.CredentialBlob or not credential.CredentialBlobSize:
                return None
            blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            for encoding in ("utf-16-le", "utf-8"):
                try:
                    value = blob.decode(encoding).rstrip("\x00")
                    if value:
                        return value
                except UnicodeDecodeError:
                    continue
            return None
        finally:
            ctypes.windll.advapi32.CredFree(credential_ptr)
    except Exception:
        return None


def read_macos_keychain(service_name: str) -> Optional[str]:
    if sys.platform != "darwin":
        return None
    account = os.getenv("USER") or getpass.getuser()
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-a", account, "-s", service_name, "-w"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def read_secret(name: str, *env_fallbacks: str) -> Optional[str]:
    """依序從 Windows Credential Manager、macOS Keychain、環境變數讀取。"""
    value = read_windows_credential(name) or read_macos_keychain(name)
    if value:
        return value
    for env_name in (name, *env_fallbacks):
        if os.getenv(env_name):
            return os.getenv(env_name)
    return None


def load_credentials() -> tuple[str, str]:
    client_id = read_secret("BLIZZARD_CLIENT_ID", "BNET_CLIENT_ID")
    client_secret = read_secret("BLIZZARD_CLIENT_SECRET", "BNET_CLIENT_SECRET")
    if client_id and client_secret:
        return client_id, client_secret

    if not sys.stdin.isatty():
        raise SystemExit(
            "找不到 BLIZZARD_CLIENT_ID / BLIZZARD_CLIENT_SECRET，"
            "請存到 Keychain / Credential Manager 或設定環境變數。"
        )
    log.warning("找不到儲存的 Blizzard API 憑證，請手動輸入（建議存到 Keychain / Credential Manager）")
    client_id = client_id or input("Blizzard Client ID: ").strip()
    client_secret = client_secret or getpass.getpass("Blizzard Client Secret: ").strip()
    if not client_id or not client_secret:
        raise SystemExit("Client ID / Secret 不可為空")
    return client_id, client_secret


# ====== API ======

class BlizzardAPIError(Exception):
    pass


class BlizzardClient:
    """Blizzard API 客戶端：自動重試 429/5xx，每個執行緒各自一個 Session。"""

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.oauth_url = os.getenv("BLIZZARD_OAUTH_URL", "https://oauth.battle.net/token")
        self.api_host = os.getenv("WOW_API_HOST", "tw.api.blizzard.com")
        self.data_namespace = os.getenv("WOW_DATA_NAMESPACE", "dynamic-classic-tw")
        self.profile_namespace = os.getenv("WOW_PROFILE_NAMESPACE", "profile-classic-tw")
        self.locale = os.getenv("WOW_LOCALE", "en_TW")
        self.access_token: Optional[str] = None
        self._local = threading.local()

    @property
    def session(self) -> requests.Session:
        if not hasattr(self._local, "session"):
            retry = Retry(
                total=5,
                backoff_factor=1,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST"],
                respect_retry_after_header=True,
            )
            session = requests.Session()
            session.mount("https://", HTTPAdapter(max_retries=retry))
            self._local.session = session
        return self._local.session

    def authenticate(self) -> None:
        response = self.session.post(
            self.oauth_url,
            data={"grant_type": "client_credentials"},
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        if response.status_code != 200:
            raise BlizzardAPIError(f"取得 token 失敗 HTTP {response.status_code}: {response.text}")
        self.access_token = response.json()["access_token"]

    def _get(self, path: str, namespace: str, timeout: int = 30) -> requests.Response:
        return self.session.get(
            f"https://{self.api_host}{path}",
            headers={"Authorization": f"Bearer {self.access_token}"},
            params={"namespace": namespace, "locale": self.locale},
            timeout=timeout,
        )

    def _get_json(self, path: str, namespace: str) -> dict:
        response = self._get(path, namespace)
        if response.status_code != 200:
            raise BlizzardAPIError(f"GET {path} 失敗 HTTP {response.status_code}: {response.text[:200]}")
        return response.json()

    def season_index(self) -> dict:
        return self._get_json("/data/wow/pvp-season/index", self.data_namespace)

    def leaderboard(self, season: int, bracket: str) -> dict:
        if season >= RBG_FIRST_SEASON:
            path = f"/data/wow/pvp-season/{season}/pvp-leaderboard/{bracket}"
        else:
            path = f"/data/wow/pvp-region/0/pvp-season/{season}/pvp-leaderboard/{bracket}"
        return self._get_json(path, self.data_namespace)

    def character_profile(self, realm_slug: str, name: str) -> Optional[dict]:
        """回傳角色資料；角色不存在（改名、轉服、刪除）時回傳 None。"""
        path = f"/profile/wow/character/{realm_slug}/{quote(name.lower(), safe='')}"
        response = self._get(path, self.profile_namespace, timeout=15)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise BlizzardAPIError(f"HTTP {response.status_code}")
        return response.json()


# ====== 資料處理 ======

def character_key(character: dict) -> str:
    # 角色 ID 偶爾會被重新分配給別的角色，所以連名字一起比對
    realm = character.get("realm", {}).get("slug", "")
    return f"{realm}:{character.get('id', '')}:{character.get('name', '').lower()}"


def has_details(character: dict) -> bool:
    return bool(character.get("playable_class", {}).get("id") and character.get("playable_race", {}).get("id"))


def describe(character: dict) -> str:
    race_id = character.get("playable_race", {}).get("id")
    class_id = character.get("playable_class", {}).get("id")
    return f"{character.get('name')} ({RACE_MAP.get(race_id, '?')} {CLASS_MAP.get(class_id, '?')})"


def output_path(season: int, bracket: str) -> Path:
    return DATA_DIR / f"season_{season}_{bracket}_tw_arena.json"


def load_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        log.warning("  %s JSON 格式錯誤，視為沒有舊資料", path.name)
        return None


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


class CharacterIndex:
    """從 data/ 底下所有檔案收集已知的角色職業 / 種族。

    Blizzard 角色 API 常對部分角色回傳 404（即使是當季活躍玩家），
    所以只要任何一個檔案曾經查到過，就跨賽季 / 賽制沿用。
    """

    def __init__(self) -> None:
        self._known: dict[str, dict] = {}

    @classmethod
    def from_data_dir(cls) -> "CharacterIndex":
        index = cls()
        paths = sorted(DATA_DIR.glob("season_*_*_tw_arena.json"), key=lambda p: int(p.stem.split("_")[1]))
        for path in paths:  # 由舊到新，較新的資料會覆蓋（例如種族變更）
            for entry in (load_json(path) or {}).get("entries", []):
                if "character" in entry:
                    index.add(entry["character"])
        return index

    def add(self, character: dict) -> None:
        if has_details(character):
            self._known[character_key(character)] = {
                "playable_class": character["playable_class"],
                "playable_race": character["playable_race"],
            }

    def fill(self, character: dict) -> bool:
        known = self._known.get(character_key(character))
        if known:
            character.update(known)
        return known is not None

    def __len__(self) -> int:
        return len(self._known)


@dataclass
class BracketResult:
    season: int
    bracket: str
    entries: int = 0
    reused: int = 0
    fetched: int = 0
    failed: list[str] = field(default_factory=list)
    written: bool = False
    skipped_reason: Optional[str] = None


def enrich_entries(
    client: BlizzardClient, characters: list[dict], index: CharacterIndex, workers: int, result: BracketResult
) -> None:
    """平行查詢角色資料，把職業 / 種族寫回 character dict。"""

    def fetch(character: dict) -> tuple[dict, Optional[dict], Optional[str]]:
        try:
            profile = client.character_profile(character["realm"]["slug"], character["name"])
            return character, profile, None if profile else "404"
        except Exception as e:  # 單一角色失敗不影響整體
            return character, None, str(e)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for character, profile, error in pool.map(fetch, characters):
            if profile and "character_class" in profile and "race" in profile:
                character["playable_class"] = profile["character_class"]
                character["playable_race"] = profile["race"]
                index.add(character)
                result.fetched += 1
                log.debug("  API 取得 %s", describe(character))
            else:
                result.failed.append(f"{character.get('name')}-{character.get('realm', {}).get('slug')}({error})")


def process_bracket(
    client: BlizzardClient,
    index: CharacterIndex,
    season: int,
    bracket: str,
    current_season: Optional[int],
    args: argparse.Namespace,
) -> BracketResult:
    result = BracketResult(season, bracket)
    path = output_path(season, bracket)
    old_data = load_json(path)
    old_entries = (old_data or {}).get("entries", [])

    # 已結束的賽季，API 會隨時間移除刪除 / 轉服的角色，重抓會讓歷史資料變少。
    # 所以已有存檔時只補職業 / 種族，不重新下載排行榜。
    archived = old_data is not None and current_season is not None and season < current_season and not args.force
    if archived:
        log.info("▶ Season %s %s（已結束，只補角色資料）", season, bracket)
        data = old_data
    else:
        log.info("▶ Season %s %s", season, bracket)
        data = client.leaderboard(season, bracket)
    entries = data.get("entries", [])
    result.entries = len(entries)

    # 防呆：新資料明顯比舊檔少時不覆寫
    if not archived and old_entries and not args.force and len(entries) < len(old_entries) * MIN_KEEP_RATIO:
        result.skipped_reason = f"新資料 {len(entries)} 筆遠少於舊檔 {len(old_entries)} 筆（加 --force 強制覆寫）"
        log.warning("  略過：%s", result.skipped_reason)
        return result

    to_fetch = []
    for entry in entries:
        character = entry.get("character")
        if not character or (archived and has_details(character)):
            continue
        if index.fill(character):
            result.reused += 1
        elif not args.no_enrich:
            to_fetch.append(character)

    if to_fetch:
        log.info("  %d 筆，補入已知 %d 個角色，查詢 %d 個角色…", len(entries), result.reused, len(to_fetch))
        enrich_entries(client, to_fetch, index, args.workers, result)

    if result.failed:
        log.warning("  %d 個角色查不到職業 / 種族：%s", len(result.failed), "、".join(result.failed))

    if archived and not (result.reused or result.fetched):
        log.info("  沒有可補的角色資料，不需更新")
    elif args.dry_run:
        log.info("  [dry-run] 不寫入 %s", path.name)
    else:
        write_json(path, data)
        result.written = True
    log.info(
        "  ✔ %d 筆｜補入已知 %d｜API %d｜失敗 %d",
        result.entries, result.reused, result.fetched, len(result.failed),
    )
    return result


def update_manifest(current_season: Optional[int]) -> None:
    """掃描 data/ 產生 manifest.json，讓網頁可以知道有哪些賽季 / 賽制。"""
    seasons: dict[str, dict] = {}
    for path in sorted(DATA_DIR.glob("season_*_*_tw_arena.json")):
        _, season, bracket, *_ = path.stem.split("_")
        data = load_json(path) or {}
        seasons.setdefault(season, {})[bracket] = {
            "entries": len(data.get("entries", [])),
        }
    manifest = {
        "current_season": current_season,
        "seasons": dict(sorted(seasons.items(), key=lambda kv: int(kv[0]))),
    }
    write_json(DATA_DIR / "manifest.json", manifest)


# ====== CLI ======

def parse_seasons(value: str) -> list[int]:
    seasons: set[int] = set()
    for part in value.split(","):
        part = part.strip()
        if "-" in part:
            start, end = (int(x) for x in part.split("-", 1))
            seasons.update(range(start, end + 1))
        elif part:
            seasons.add(int(part))
    return sorted(seasons)


def parse_brackets(value: str) -> list[str]:
    if value == "all":
        return ALL_BRACKETS
    brackets = [b.strip() for b in value.split(",") if b.strip()]
    invalid = [b for b in brackets if b not in ALL_BRACKETS]
    if invalid:
        raise argparse.ArgumentTypeError(f"不支援的賽制: {', '.join(invalid)}（可用: {', '.join(ALL_BRACKETS)}, all）")
    return brackets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="抓取台服經典版競技場天梯資料",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("用法範例：", 1)[1],
    )
    seasons = parser.add_mutually_exclusive_group()
    seasons.add_argument("-s", "--season", type=parse_seasons, help="賽季，如 13、10-13、11,13（預設：目前賽季）")
    seasons.add_argument("--all-seasons", action="store_true", help="抓 API 上所有賽季")
    seasons.add_argument("--list-seasons", action="store_true", help="列出可用賽季後結束")
    parser.add_argument("-b", "--bracket", type=parse_brackets, default=DEFAULT_BRACKETS,
                        help="賽制，逗號分隔或 all（預設：2v2,3v3,5v5）")
    parser.add_argument("--no-enrich", action="store_true", help="不查詢新角色的職業 / 種族")
    parser.add_argument("--refresh-characters", action="store_true", help="不沿用已知資料，重新查詢所有角色")
    parser.add_argument("--force", action="store_true", help="重新下載已結束的賽季，且資料大幅減少時仍然覆寫")
    parser.add_argument("--dry-run", action="store_true", help="只抓資料不寫檔")
    parser.add_argument("--workers", type=int, default=8, help="查詢角色的平行數（預設 8）")
    parser.add_argument("-v", "--verbose", action="store_true", help="顯示每個角色的詳細紀錄")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    client = BlizzardClient(*load_credentials())
    try:
        client.authenticate()
        index = client.season_index()
    except (BlizzardAPIError, requests.RequestException) as e:
        log.error("✖ %s", e)
        return 1

    available = sorted(int(s["id"]) for s in index.get("seasons", []) if s.get("id") is not None)
    current = index.get("current_season", {}).get("id") or (max(available) if available else None)

    if args.list_seasons:
        print(f"可用賽季: {', '.join(map(str, available))}（目前賽季: {current}）")
        return 0

    if args.all_seasons:
        seasons = available
    elif args.season:
        seasons = args.season
        unknown = [s for s in seasons if available and s not in available]
        if unknown:
            log.error("✖ API 沒有這些賽季: %s（可用: %s）", unknown, available)
            return 1
    elif current:
        seasons = [current]
    else:
        log.error("✖ 無法取得目前賽季，請用 -s 指定")
        return 1

    index = CharacterIndex() if args.refresh_characters else CharacterIndex.from_data_dir()
    log.info("已知角色資料 %d 筆", len(index))

    start = time.time()
    results: list[BracketResult] = []
    errors: list[str] = []
    for season in seasons:
        for bracket in args.bracket:
            if bracket == "rbg" and season < RBG_FIRST_SEASON:
                continue
            try:
                results.append(process_bracket(client, index, season, bracket, current, args))
            except (BlizzardAPIError, requests.RequestException) as e:
                errors.append(f"Season {season} {bracket}: {e}")
                log.error("  ✖ %s", e)

    if not args.dry_run and any(r.written for r in results):
        update_manifest(current)

    written = sum(r.written for r in results)
    failed_chars = sum(len(r.failed) for r in results)
    log.info("\n完成：寫入 %d 個檔案，略過 %d，錯誤 %d，角色查詢失敗 %d（%.1f 秒）",
             written, sum(bool(r.skipped_reason) for r in results), len(errors), failed_chars, time.time() - start)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
