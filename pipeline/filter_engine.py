import re
import os
import time
import json
import config
from config import BLACKLIST_RETAILERS, PRODUCT_FORMATS, SKIN_CONCERNS, COMMERCIAL_INTENTS, SERPER_API_KEY
from database import get_connection, mark_keyword_filtered, save_raw_keywords

# CHỦ ĐỀ 1: DA LIỄU & DƯỢC MỸ PHẨM (Da cơ thể người, Mỹ phẩm, Thuốc da liễu)
DERM_BODY_TOPICS = [
    "da", "body", "cơ thể", "lưng", "mông", "nách", "bẹn", "ngực", "bắp tay",
    "nang lông", "viêm nang lông", "dày sừng", "rạn da", "vảy cá", "da rắn",
    "khô ráp", "nứt nẻ", "gót chân", "cùi chỏ", "đầu gối", "thâm mông", "thâm nách",
    "chàm", "eczema", "vảy nến", "nấm da", "hắc lào", "lang ben", "viêm da", "ngứa"
]

COSMETICS_TOPICS = [
    "mỹ phẩm", "dược mỹ phẩm", "kem", "serum", "gel", "lotion", "dung dịch",
    "peel", "tẩy da chết", "sữa tắm", "tinh chất", "chấm mụn", "dưỡng trắng",
    "phục hồi", "dưỡng ẩm", "chống nắng", "urea", "bha", "aha", "salicylic",
    "b5", "niacinamide", "retinol", "arbutin", "tca", "glycolic"
]

MEDICINE_TOPICS = [
    "thuốc", "da liễu", "thuốc bôi", "thuốc trị", "đặc trị", "kháng viêm",
    "kháng nấm", "kem bôi", "tuýp bôi", "bác sĩ da liễu", "kê đơn", "không corticoid"
]

ALL_DERM_KEYWORDS = set(DERM_BODY_TOPICS + COSMETICS_TOPICS + MEDICINE_TOPICS + PRODUCT_FORMATS + SKIN_CONCERNS)

# CHỦ ĐỀ 2: ĐỒ ĐIỆN TỬ GIA DỤNG (Thiết bị nhà bếp, gia dụng thông minh, điện tử gia đình)
APPLIANCE_KEYWORDS = {
    "nồi", "chiên", "không dầu", "cơm điện", "cao tần", "áp suất", "nấu chậm", "nấu cháo",
    "máy ép", "ép chậm", "sữa hạt", "máy xay", "sinh tố", "lò vi sóng", "lò nướng",
    "bếp từ", "bếp hồng ngoại", "máy rửa bát", "ấm siêu tốc", "bình thủy điện", "nồi lẩu", "lẩu nướng",
    "robot", "hút bụi", "lau nhà", "máy lọc", "không khí", "lọc nước", "hút ẩm", "tạo ẩm", "hút chân không",
    "bàn ủi", "hơi nước", "bàn là", "máy sấy", "quần áo", "quạt", "tích điện", "không cánh", "máy sưởi", "sưởi dầu",
    "máy sấy tóc", "ion âm", "cạo râu", "bàn chải điện", "tăm nước", "massage", "cổ vai gáy", "tiệt trùng",
    "thiết bị gia dụng", "đồ gia dụng", "gia dụng", "điện gia dụng", "điện tử", "thông minh"
}

def is_blacklisted_brand(keyword: str) -> bool:
    """Kiểm tra xem từ khóa có chứa các chuỗi bán lẻ lớn cần tránh cạnh tranh trực diện không."""
    kw = keyword.lower()
    for brand in BLACKLIST_RETAILERS:
        if re.search(r'\b' + re.escape(brand) + r'\b', kw) or brand in kw:
            return True
    return False

def check_topic_relevance(keyword: str, topic_mode: str = "topic_1") -> bool:
    """Kiểm tra từ khóa có liên quan mật thiết đến chủ đề đang chọn hay không."""
    kw = keyword.lower().strip()
    if topic_mode == "topic_2":
        return any(term in kw for term in APPLIANCE_KEYWORDS)
    return any(term in kw for term in ALL_DERM_KEYWORDS)

def is_sweet_spot_candidate(keyword: str, topic_mode: str = "topic_1") -> tuple[bool, str]:
    """Kiểm tra điều kiện Sweet Spot theo chủ đề đã chọn."""
    kw = keyword.lower().strip()
    
    # 1. Kiểm tra độ dài từ khóa
    if len(kw) < 5:
        return False, "Từ khóa quá ngắn"
    if len(kw) > 85:
        return False, "Từ khóa quá dài / Spam query"
        
    # 2. Kiểm tra chuỗi bán lẻ lớn (Blacklist)
    if is_blacklisted_brand(kw):
        return False, "Chứa tên chuỗi bán lẻ lớn (Blacklist Brand)"
        
    # 3. Loại bỏ câu hỏi thuần kiến thức chung chung
    pure_info_stops = ["là gì", "định nghĩa", "hình ảnh", "bài giảng", "wiki", "nguyên nhân gây ra"]
    if any(stop in kw for stop in pure_info_stops):
        return False, "Chỉ hỏi thông tin chung chung, không có ý định mua sản phẩm"
        
    # 4. Kiểm tra đúng ngành hàng đang chọn
    if not check_topic_relevance(kw, topic_mode=topic_mode):
        if topic_mode == "topic_2":
            return False, "Không liên quan đến Đồ Điện Tử Gia Dụng"
        return False, "Không liên quan đến Da Liễu & Dược Mỹ Phẩm"
        
    return True, "Passed"

def run_pre_filtering(session_id: str = "", topic_mode: str = "topic_1") -> dict:
    """TẦNG 2: Dùng Serper.dev tìm kiếm, thẩm định chủ đề và lọc từ khóa Sweet Spot."""
    topic_label = "Chủ đề 2: Đồ Điện Tử Gia Dụng" if topic_mode == "topic_2" else "Chủ đề 1: Da Liễu & Dược Mỹ Phẩm"
    print("=" * 60)
    print("🔎 [TẦNG 2 - SERPER & PRE-FILTERING]: BẮT ĐẦU LỌC CHỦ ĐỀ & THẨM ĐỊNH TỪ KHÓA...")
    print(f"📌 [TIÊU CHUẨN LỌC NGÀNH HÀNG]: {topic_label}")
    print("=" * 60)
    
    conn = get_connection()
    cursor = conn.cursor()
    if session_id:
        cursor.execute("SELECT keyword, source FROM raw_keywords WHERE is_filtered = 0 AND session_id = ?", (session_id,))
    else:
        cursor.execute("SELECT keyword, source FROM raw_keywords WHERE is_filtered = 0")
    rows = cursor.fetchall()
    conn.close()
    
    total = len(rows)
    passed_count = 0
    filtered_count = 0
    
    serper_key = (getattr(config, "SERPER_API_KEY", "") or os.getenv("SERPER_API_KEY", "")).strip()
    serper_active = bool(serper_key)

    if serper_active:
        print(f"⚡ [SERPER.DEV TÍCH HỢP]: Sẵn sàng tìm kiếm Google SERP & bóc tách Related Searches ngành hàng.")
        from pipeline.serp_fetcher import fetch_serp_via_serper
    
    serp_queries_harvested = 0

    for idx, row in enumerate(rows, start=1):
        kw = row["keyword"]

        passed, reason = is_sweet_spot_candidate(kw, topic_mode=topic_mode)
        if passed:
            passed_count += 1
            if serper_active and serp_queries_harvested < 10 and idx <= 20:
                try:
                    serp_data = fetch_serp_via_serper(kw, num_results=5)
                    if serp_data:
                        serp_queries_harvested += 1
                except Exception:
                    pass
        else:
            filtered_count += 1
            mark_keyword_filtered(kw, reason)
            
    print(f"\n[*] Tổng số từ khóa đã thẩm định ở Tầng 2: {total}")
    print(f"[✓] Từ khóa ĐẠT CHUẨN {topic_label} (Sweet Spot): {passed_count}")
    print(f"[X] Từ khóa bị loại (Xu hướng không liên quan / Blacklist brand): {filtered_count}")
    
    return {
        "total_evaluated": total,
        "passed": passed_count,
        "filtered": filtered_count
    }
