import requests
import json
import time
import os
import getpass
from typing import Dict, List, Optional

# ====== Race & Class Maps ======
RACE_MAP = {
    1: '人類', 2: '獸人', 3: '矮人', 4: '夜精靈', 5: '不死族',
    6: '牛頭人', 7: '地精', 8: '食人妖', 9: '哥布林', 10: '血精靈',
    11: '德萊尼', 24: '熊貓人', 25: '熊貓人', 26: '熊貓人'
}

CLASS_MAP = {
    1:'戰士', 2:'聖騎士', 3:'獵人', 4:'盜賊', 5:'牧師', 6:'死亡騎士',
    7:'薩滿', 8:'法師', 9:'術士', 10:'武僧', 11:'德魯伊',
    12:'惡魔獵人', 13:'喚法師'
}

class WoWPvPLeaderboard:
    """WoW PvP 排行榜資料抓取類別"""
    
    def __init__(self, client_id: str, client_secret: str, region: str = 'us'):
        self.client_id = client_id
        self.client_secret = client_secret
        self.region = region
        self.api_host = os.getenv("WOW_API_HOST", "tw.api.blizzard.com")
        self.data_namespace = os.getenv("WOW_DATA_NAMESPACE", "dynamic-classic-tw")
        self.profile_namespace = os.getenv("WOW_PROFILE_NAMESPACE", "profile-classic-tw")
        self.locale = os.getenv("WOW_LOCALE", "en_TW")
        self.access_token = None
        self.available_brackets = ['2v2', '3v3', '5v5', 'rbg']
        self.character_cache = {}
    
    def get_access_token(self) -> bool:
        try:
            data = {'grant_type': 'client_credentials'}
            token_url = f'https://{self.region}.battle.net/oauth/token'
            response = requests.post(token_url, data=data, auth=(self.client_id, self.client_secret), timeout=30)
            if response.status_code != 200:
                print(f"[ERROR] Token 請求失敗，狀態碼: {response.status_code}")
                print(f"錯誤內容: {response.text}")
                return False
            result = response.json()
            if 'access_token' in result:
                self.access_token = result['access_token']
                print(f"[OK] 成功獲取 access token")
                return True
            else:
                print(f"[ERROR] 無法獲取 access token: {result}")
                return False
        except Exception as e:
            print(f"[ERROR] 獲取 access token 時發生錯誤: {e}")
            return False

    def get_api_url(self, season: int, bracket: str) -> str:
        base_url = f"https://{self.api_host}/data/wow"
        if season >= 9:
            return f"{base_url}/pvp-season/{season}/pvp-leaderboard/{bracket}"
        else:
            return f"{base_url}/pvp-region/0/pvp-season/{season}/pvp-leaderboard/{bracket}"

    def fetch_character_details(self, realm_slug: str, character_name: str) -> Optional[Dict]:
        lowercase_name = ''.join(c.lower() if 'A' <= c <= 'Z' else c for c in character_name)
        encoded_name = requests.utils.quote(lowercase_name)
        cache_key = f"{realm_slug}:{encoded_name}"
        if cache_key in self.character_cache:
            print(f"[CACHE] 從快取取得 {character_name} 詳細資料")
            return self.character_cache[cache_key]
        if not self.access_token:
            return None
        try:
            url = f"https://{self.api_host}/profile/wow/character/{realm_slug}/{encoded_name}"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            params = {"namespace": self.profile_namespace, "locale": self.locale}
            response = requests.get(url, headers=headers, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                self.character_cache[cache_key] = data
                return data
            else:
                print(f"[WARN] 無法獲取角色 {character_name} 的詳情: HTTP {response.status_code}")
                return None
        except Exception as e:
            print(f"[WARN] 獲取角色 {character_name} 詳情時發生錯誤: {e}")
            return None

    def enrich_character_data(self, character_data: Dict, realm_slug: str) -> Dict:
        character_name = character_data.get('name')
        if not character_name:
            return character_data
        character_details = self.fetch_character_details(realm_slug, character_name)
        if character_details:
            if 'character_class' in character_details:
                character_data['playable_class'] = character_details['character_class']
            if 'race' in character_details:
                character_data['playable_race'] = character_details['race']
            race_id = character_data.get('playable_race', {}).get('id')
            class_id = character_data.get('playable_class', {}).get('id')
            race_name = RACE_MAP.get(race_id, f"Race{race_id}")
            class_name = CLASS_MAP.get(class_id, f"Class{class_id}")
            print(f"[OK] API補充: {character_name} ({race_name} {class_name})")
        else:
            print(f"[WARN] 無法獲取角色 {character_name} 的詳細信息")
        return character_data

    def get_pvp_season_index(self) -> Optional[Dict]:
        if not self.access_token:
            print("需要先取得 access token")
            return None
        try:
            url = f"https://{self.api_host}/data/wow/pvp-season/index"
            headers = {"Authorization": f"Bearer {self.access_token}"}
            params = {"namespace": self.data_namespace, "locale": self.locale}
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                print(f"無法取得 PvP 賽季清單: HTTP {response.status_code}")
                print(f"錯誤內容: {response.text}")
                return None
            return response.json()
        except Exception as e:
            print(f"取得 PvP 賽季清單時發生錯誤: {e}")
            return None

    def get_available_seasons(self) -> List[int]:
        data = self.get_pvp_season_index()
        if not data:
            return []

        season_ids = []
        for season in data.get("seasons", []):
            season_id = season.get("id")
            if season_id is not None:
                season_ids.append(int(season_id))

        return sorted(set(season_ids))

    def get_current_season(self) -> Optional[int]:
        data = self.get_pvp_season_index()
        if not data:
            return None

        current_id = data.get("current_season", {}).get("id")
        if current_id:
            return int(current_id)

        seasons = [season.get("id") for season in data.get("seasons", []) if season.get("id")]
        if seasons:
            return int(max(seasons))

        return None

    def fetch_bracket_data(self, bracket: str, season: int = 12) -> Optional[Dict]:
        if not self.access_token:
            print("[ERROR] 請先獲取 access token")
            return None
        if season < 9 and bracket == 'rbg':
            print(f"[WARN] Season {season} 不支援 {bracket} 賽制")
            return None
        if bracket not in self.available_brackets:
            print(f"[ERROR] 不支援的賽制: {bracket}")
            return None
        try:
            url = self.get_api_url(season, bracket)
            headers = {"Authorization": f"Bearer {self.access_token}"}
            params = {"namespace": self.data_namespace, "locale": self.locale}
            print(f"正在獲取 Season {season} {bracket} 基礎資料...")
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code != 200:
                print(f"[ERROR] HTTP 錯誤 {response.status_code}")
                print(f"錯誤內容: {response.text}")
                return None
            if not response.text.strip():
                print("[ERROR] API 回傳空的回應")
                return None
            data = response.json()
            if 'error' in data:
                print(f"[ERROR] {bracket} API 錯誤: {data.get('error', {}).get('message', 'Unknown error')}")
                return None
            print(f"[OK] {bracket} 成功獲取 {len(data.get('entries', []))} 筆基礎資料")
            return data
        except Exception as e:
            print(f"[ERROR] 獲取 {bracket} 資料時發生錯誤: {e}")
            return None

    def merge_with_existing_data(self, temp_data: Dict, bracket: str, season: int, enrich_data: bool, output_dir: str = "./data") -> Dict:
        final_entries = []
        final_filename = f"{output_dir}/season_{season}_{bracket}_tw_arena.json"
        old_data = {}
        if os.path.exists(final_filename):
            with open(final_filename, "r", encoding="utf-8") as f:
                try:
                    old_data = json.load(f)
                except json.JSONDecodeError:
                    print(f"[WARN] 舊檔案 {final_filename} JSON 格式錯誤，忽略")
        # 將舊資料寫入 character_cache
        for entry in old_data.get("entries", []):
            char = entry.get("character")
            if char:
                key = f"{char.get('realm', {}).get('slug','')}:{char.get('name','').lower()}"
                self.character_cache[key] = char
        old_lookup = {}
        for entry in old_data.get("entries", []):
            char = entry.get("character")
            if char:
                key = f"{char.get('realm', {}).get('slug','')}:{char.get('name','').lower()}"
                old_lookup[key] = char
        reused_count = 0
        api_count = 0
        for idx, entry in enumerate(temp_data.get("entries", []), start=1):
            if "character" in entry:
                char = entry["character"]
                key = f"{char.get('realm', {}).get('slug','')}:{char.get('name','').lower()}"
                race_id = char.get('playable_race', {}).get('id')
                class_id = char.get('playable_class', {}).get('id')
                race_name = RACE_MAP.get(race_id, f"Race{race_id}")
                class_name = CLASS_MAP.get(class_id, f"Class{class_id}")
                rank = entry.get("rank", "?")
                rating = entry.get("rating", "?")

                if key in old_lookup:
                    if 'playable_class' in old_lookup[key]:
                        char['playable_class'] = old_lookup[key]['playable_class']
                    if 'playable_race' in old_lookup[key]:
                        char['playable_race'] = old_lookup[key]['playable_race']
                    entry["character"] = char
                    reused_count += 1
                    print(f"#{idx} 舊資料命中: {char.get('name')} ({race_name} {class_name}) Rank: {rank}, Rating: {rating}")
                elif enrich_data:
                    realm_slug = char.get("realm", {}).get("slug", "unknown")
                    entry["character"] = self.enrich_character_data(char, realm_slug)
                    api_count += 1
                    print(f"#{idx} 新API取得: {char.get('name')} ({race_name} {class_name}) Rank: {rank}, Rating: {rating}")
            final_entries.append(entry)
        temp_data["entries"] = final_entries
        temp_filename = f"{final_filename}.tmp"
        with open(temp_filename, "w", encoding="utf-8") as f:
            json.dump(temp_data, f, ensure_ascii=False, indent=2)
        os.replace(temp_filename, final_filename)
        print(f"[OK] 已更新並覆蓋 {final_filename}")
        print(f"統計: 從舊檔案補齊 {reused_count} 個角色, API 呼叫 {api_count} 個角色")
        return temp_data

    def get_available_brackets_for_season(self, season: int) -> List[str]:
        return ['2v2', '3v3', '5v5'] if season < 9 else ['2v2', '3v3', '5v5', 'rbg']

def get_user_choice(prompt: str, options: List[str]) -> List[str]:
    print(f"\n{prompt}")
    for i, option in enumerate(options, 1):
        print(f"{i}. {option}")
    print(f"{len(options)+1}. 全選")
    if 'rbg' in options:
        print(f"{len(options)+2}. rbg以外全選")
    print("0. 跳過")
    while True:
        choice = input("請輸入選項: ").strip()
        if choice == '0':
            return []
        elif choice == str(len(options)+1):
            return options.copy()
        elif 'rbg' in options and choice == str(len(options)+2):
            return [o for o in options if o != 'rbg']
        else:
            try:
                idxs = [int(x) for x in choice.split(',')]
                selected = [options[i-1] for i in idxs if 1 <= i <= len(options)]
                if selected:
                    return selected
                print("請輸入有效的選項編號")
            except:
                print("請輸入有效的數字")

def get_season_input(wow_client: WoWPvPLeaderboard) -> List[int]:
    while True:
        print("\n請選擇要抓取的賽季:")
        print("1. 單個賽季")
        available_seasons = wow_client.get_available_seasons()
        current_season = max(available_seasons) if available_seasons else wow_client.get_current_season()
        season_label = (
            f"Season {available_seasons[0]}-{available_seasons[-1]}"
            if available_seasons
            else "目前 API 可用賽季"
        )
        print(f"2. 全部賽季 ({season_label})")
        mode = input("請輸入選項 (1 或 2): ").strip()
        if mode == '1':
            try:
                season = int(input("請輸入賽季編號: ").strip())
            except ValueError:
                print("請輸入有效的賽季數字")
                continue
            if available_seasons and season not in available_seasons:
                print(f"Season {season} 目前不在 API 可用賽季清單內")
                continue
            return [season]
        elif mode == '2':
            if available_seasons:
                return available_seasons
            if current_season:
                return list(range(1, current_season + 1))
            print("無法動態取得目前賽季，請改用單一賽季輸入")
            continue
        else:
            print("請輸入正確選項")

def read_blizzard_credentials() -> Optional[Dict[str, str]]:
    client_id = os.getenv("BLIZZARD_CLIENT_ID") or os.getenv("BNET_CLIENT_ID")
    client_secret = os.getenv("BLIZZARD_CLIENT_SECRET") or os.getenv("BNET_CLIENT_SECRET")
    region = os.getenv("BLIZZARD_REGION") or os.getenv("BNET_REGION") or "us"

    if client_id and client_secret:
        return {"client_id": client_id, "client_secret": client_secret, "region": region}

    print("未偵測到 Blizzard API 環境變數。")
    print("建議設定 BLIZZARD_CLIENT_ID 與 BLIZZARD_CLIENT_SECRET，避免把 token 寫進程式。")
    client_id = client_id or input("請輸入 Blizzard Client ID: ").strip()
    client_secret = client_secret or getpass.getpass("請輸入 Blizzard Client Secret: ").strip()

    if not client_id or not client_secret:
        print("[ERROR] Blizzard Client ID / Secret 不可為空")
        return None

    return {"client_id": client_id, "client_secret": client_secret, "region": region}

def process_single_season(wow_client: WoWPvPLeaderboard, season: int, selected_brackets: List[str], enrich_data: bool) -> int:
    print(f"\n{'='*60}\n處理 Season {season}\n{'='*60}")
    available_brackets = wow_client.get_available_brackets_for_season(season)
    season_brackets = [b for b in selected_brackets if b in available_brackets]
    if not season_brackets:
        return 0
    success_count = 0
    for bracket in season_brackets:
        print(f"\n{'-'*40}\n處理 Season {season} {bracket} 資料...\n{'-'*40}")
        raw_data = wow_client.fetch_bracket_data(bracket, season)
        if raw_data:
            temp_filename = f"./data/season_{season}_{bracket}_temp.json"
            os.makedirs("./data", exist_ok=True)
            with open(temp_filename, "w", encoding="utf-8") as f:
                json.dump(raw_data, f, ensure_ascii=False, indent=2)
            print(f"[OK] 已暫存基礎資料到 {temp_filename}")
            wow_client.merge_with_existing_data(raw_data, bracket, season, enrich_data)
            success_count += 1
    return success_count

def main():
    print("=" * 60)
    print("    WoW PvP 排行榜資料抓取工具 (新版快取機制)")
    print("=" * 60)
    credentials = read_blizzard_credentials()
    if not credentials:
        return

    wow_client = WoWPvPLeaderboard(**credentials)
    if not wow_client.get_access_token():
        return
    seasons = get_season_input(wow_client)
    max_season = max(seasons)
    brackets = wow_client.get_available_brackets_for_season(max_season)
    selected_brackets = get_user_choice("請選擇要抓取的賽制:", brackets)
    if not selected_brackets:
        return
    enrich_choice = input("是否需要獲取角色詳細信息？(y/n): ").strip().lower()
    enrich_data = enrich_choice in ['y','yes']
    total_success, total_possible = 0, 0
    start_time = time.time()
    for season in seasons:
        total_success += process_single_season(wow_client, season, selected_brackets, enrich_data)
        total_possible += len([b for b in selected_brackets if b in wow_client.get_available_brackets_for_season(season)])
    print("\n" + "="*60)
    print(f"總成功數: {total_success}/{total_possible}")
    print(f"總處理時間: {time.time()-start_time:.1f} 秒")
    print("完成！")

if __name__ == "__main__":
    main()


