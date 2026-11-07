import os
import urllib.request
import urllib.parse
import json
import time
import re
import ssl
import xml.etree.ElementTree as ET
import config
from config import PRODUCT_FORMATS, SKIN_CONCERNS, COMMERCIAL_INTENTS, GEMINI_API_KEY, GEMINI_MODEL, SERPER_API_KEY
from database import save_raw_keywords

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
}

SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

def fetch_google_trending_vietnam(min_volume: int = 1000, hours: int = 168) -> list[dict]:
    """Cào danh sách từ khóa xu hướng thực tế tại Việt Nam từ Google Trends (https://trends.google.com/trending?geo=VN)."""
    url = f"https://trends.google.com/trending?geo=VN&hours={hours}"
    results = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12, context=SSL_CTX) as resp:
            html = resp.read().decode("utf-8")
        
        matches = re.findall(r'AF_initDataCallback\s*\(\s*\{key:\s*[\'"][^\'"]+[\'"],\s*hash:\s*[\'"][^\'"]+[\'"],\s*data:\s*(\[.*?\])\s*,\s*sideChannel', html, re.DOTALL)
        if len(matches) > 1:
            data = json.loads(matches[1])
            items = data[1] if len(data) > 1 and isinstance(data[1], list) else []
            for item in items:
                if not isinstance(item, list) or len(item) == 0:
                    continue
                query = str(item[0]).strip() if item[0] else ""
                if not query:
                    continue
                
                vol = item[6] if len(item) > 6 and isinstance(item[6], (int, float)) else 0
                if vol < min_volume:
                    continue
                    
                related = []
                if len(item) > 9 and isinstance(item[9], list):
                    related = [str(r).strip() for r in item[9] if r and isinstance(r, str)]
                    
                results.append({
                    "query": query,
                    "volume": int(vol),
                    "related": related
                })
        print(f"🔥 [GOOGLE TRENDS VN]: Thu thập được {len(results)} xu hướng thịnh hành (Volume >= {min_volume:,})")
    except Exception as e:
        print(f"[!] Lỗi cào Google Trends trực tiếp: {e}. Thử fallback sang RSS...")
        try:
            rss_url = "https://trends.google.com/trending/rss?geo=VN"
            req_rss = urllib.request.Request(rss_url, headers=HEADERS)
            with urllib.request.urlopen(req_rss, timeout=8, context=SSL_CTX) as resp_rss:
                root = ET.fromstring(resp_rss.read())
                for it in root.findall("./channel/item"):
                    title = it.find("title").text if it.find("title") is not None else ""
                    if not title:
                        continue
                    traffic_el = it.find("{https://trends.google.com/trending/rss}approx_traffic")
                    traffic_txt = traffic_el.text if traffic_el is not None else "1,000+"
                    num = int(re.sub(r'[^\d]', '', traffic_txt) or 1000)
                    if num >= min_volume:
                        results.append({
                            "query": title.strip(),
                            "volume": num,
                            "related": []
                        })
        except Exception as rss_err:
            print(f"[!] Lỗi RSS Google Trends: {rss_err}")

    return results

def fetch_google_suggestions(query: str) -> list[str]:
    """Lấy danh sách từ khóa gợi ý tự động từ Google Search theo thời gian thực (100% Miễn phí)."""
    encoded_query = urllib.parse.quote(query)
    url = f"https://suggestqueries.google.com/complete/search?client=chrome&hl=vi&gl=vn&q={encoded_query}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=6, context=SSL_CTX) as response:
            data = json.loads(response.read().decode("utf-8"))
            if len(data) > 1 and isinstance(data[1], list):
                return [s.strip() for s in data[1] if isinstance(s, str)]
    except Exception:
        pass
    return []

# CHỦ ĐỀ 1: DA LIỄU & DƯỢC MỸ PHẨM (Da cơ thể, Mỹ phẩm, Thuốc da liễu)
CORE_DERM_SEEDS = [
    # 1. Da cơ thể & Vấn đề da body
    "viêm nang lông", "mụn lưng", "thâm mông", "thâm nách", "rạn da body",
    "da rắn vảy cá", "dày sừng nang lông", "ngứa da cơ thể", "viêm da cơ địa",
    "chàm da", "vảy nến", "nấm da", "hắc lào", "lang ben", "nứt nẻ gót chân",
    # 2. Định dạng mỹ phẩm & Hoạt chất
    "serum trị mụn lưng", "kem trị viêm nang lông", "dung dịch peel da body",
    "peel da trị mụn", "sữa tắm trị viêm nang lông", "kem body urea",
    "serum b5 phục hồi", "gel chấm mụn", "kem trị rạn da sau sinh", "kem làm mờ thâm nách",
    # 3. Thuốc da liễu & Đặc trị
    "thuốc bôi viêm nang lông", "thuốc trị nấm da", "kem bôi vảy nến",
    "thuốc đặc trị chàm", "kem phục hồi da không corticoid"
]

# CHỦ ĐỀ 2: ĐỒ ĐIỆN TỬ GIA DỤNG (Gia dụng thông minh, Thiết bị điện tử nhà bếp & gia đình)
CORE_APPLIANCE_SEEDS = [
    # 1. Thiết bị nhà bếp thông minh
    "nồi chiên không dầu", "nồi cơm điện cao tần", "máy ép chậm", "máy làm sữa hạt",
    "máy xay sinh tố đa năng", "lò vi sóng có nướng", "bếp từ đơn", "bếp từ đôi",
    "nồi áp suất điện", "nồi nấu chậm", "máy rửa bát mini", "ấm siêu tốc thủy tinh",
    "nồi lẩu nướng đa năng", "máy hút chân không thực phẩm",
    # 2. Thiết bị làm sạch & chăm sóc không gian sống
    "robot hút bụi lau nhà", "máy hút bụi cầm tay", "máy lọc không khí bù ẩm",
    "máy hút ẩm gia đình", "bàn ủi hơi nước cầm tay", "máy sấy quần áo thông minh",
    "quạt tích điện mini", "quạt không cánh", "máy tạo độ ẩm phun sương", "máy sưởi dầu gốm ceramic",
    # 3. Thiết bị điện tử gia đình & đời sống
    "máy sấy tóc ion âm", "máy cạo râu điện", "bàn chải điện sóng âm",
    "máy tăm nước cầm tay", "máy massage cổ vai gáy", "máy tiệt trùng sấy khô"
]

def harvest_all_raw_keywords(min_volume: int = 1000, trend_hours: int = 168, max_seeds: int = 40, topic_mode: str = "topic_1", session_id: str = "", topic: str = "") -> int:
    """TẦNG 1: Thu thập từ khóa thô từ Google Trends VN theo Volume đã chọn + Matrix theo từng Chủ đề."""
    print("=" * 60)
    print("🚀 [TẦNG 1 - GOOGLE TRENDS INGESTION]: BẮT ĐẦU THU THẬP TỪ KHÓA THÔ...")
    print(f"📊 [BỘ LỌC VOLUME GOOGLE TRENDS]: Khối lượng tìm kiếm >= {min_volume:,} | Khung giờ: {trend_hours}h")
    print(f"🏷️ [NGÀNH HÀNG ĐANG CHỌN]: {'Chủ đề 2: Đồ Điện Tử Gia Dụng' if topic_mode == 'topic_2' else 'Chủ đề 1: Da Liễu & Dược Mỹ Phẩm'}")
    print("=" * 60)
    
    total_harvested = 0

    # 1. Cào từ khóa thực tế từ Google Trends Việt Nam theo Volume đã chọn
    trends_items = fetch_google_trending_vietnam(min_volume=min_volume, hours=trend_hours)
    trending_queries = []
    for item in trends_items:
        q = item["query"]
        vol = item["volume"]
        trending_queries.append(q)
        for r in item.get("related", []):
            if r and r not in trending_queries:
                trending_queries.append(r)

    print(f"[*] Thu được {len(trending_queries)} từ khóa từ luồng Google Trends VN.")
    if trending_queries:
        saved_trends = save_raw_keywords(
            trending_queries,
            seed_term="Google Trends VN",
            source="google_trends",
            session_id=session_id,
            topic=topic or "Google Trends VN"
        )
        total_harvested += saved_trends
        print(f"[✓] Đã lưu {saved_trends} từ khóa Google Trends vào SQLite.")

    # 2. Khai phá hạt giống theo Chủ đề đã chọn
    if topic_mode == "topic_2":
        seed_list = CORE_APPLIANCE_SEEDS
        modifiers = ["loại nào tốt", "giá bao nhiêu", "tiết kiệm điện", "review", "chính hãng", "cho gia đình", "mini", "thông minh"]
        print(f"\n[*] Đang mở rộng các cụm từ hạt giống Đồ Điện Tử Gia Dụng cốt lõi...")
    else:
        seed_list = CORE_DERM_SEEDS
        modifiers = ["giá bao nhiêu", "review", "cho da dầu", "tại nhà", "loại nào tốt", "mua ở đâu", "cho bà bầu", "bác sĩ khuyên dùng"]
        print(f"\n[*] Đang mở rộng các cụm từ hạt giống Da Liễu & Dược Mỹ Phẩm cốt lõi...")
    
    for idx, seed in enumerate(seed_list[:max_seeds], start=1):
        collected = set()
        collected.add(seed)

        suggs = fetch_google_suggestions(seed)
        collected.update(suggs)

        mod = modifiers[idx % len(modifiers)]
        mod_suggs = fetch_google_suggestions(f"{seed} {mod}")
        collected.update(mod_suggs)

        saved = save_raw_keywords(
            list(collected),
            seed_term=seed,
            source="google_suggest",
            session_id=session_id,
            topic=topic or ("Đồ Điện Tử Gia Dụng" if topic_mode == "topic_2" else "Da Liễu & Dược Mỹ Phẩm")
        )
        total_harvested += saved
        time.sleep(0.08)

    print(f"\n[✓] Hoàn thành Tầng 1! Tổng cộng {total_harvested} từ khóa thô đã sẵn sàng cho Tầng 2.")
    return total_harvested
