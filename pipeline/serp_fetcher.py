import requests
import json
import urllib.parse
import urllib3
import config
from config import SERPER_API_KEY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def _safe_post(url, headers=None, data=None, timeout=10):
    try:
        return requests.post(url, headers=headers, data=data, timeout=timeout)
    except (requests.exceptions.SSLError, requests.exceptions.ConnectionError):
        return requests.post(url, headers=headers, data=data, timeout=timeout, verify=False)

def test_serper_connection(api_key: str = None) -> dict:
    """Kiểm tra tính hợp lệ của Serper.dev API Key."""
    key = (api_key or getattr(config, "SERPER_API_KEY", "") or "").strip()
    if not key:
        return {"success": False, "message": "Vui lòng nhập Serper.dev API Key trước khi kiểm tra!"}
    
    url = "https://google.serper.dev/search"
    payload = json.dumps({"q": "kem tri mun", "gl": "vn", "hl": "vi", "num": 1})
    headers = {
        'X-API-KEY': key,
        'Content-Type': 'application/json'
    }
    try:
        response = _safe_post(url, headers=headers, data=payload, timeout=10)
        if response.status_code == 200:
            return {"success": True, "message": "Kết nối Serper.dev thành công! Đã sẵn sàng trích xuất Top 5 SERP Google."}
        elif response.status_code == 403 or response.status_code == 401:
            return {"success": False, "message": "Serper.dev báo lỗi: API Key không đúng hoặc chưa kích hoạt (401/403)!"}
        else:
            return {"success": False, "message": f"Serper.dev trả về mã lỗi HTTP {response.status_code}: {response.text[:120]}"}
    except Exception as e:
        return {"success": False, "message": f"Lỗi kết nối Serper.dev: {str(e)}"}

def fetch_serp_via_serper(keyword: str, num_results=5) -> list[dict]:
    """Lấy Top kết quả tìm kiếm Google thông qua Serper.dev API."""
    key = (getattr(config, "SERPER_API_KEY", "") or "").strip()
    if not key:
        return []
        
    url = "https://google.serper.dev/search"
    payload = json.dumps({
        "q": keyword,
        "gl": "vn",
        "hl": "vi",
        "num": num_results
    })
    headers = {
        'X-API-KEY': key,
        'Content-Type': 'application/json'
    }
    
    try:
        response = _safe_post(url, headers=headers, data=payload, timeout=10)
        if response.status_code == 200:
            data = response.json()
            results = []
            for item in data.get("organic", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "link": item.get("link", "")
                })
            return results
    except Exception as e:
        print(f"[!] Lỗi Serper.dev API: {e}")
    return []

def fetch_serp_fallback(keyword: str, num_results=5) -> list[dict]:
    """Cơ chế dự phòng làm giàu dữ liệu SERP khi chưa có SERPER_API_KEY."""
    return [
        {
            "title": f"Top các sản phẩm {keyword} được đánh giá cao",
            "snippet": f"Tìm hiểu công dụng, thành phần, giá bán và đánh giá thực tế của người dùng về {keyword} trên thị trường Việt Nam.",
            "link": "https://google.com/search?q=" + urllib.parse.quote(keyword)
        }
    ]

def get_serp_snippets(keyword: str) -> list[dict]:
    """TẦNG 3 - Bước 1: Thu thập SERP snippets cho từ khóa."""
    active_key = (getattr(config, "SERPER_API_KEY", "") or "").strip()
    if active_key:
        serp = fetch_serp_via_serper(keyword)
        if serp:
            return serp
    return fetch_serp_fallback(keyword)
