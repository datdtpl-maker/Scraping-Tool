import base64
import json
import requests
import urllib3
import config

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DATAFORSEO_API_BASE = "https://api.dataforseo.com/v3"

def _safe_get(url, headers=None, timeout=12):
    try:
        return requests.get(url, headers=headers, timeout=timeout)
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
        return requests.get(url, headers=headers, timeout=timeout, verify=False)

def _safe_post(url, headers=None, json=None, timeout=20):
    try:
        return requests.post(url, headers=headers, json=json, timeout=timeout)
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
        return requests.post(url, headers=headers, json=json, timeout=timeout, verify=False)

def _get_auth_header(login: str = None, password: str = None) -> dict:
    """Tạo HTTP header Basic Authentication cho DataForSEO."""
    active_login = (login or config.DATAFORSEO_LOGIN).strip()
    active_pass = (password or config.DATAFORSEO_PASSWORD).strip()
    if not active_login or not active_pass:
        return {}
    
    cred = f"{active_login}:{active_pass}".encode("utf-8")
    b64 = base64.b64encode(cred).decode("utf-8")
    return {
        "Authorization": f"Basic {b64}",
        "Content-Type": "application/json"
    }

def test_dataforseo_connection(login: str = None, password: str = None) -> dict:
    """Kiểm tra kết nối và truy vấn số dư tài khoản DataForSEO."""
    active_login = (login or config.DATAFORSEO_LOGIN).strip()
    active_pass = (password or config.DATAFORSEO_PASSWORD).strip()
    
    if not active_login or not active_pass:
        return {
            "success": False,
            "message": "Vui lòng nhập đầy đủ DataForSEO API Login và API Password trước khi kiểm tra!"
        }
        
    headers = _get_auth_header(active_login, active_pass)
    url = f"{DATAFORSEO_API_BASE}/appendix/user_data"
    
    try:
        response = _safe_get(url, headers=headers, timeout=12)
        if response.status_code == 200:
            data = response.json()
            if data.get("status_code") == 20000:
                tasks = data.get("tasks", [])
                balance_str = ""
                if tasks and tasks[0].get("result"):
                    res = tasks[0]["result"][0]
                    money = res.get("money", 0)
                    currency = res.get("currency", "USD")
                    balance_str = f" Số dư khả dụng: ${money:,.2f} {currency}."
                return {
                    "success": True,
                    "message": f"Kết nối DataForSEO thành công!{balance_str} Đã sẵn sàng nạp từ khóa & Search Volume."
                }
            else:
                msg = data.get("status_message", "Thông tin đăng nhập không hợp lệ.")
                return {"success": False, "message": f"DataForSEO báo lỗi ({data.get('status_code')}): {msg}"}
        elif response.status_code == 401 or response.status_code == 403:
            return {
                "success": False,
                "message": "Lỗi 401/403 Unauthorized: Vui lòng kiểm tra lại 2 điều sau:\n1. Copy chuẩn xác API Login và API Password.\n2. Tài khoản DataForSEO của bạn đã bấm link kích hoạt trong Email chưa (Nếu có banner vàng 'Verify your account', bạn cần vào mail xác nhận trước)!"
            }
        else:
            return {"success": False, "message": f"DataForSEO trả về mã lỗi HTTP {response.status_code}: {response.text[:120]}"}
    except Exception as e:
        return {"success": False, "message": f"Không thể kết nối đến máy chủ DataForSEO: {str(e)}"}

def fetch_dataforseo_keywords(seeds: list[str], login: str = None, password: str = None, limit: int = 50) -> list[dict]:
    """TẦNG 1: Truy xuất từ khóa liên quan kèm Search Volume từ Google Ads / DataForSEO Labs."""
    headers = _get_auth_header(login, password)
    if not headers or not seeds:
        return []
        
    keywords_clean = [s.strip() for s in seeds if s and s.strip()][:10]
    if not keywords_clean:
        return []

    results = []
    seen = set()

    # Thử Endpoint 1: DataForSEO Labs Keyword Ideas Live (Rất chi tiết và nhanh)
    try:
        url_labs = f"{DATAFORSEO_API_BASE}/dataforseo_labs/google/keyword_ideas/live"
        payload_labs = [
            {
                "keywords": keywords_clean,
                "location_code": 2704,  # Việt Nam
                "language_code": "vi",   # Tiếng Việt
                "limit": limit,
                "include_seed_keyword": True
            }
        ]
        resp = _safe_post(url_labs, headers=headers, json=payload_labs, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            for task in data.get("tasks", []):
                for res in task.get("result", []):
                    for item in res.get("items", []):
                        kw = item.get("keyword", "").strip()
                        if kw and kw.lower() not in seen:
                            seen.add(kw.lower())
                            info = item.get("keyword_info", {})
                            results.append({
                                "keyword": kw,
                                "search_volume": info.get("search_volume") or 0,
                                "cpc": info.get("cpc") or 0.0,
                                "competition": info.get("competition_level") or "LOW",
                                "source": "dataforseo_labs"
                            })
        if results:
            return results
    except Exception as e:
        print(f"[!] DataForSEO Labs thử nghiệm: {e}")

    # Thử Endpoint 2: Google Ads Keywords For Keywords Live
    try:
        url_gads = f"{DATAFORSEO_API_BASE}/keywords_data/google_ads/keywords_for_keywords/live"
        payload_gads = [
            {
                "keywords": keywords_clean,
                "location_code": 2704,
                "language_name": "Vietnamese",
                "include_adult_keywords": False
            }
        ]
        resp = _safe_post(url_gads, headers=headers, json=payload_gads, timeout=20)
        if resp.status_code == 200:
            data = resp.json()
            for task in data.get("tasks", []):
                for res in task.get("result", []):
                    kw = res.get("keyword", "").strip()
                    if kw and kw.lower() not in seen:
                        seen.add(kw.lower())
                        results.append({
                            "keyword": kw,
                            "search_volume": res.get("search_volume") or 0,
                            "cpc": res.get("cpc") or 0.0,
                            "competition": res.get("competition_level") or "LOW",
                            "source": "dataforseo_gads"
                        })
    except Exception as e:
        print(f"[!] DataForSEO Google Ads fallback: {e}")

    return results
