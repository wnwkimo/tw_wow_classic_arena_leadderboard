"""台服經典版競技場天梯資料抓取工具。

從 Blizzard API 抓取排行榜，補上每個角色的職業 / 種族，
輸出成網頁讀取的 data/season_{賽季}_{賽制}_tw_arena.json，並更新 data/manifest.json。

用法範例：
    python dumpArena.py                      # 互動選單（↑↓ 選擇、Enter 確認）
    python dumpArena.py -s 14                # 指定賽季，不進選單
    python dumpArena.py -s 13 -b 2v2,3v3     # 指定賽季與賽制
    python dumpArena.py -s 10-13             # 賽季範圍
    python dumpArena.py --all-seasons        # API 上所有賽季
    python dumpArena.py --list-seasons       # 只列出可用賽季
"""

from __future__ import annotations

import argparse
import copy
import getpass
import json
import logging
import os
import subprocess
import sys
import threading
import time
import unicodedata
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


def entry_characters(entry: dict) -> list[dict]:
    """S5 以後每筆是單一角色；S1–S4 是隊伍，角色在 team.members 裡。"""
    if "character" in entry:
        return [entry["character"]]
    return [m["character"] for m in entry.get("team", {}).get("members", []) if "character" in m]


def entry_key(entry: dict) -> str:
    if "character" in entry:
        return character_key(entry["character"])
    team = entry.get("team", {})
    return f"team:{team.get('realm', {}).get('slug', '')}:{team.get('name', '')}"


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
                for character in entry_characters(entry):
                    index.add(character)
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
    # 試跑時暫存結果，之後可直接寫入不必重抓
    path: Optional[Path] = field(default=None, repr=False)
    data: Optional[dict] = field(default=None, repr=False)

    @property
    def pending(self) -> bool:
        return self.data is not None and not self.written


FACTION_MAP = {"HORDE": "部落", "ALLIANCE": "聯盟"}


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(width - display_width(text), 0)


def diff_summary(old_entries: list[dict], new_entries: list[dict]) -> str:
    """跟存檔比較：新上榜、掉出、分數變動、補上職業。"""
    old = {entry_key(e): e for e in old_entries}
    new = {entry_key(e): e for e in new_entries}
    common = old.keys() & new.keys()
    rating_changed = sum(1 for k in common if old[k].get("rating") != new[k].get("rating"))
    missing = lambda e: sum(not has_details(c) for c in entry_characters(e))
    filled = sum(max(missing(old[k]) - missing(new[k]), 0) for k in common)
    return (
        f"筆數 {len(old_entries)} → {len(new_entries)}｜新上榜 {len(new.keys() - old.keys())}｜"
        f"掉出 {len(old.keys() - new.keys())}｜分數變動 {rating_changed}｜補上職業 {filled}"
    )


def print_preview(entries: list[dict], limit: int) -> None:
    rows = sorted(entries, key=lambda e: e.get("rank") or 0)[:limit]
    is_team = bool(rows) and "team" in rows[0]
    who = "隊伍" if is_team else "角色"
    detail = "成員" if is_team else f"{pad('職業', 9)}種族"
    log.info("    %s%s%s%s%s%s", pad("排名", 5), pad(who, 20), pad("陣營", 5), pad("分數", 6), pad("勝-敗", 10), detail)
    for e in rows:
        stats = e.get("season_match_statistics", {})
        if is_team:
            name = e.get("team", {}).get("name", "?")
            detail = "、".join(
                f"{c.get('name')}({CLASS_MAP.get(c.get('playable_class', {}).get('id'), '-')})"
                for c in entry_characters(e)
            )
        else:
            character = e.get("character", {})
            name = character.get("name", "?")
            detail = (
                pad(CLASS_MAP.get(character.get("playable_class", {}).get("id"), "-"), 9)
                + RACE_MAP.get(character.get("playable_race", {}).get("id"), "-")
            )
        log.info(
            "    %s%s%s%s%s%s",
            pad(str(e.get("rank", "?")), 5),
            pad(name, 20),
            pad(FACTION_MAP.get(e.get("faction", {}).get("type"), "-"), 5),
            pad(str(e.get("rating", "?")), 6),
            pad(f"{stats.get('won', 0)}-{stats.get('lost', 0)}", 10),
            detail,
        )
    if len(entries) > limit:
        log.info("    …共 %d 筆", len(entries))


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
            elif has_details(character) or index.fill(character):
                result.reused += 1  # 查詢失敗，保留已知資料
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
    path = output_path(season, bracket)
    result = BracketResult(season, bracket, path=path)
    old_data = load_json(path)
    old_entries = copy.deepcopy((old_data or {}).get("entries", []))

    # 已結束的賽季，API 會隨時間移除刪除 / 轉服的角色，重抓會讓歷史資料變少。
    # 所以已有存檔時只補職業 / 種族，不重新下載排行榜。
    finished = current_season is not None and season < current_season
    archived = old_data is not None and not args.force and (finished or args.fill_only)
    if archived:
        log.info("▶ Season %s %s（%s，只補角色資料）", season, bracket, "已結束" if finished else "使用存檔")
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
    for character in (c for entry in entries for c in entry_characters(entry)):
        # 已有職業 / 種族的不動（S1–S4 的 API 本身就有，且要保留當季的原始資料）
        if has_details(character) and not args.refresh_characters:
            continue
        if args.refresh_characters and not args.no_enrich:
            to_fetch.append(character)
        elif index.fill(character):
            result.reused += 1
        elif not args.no_enrich:
            to_fetch.append(character)

    if to_fetch:
        log.info("  %d 筆，補入已知 %d 個角色，查詢 %d 個角色…", len(entries), result.reused, len(to_fetch))
        result.reused = 0 if args.refresh_characters else result.reused
        enrich_entries(client, to_fetch, index, args.workers, result)

    if result.failed:
        log.warning("  %d 個角色查不到職業 / 種族：%s", len(result.failed), "、".join(result.failed))

    log.info("  與存檔比較：%s", diff_summary(old_entries, entries) if old_data else "尚無存檔，將建立新檔")
    if args.dry_run:
        print_preview(entries, args.preview)

    if archived and entries == old_entries:
        log.info("  資料沒有變化，不需更新")
    else:
        result.data = data
        if args.dry_run:
            log.info("  [試跑] 尚未寫入 %s", path.name)
        else:
            write_json(path, data)
            result.written = True
    log.info(
        "  ✔ %d 筆｜補入已知 %d｜API %d｜失敗 %d",
        result.entries, result.reused, result.fetched, len(result.failed),
    )
    return result


def write_pending(results: list[BracketResult], current_season: Optional[int]) -> None:
    for r in results:
        if r.pending:
            write_json(r.path, r.data)
            r.written = True
            log.info("  已寫入 %s", r.path.name)
    update_manifest(current_season)


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
    parser.add_argument("--refresh-characters", action="store_true", help="所有角色都重新查詢 API（查不到時保留已知資料）")
    parser.add_argument("--force", action="store_true", help="重新下載已結束的賽季，且資料大幅減少時仍然覆寫")
    parser.add_argument("--fill-only", action="store_true", help="不重新下載排行榜，只補現有存檔的角色資料")
    parser.add_argument("--dry-run", action="store_true", help="只抓資料不寫檔")
    parser.add_argument("--preview", type=int, default=10, help="試跑時預覽前幾名（預設 10）")
    parser.add_argument("--workers", type=int, default=8, help="查詢角色的平行數（預設 8）")
    parser.add_argument("-v", "--verbose", action="store_true", help="顯示每個角色的詳細紀錄")
    return parser


def has_any_file(season: int) -> list[str]:
    return [b for b in ALL_BRACKETS if output_path(season, b).exists()]


def run_job(
    client: BlizzardClient, seasons: list[int], current: Optional[int], args: argparse.Namespace
) -> list[BracketResult]:
    index = CharacterIndex.from_data_dir()
    log.info("已知角色資料 %d 筆", len(index))

    start = time.time()
    results: list[BracketResult] = []
    errors: list[str] = []
    for season in seasons:
        for bracket in args.bracket:
            if bracket == "rbg" and season < RBG_FIRST_SEASON:
                continue
            if args.fill_only and not output_path(season, bracket).exists():
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
    pending = sum(r.pending for r in results)
    log.info("\n完成：寫入 %d 個檔案%s，略過 %d，錯誤 %d，角色查詢失敗 %d（%.1f 秒）",
             written, f"（試跑，{pending} 個待寫入）" if args.dry_run else "",
             sum(bool(r.skipped_reason) for r in results), len(errors), failed_chars, time.time() - start)
    return results if not errors else results + [BracketResult(0, "error", skipped_reason="error")]


# ====== 互動選單用的操作 ======

def count_missing(entries: list[dict]) -> int:
    return sum(not has_details(c) for e in entries for c in entry_characters(e))


def fetch_bracket(
    client: BlizzardClient, index: CharacterIndex, season: int, bracket: str, workers: int, limit: Optional[int] = None
) -> tuple[dict, BracketResult]:
    """從 API 下載排行榜並補上職業 / 種族（先用已知資料，查不到再呼叫 API）。"""
    result = BracketResult(season, bracket)
    data = client.leaderboard(season, bracket)
    if limit:
        data["entries"] = sorted(data.get("entries", []), key=lambda e: e.get("rank") or 0)[:limit]
    entries = data.get("entries", [])
    result.entries = len(entries)

    to_fetch = []
    for character in (c for e in entries for c in entry_characters(e)):
        if has_details(character):
            continue  # API 已提供（S1–S4），保留原始資料
        if index.fill(character):
            result.reused += 1
        else:
            to_fetch.append(character)
    if to_fetch:
        enrich_entries(client, to_fetch, index, workers, result)
    return data, result


def show_cache(season: int, bracket: str, limit: int) -> None:
    path = output_path(season, bracket)
    data = load_json(path)
    if data is None:
        log.info("▶ Season %s %s：尚無存檔", season, bracket)
        return
    entries = data.get("entries", [])
    log.info("▶ Season %s %s：%s｜%d 筆｜缺職業 %d", season, bracket, path.name, len(entries), count_missing(entries))
    if entries:
        print_preview(entries, limit)


# ====== 互動選單 ======

def interactive(client: BlizzardClient, available: list[int], current: Optional[int]) -> int:
    import questionary
    from questionary import Choice

    def season_choices(default: list[int]) -> list[Choice]:
        choices = []
        for season in sorted(available, reverse=True):
            saved = has_any_file(season)
            if season == current:
                note = "目前賽季"
            elif saved:
                note = f"已結束，存檔 {'/'.join(saved)}"
            else:
                note = "已結束，尚無存檔"
            choices.append(Choice(f"S{season:<3} {note}", value=season, checked=season in default))
        return choices

    def ask_seasons() -> Optional[list[int]]:
        return questionary.checkbox(
            "選擇賽季（空白鍵勾選，Enter 確認）",
            choices=season_choices([current] if current else []),
            validate=lambda picked: bool(picked) or "至少選一個賽季",
        ).ask()

    def ask_brackets() -> Optional[list[str]]:
        return questionary.checkbox(
            "選擇賽制（可複選）",
            choices=[Choice(b, value=b, checked=b in DEFAULT_BRACKETS) for b in ALL_BRACKETS],
            validate=lambda picked: bool(picked) or "至少選一個賽制",
        ).ask()

    def targets(seasons: list[int], brackets: list[str]) -> list[tuple[int, str]]:
        return [(s, b) for s in seasons for b in brackets if not (b == "rbg" and s < RBG_FIRST_SEASON)]

    def update_from_server(pairs: list[tuple[int, str]]) -> None:
        index = CharacterIndex.from_data_dir()
        written = False
        for season, bracket in pairs:
            log.info("下載 Season %s %s…", season, bracket)
            try:
                data, result = fetch_bracket(client, index, season, bracket, workers=8)
            except (BlizzardAPIError, requests.RequestException) as e:
                log.error("  ✖ %s", e)
                continue
            path = output_path(season, bracket)
            write_json(path, data)
            written = True
            log.info(
                "  ✔ 已寫入 %s｜%d 筆｜補入已知 %d｜API %d｜失敗 %d",
                path.name, result.entries, result.reused, result.fetched, len(result.failed),
            )
        if written:
            update_manifest(current)

    def season_status() -> None:
        for season in sorted(available, reverse=True):
            note = "目前賽季" if season == current else "已結束"
            parts = []
            for bracket in ALL_BRACKETS:
                if bracket == "rbg" and season < RBG_FIRST_SEASON:
                    continue
                data = load_json(output_path(season, bracket))
                if data is None:
                    parts.append(f"{bracket} -")
                else:
                    entries = data.get("entries", [])
                    missing = count_missing(entries)
                    parts.append(f"{bracket} {len(entries)}" + (f"(缺{missing})" if missing else ""))
            print(f"  S{season:<3} {note}｜{'｜'.join(parts)}")

    while True:
        print()
        action = questionary.select(
            "要做什麼？",
            choices=[
                Choice(f"1. Check current season   查看目前賽季 (S{current}) 存檔", value="check"),
                Choice("2. Update season/bracket  選擇賽季 / 賽制，重新下載並直接覆蓋存檔", value="update"),
                Choice("3. List season status     列出各賽季存檔狀態", value="status"),
                Choice("離開", value="exit"),
            ],
        ).ask()
        if action in (None, "exit"):
            return 0

        if action == "check":
            for bracket in ALL_BRACKETS:
                if bracket == "rbg" and current < RBG_FIRST_SEASON:
                    continue
                show_cache(current, bracket, 10)
        elif action == "status":
            season_status()
        elif action == "update":
            seasons = ask_seasons()
            if not seasons:
                continue
            brackets = ask_brackets()
            if not brackets:
                continue
            pairs = targets(seasons, brackets)
            if not pairs:
                log.info("S%s 之前沒有 rbg", RBG_FIRST_SEASON)
                continue
            update_from_server(pairs)


# ====== 進入點 ======

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

    # 沒有任何參數且在終端機執行時，進入互動選單
    if len(sys.argv) == 1 and sys.stdin.isatty():
        try:
            return interactive(client, available, current)
        except KeyboardInterrupt:
            return 130

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

    results = run_job(client, seasons, current, args)
    return 1 if any(r.bracket == "error" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
