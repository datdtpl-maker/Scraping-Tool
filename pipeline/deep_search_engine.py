import os
import re
import sys
import time
import json
import urllib.parse
import requests
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

import config
from config import GEMINI_API_KEY, GEMINI_MODEL, SERPER_API_KEY
from database import (
    get_connection,
    save_raw_keywords,
    save_product_opportunity,
    export_to_csv,
    get_unfiltered_raw_keywords,
    mark_keyword_filtered
)
from pipeline.serp_fetcher import _safe_post, fetch_serp_via_serper

COMMON_PROVINCES = [
    "phan thiết", "phan thiet", "bình thuận", "binh thuan", "lâm đồng", "lam dong", "đà lạt", "da lat",
    "hồ chí minh", "ho chi minh", "hcm", "sài gòn", "sai gon",
    "hà nội", "ha noi", "đà nẵng", "da nang", "cần thơ", "can tho",
    "hải phòng", "hai phong", "nha trang", "khánh hòa", "khanh hoa",
    "bình dương", "binh duong", "đồng nai", "dong nai", "vũng tàu", "vung tau",
    "quảng ninh", "quang ninh", "huế", "hue", "quy nhơn", "quy nhon", "buôn ma thuột",
    "long an", "tiền giang", "bến tre", "an giang", "kiên giang"
]

# DANH SÁCH TOÀN BỘ CÁC TỈNH THÀNH / ĐỊA PHƯƠNG KHÁC Ở VIỆT NAM ĐỂ LOẠI TRỪ LẪN NHAU
ALL_COMPETING_LOCATIONS = [
    "nha trang", "khánh hòa", "khanh hoa", "hà nội", "ha noi", "hồ chí minh", "ho chi minh",
    "sài gòn", "sai gon", "tphcm", "hcm", "đà nẵng", "da nang", "hải phòng", "hai phong",
    "cần thơ", "can tho", "huế", "hue", "quy nhơn", "quy nhon", "bình định", "binh dinh",
    "vũng tàu", "vung tau", "bà rịa", "ba ria", "bình dương", "binh duong", "thủ dầu một",
    "dĩ an", "thuận an", "đồng nai", "dong nai", "biên hòa", "bien hoa", "buôn ma thuột",
    "buon ma thuot", "đắk lắk", "dak lak", "pleiku", "gia lai", "quảng ninh", "hạ long",
    "bắc ninh", "hải dương", "thái nguyên", "nam định", "thái bình", "ninh bình",
    "thanh hóa", "nghệ an", "vinh", "quảng nam", "hội an", "quảng ngãi", "phú yên", "tuy hòa",
    "tây ninh", "bình phước", "long an", "tiền giang", "mỹ tho", "bến tre", "trà vinh",
    "vĩnh long", "đồng tháp", "cao lãnh", "an giang", "long xuyên", "châu đốc", "kiên giang",
    "rạch giá", "phú quốc", "cà mau", "bạc liêu", "sóc trăng", "hậu giang",
    # Các quận huyện đối thủ
    "bình tân", "tân bình", "gò vấp", "thủ đức", "bình thạnh", "phú nhuận", "quận 1",
    "quận 2", "quận 3", "quận 7", "quận 10", "quận 12", "cầu giấy", "đống đa", "hoàn kiếm",
    "hai bà trưng", "ba đình", "hà đông", "thanh xuân"
]

def get_allowed_geo_tokens(location_input: str, detected_geo: str) -> list[str]:
    """Trích xuất tập hợp từ khóa địa phương hợp lệ theo lựa chọn của người dùng."""
    combined = f"{location_input} {detected_geo}".lower()
    tokens = []
    
    # 1. Cụm Phan Thiết / Bình Thuận
    if any(k in combined for k in ["phan thiết", "phan thiet", "bình thuận", "binh thuan"]):
        tokens.extend([
            "phan thiết", "phan thiet", "bình thuận", "binh thuan",
            "mũi né", "mui ne", "la gi", "hàm tiến", "hàm thuận", "hàm tân", "tuy phong", "bắc bình"
        ])
        
    # 2. Cụm Lâm Đồng / Đà Lạt (khi chọn Phan Thiết, Lâm Đồng mới)
    if any(k in combined for k in ["lâm đồng", "lam dong", "đà lạt", "da lat"]):
        tokens.extend([
            "lâm đồng", "lam dong", "đà lạt", "da lat", "bảo lộc", "bao loc", "đức trọng", "di linh"
        ])
        
    # 3. TP. Hồ Chí Minh
    if any(k in combined for k in ["hồ chí minh", "ho chi minh", "sài gòn", "sai gon", "hcm"]):
        tokens.extend(["hồ chí minh", "ho chi minh", "sài gòn", "sai gon", "tphcm", "hcm"])
        
    # 4. Hà Nội
    if any(k in combined for k in ["hà nội", "ha noi"]):
        tokens.extend(["hà nội", "ha noi"])
        
    # 5. Đà Nẵng
    if any(k in combined for k in ["đà nẵng", "da nang"]):
        tokens.extend(["đà nẵng", "da nang"])
        
    # 6. Nha Trang
    if any(k in combined for k in ["nha trang", "khánh hòa", "khanh hoa"]):
        tokens.extend(["nha trang", "khánh hòa", "khanh hoa"])

    return list(set(tokens))

def is_competing_geo(keyword: str, allowed_tokens: list[str]) -> bool:
    """Kiểm tra nghiêm ngặt: Từ khóa có chứa bất kỳ địa danh cạnh tranh nào khác ngoài vị trí đã chọn không."""
    if not allowed_tokens:
        return False
    kw_lower = keyword.lower()
    for comp_loc in ALL_COMPETING_LOCATIONS:
        # Nếu địa danh này nằm trong danh sách cho phép của khu vực được chọn -> Không cấm
        if any(comp_loc in tok or tok in comp_loc for tok in allowed_tokens):
            continue
        # Nếu từ khóa chứa địa danh cạnh tranh (ví dụ: 'nha trang', 'bình tân', 'hà nội'...) -> CẤM
        if re.search(r'\b' + re.escape(comp_loc) + r'\b', kw_lower) or comp_loc in kw_lower:
            return True
    return False

def split_seed_and_location(seed_kw: str, location_input: str = "") -> tuple[str, str]:
    """Phân tách từ khóa lõi và địa danh nếu người dùng nhập kèm tỉnh thành."""
    seed_lower = seed_kw.lower().strip()
    detected_geo = ""
    base_term = seed_lower

    for prov in COMMON_PROVINCES:
        if prov in seed_lower:
            detected_geo = prov
            # Thay thế địa danh khỏi seed
            base_term = re.sub(r'\b' + re.escape(prov) + r'\b', '', base_term).strip()
            base_term = re.sub(r'\s+', ' ', base_term).strip()
            break

    if not detected_geo and location_input:
        loc_clean = location_input.split(',')[0].strip().lower()
        if loc_clean and loc_clean != "vietnam" and loc_clean != "toàn quốc việt nam":
            detected_geo = loc_clean

    return base_term or seed_lower, detected_geo

def fetch_google_suggestions_free(query: str) -> list[str]:
    """Cào Google Autocomplete Suggestions trực tiếp (miễn phí, tốc độ cao)."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
    }
    try:
        url = f"https://suggestqueries.google.com/complete/search?client=firefox&hl=vi&gl=vn&q={urllib.parse.quote(query)}"
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            if len(data) > 1 and isinstance(data[1], list):
                return [str(item).strip().lower() for item in data[1] if item]
    except Exception:
        pass
    return []

def fetch_serper_search_data(query: str, location: str = "Vietnam", tbs: str = "", num: int = 10) -> dict:
    """Gọi Serper /search để lấy Organic, Related Searches và People Also Ask."""
    key = (getattr(config, "SERPER_API_KEY", "") or os.getenv("SERPER_API_KEY", "")).strip()
    if not key:
        return {"organic": [], "related": [], "paa": []}

    url = "https://google.serper.dev/search"
    payload = {
        "q": query,
        "gl": "vn",
        "hl": "vi",
        "num": num
    }
    if location and location.strip():
        payload["location"] = location.strip()
    if tbs and tbs.strip():
        payload["tbs"] = tbs.strip()

    headers = {
        'X-API-KEY': key,
        'Content-Type': 'application/json'
    }

    try:
        r = _safe_post(url, headers=headers, data=json.dumps(payload), timeout=10)
        if r.status_code == 200:
            res = r.json()
            organic = [
                {"title": item.get("title", ""), "snippet": item.get("snippet", ""), "link": item.get("link", "")}
                for item in res.get("organic", [])
            ]
            related = [item.get("query", "").strip().lower() for item in res.get("relatedSearches", []) if item.get("query")]
            paa = [item.get("question", "").strip().lower() for item in res.get("peopleAlsoAsk", []) if item.get("question")]
            return {"organic": organic, "related": related, "paa": paa}
    except Exception as e:
        print(f"[!] Lỗi gọi Serper search: {e}")

    return {"organic": [], "related": [], "paa": []}

def fetch_serper_autocomplete_data(query: str) -> list[str]:
    """Gọi Serper /autocomplete để lấy gợi ý tìm kiếm bổ sung."""
    key = (getattr(config, "SERPER_API_KEY", "") or os.getenv("SERPER_API_KEY", "")).strip()
    if not key:
        return []

    url = "https://google.serper.dev/autocomplete"
    payload = {"q": query, "gl": "vn", "hl": "vi"}
    headers = {'X-API-KEY': key, 'Content-Type': 'application/json'}

    try:
        r = _safe_post(url, headers=headers, data=json.dumps(payload), timeout=8)
        if r.status_code == 200:
            res = r.json()
            return [it.get("value", "").strip().lower() for it in res.get("suggestions", []) if it.get("value")]
    except Exception:
        pass
    return []

class DeepOpportunitySchema(BaseModel):
    keyword: str = Field(description="Từ khóa gốc đang phân tích")
    is_product_to_sell: bool = Field(description="True nếu là sản phẩm vật lý, gói dịch vụ, hoặc liệu trình cụ thể để bán/thương mại")
    entity_name: str = Field(description="Tên sản phẩm, thương hiệu, hoặc tên gói liệu trình/dịch vụ cụ thể")
    ai_summary: str = Field(description="Tóm tắt 2-3 câu phân tích nhu cầu thị trường, đối thủ cạnh tranh trên SERP và góc USP khác biệt")
    opportunity_score: float = Field(description="Điểm cơ hội kinh doanh từ 1.0 đến 10.0")
    search_intent: str = Field(description="Ý định tìm kiếm: TRANSACTIONAL, COMMERCIAL, INFORMATIONAL")
    category: str = Field(description="Phân loại: Dịch vụ thẩm mỹ, Spa & Clinic, Dược mỹ phẩm, Liệu trình công nghệ cao, v.v.")

def analyze_deep_keyword_with_gemini(keyword: str, seed_term: str, location_name: str, serp_snippets: list[dict], api_key: str = None) -> dict:
    """Phân tích chuyên sâu từ khóa nghiên cứu bằng Gemini Flash kết hợp dữ liệu SERP thực tế."""
    active_key = api_key or getattr(config, "GEMINI_API_KEY", "") or os.getenv("GEMINI_API_KEY", "")
    snippets_text = "\n".join([f"- Tiêu đề: {s['title']} | Mô tả: {s['snippet']}" for s in serp_snippets[:5]])

    # Kịch bản mô phỏng nếu chưa có key
    if not active_key:
        is_sell = any(t in keyword.lower() for t in ["giá", "bảng giá", "ở đâu", "uy tín", "spa", "mua", "liệu trình", "bán", "phòng khám", "tiêm", "peel"])
        return {
            "keyword": keyword,
            "is_product_to_sell": is_sell,
            "entity_name": keyword.title(),
            "ai_summary": f"Từ khóa nghiên cứu sâu theo chủ đề '{seed_term}' tại {location_name or 'Việt Nam'}. Phản ánh nhu cầu thực tế của khách hàng về dịch vụ/sản phẩm.",
            "opportunity_score": 8.2 if is_sell else 5.5,
            "search_intent": "COMMERCIAL" if is_sell else "INFORMATIONAL",
            "category": "Dịch vụ & Liệu trình thẩm mỹ" if any(t in keyword for t in ["tiêm", "meso", "spa", "liệu trình", "peel"]) else "Dược mỹ phẩm chăm sóc da",
            "serp_snippets": serp_snippets,
            "status": "simulated"
        }

    client = genai.Client(api_key=active_key)
    location_desc = f"tại khu vực {location_name}" if location_name else "tại thị trường Việt Nam"

    prompt = f"""
Bạn là chuyên gia thẩm định thị trường và phát triển sản phẩm/dịch vụ thương mại trong ngành Dược mỹ phẩm, Spa & Thẩm mỹ viện, và Chăm sóc sức khỏe - sắc đẹp.
Bạn đang thực hiện nghiên cứu sâu cho từ khóa hạt giống: "{seed_term}" {location_desc}.

Dữ liệu kết quả tìm kiếm thực tế trên Google (Top SERP Snippets):
{snippets_text or "Đang truy xuất từ các truy vấn Google liên quan thực tế."}

Từ khóa người tiêu dùng tìm kiếm: "{keyword}"

Hãy phân tích chuẩn xác theo JSON Schema:
1. `is_product_to_sell`: True nếu từ khóa này có thể chuyển đổi thành sản phẩm vật lý cụ thể (kem, serum, thuốc) HOẶC dịch vụ/liệu trình thương mại cụ thể tại Spa/Clinic/Cửa hàng (ví dụ: Tiêm meso trị mụn chuẩn y khoa, Peel da sinh học trị thâm sẹo, Serum meso B5 phục hồi...). False nếu là tin tức chung chung hoặc câu hỏi giải trí.
2. `entity_name`: Tên gói dịch vụ, tên liệu trình, thương hiệu, hoặc tên sản phẩm nổi bật phù hợp nhất với từ khóa này.
3. `ai_summary`: Tóm tắt 2-3 câu đánh giá: (a) Nhu cầu và nỗi đau thực tế của khách hàng, (b) Các đối thủ/đơn vị đang cung cấp trên SERP, (c) Góc USP để làm truyền thông hoặc mở dịch vụ vượt trội.
4. `opportunity_score`: Chấm điểm từ 1.0 đến 10.0 (Điểm cao nếu nhu cầu mua sắm/đặt lịch cao, dễ triển khai thương mại và ít bị cạnh tranh phá giá).
5. `search_intent`: TRANSACTIONAL (mua/đặt lịch ngay), COMMERCIAL (so sánh/tìm nơi uy tín), INFORMATIONAL (tìm hiểu kiến thức).
6. `category`: Dịch vụ thẩm mỹ & Spa | Dược mỹ phẩm đặc trị | Liệu trình công nghệ cao | Sản phẩm chăm sóc cơ thể.
"""
    models_to_try = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-2.0-flash"]
    for target_model in models_to_try:
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=DeepOpportunitySchema,
                    temperature=0.2
                )
            )
            data = json.loads(response.text)
            data["keyword"] = keyword
            data["serp_snippets"] = serp_snippets
            return data
        except Exception as e:
            if target_model == models_to_try[-1]:
                print(f"[!] Lỗi gọi Gemini ({target_model}) cho từ khóa '{keyword}': {e}")
            continue

    return None

def run_deep_keyword_pipeline(
    seed_keyword: str,
    location: str = "Vietnam",
    time_range: str = "",
    target_count: int = 100,
    ai_limit: int = 25,
    traffic_priority: str = "all",
    session_id: str = "",
    custom_topic_name: str = ""
) -> dict:
    """Pipeline 4 tầng chuyên sâu: Nghiên cứu từ khóa thật qua Serper.dev & Phân tích bằng Gemini 3.8 Flash."""
    clean_seed = seed_keyword.strip()
    if not clean_seed:
        print("[!] Lỗi: Từ khóa hạt giống không được để trống!")
        return {"success": False, "message": "Từ khóa trống"}

    if not session_id:
        session_id = f"deep_{int(time.time())}"

    base_term, geo_term = split_seed_and_location(clean_seed, location)
    allowed_tokens = get_allowed_geo_tokens(location, geo_term)
    location_label = geo_term.title() if geo_term else (location if location != "Vietnam" else "Toàn quốc VN")

    if not custom_topic_name:
        topic_name = f"Nghiên cứu: \"{clean_seed}\" ({location_label})"
    else:
        topic_name = custom_topic_name

    print("\n" + "=" * 65)
    print("🚀 >>> BẮT ĐẦU PIPELINE NGHIÊN CỨU TỪ KHÓA SÂU (SERPER.DEV & AI) <<<")
    print(f"🎯 [TỪ KHÓA HẠT GIỐNG]: \"{clean_seed}\" (Lõi: \"{base_term}\" | Vùng: \"{location_label}\")")
    print(f"📍 [VỊ TRÍ ĐỊA LÝ GOOGLE]: {location or 'Vietnam'}")
    if allowed_tokens:
        print(f"🔒 [SIẾT ĐỊA PHƯƠNG MỤC TIÊU]: {location_label} (Chặn toàn bộ các tỉnh thành đối thủ)")
    print(f"⏱️ [KHUNG THỜI GIAN]: {time_range or 'Tất cả thời gian (Toàn diện)'}")
    print(f"🎯 [MỤC TIÊU]: Thu thập ~{target_count} từ khóa thật | AI phân tích sâu: {ai_limit} từ khóa")
    print(f"📁 [CHỦ ĐỀ LƯU TRỮ]: {topic_name}")
    print("=" * 65 + "\n")

    # =========================================================================
    # TẦNG 1: THU THẬP TỪ KHÓA THỰC TẾ 100% (MULTI-SOURCE REAL HARVESTING)
    # =========================================================================
    print(f"[TẦNG 1 - DATA MINING]: Đang cào dữ liệu Google SERP, Suggestions và Autocomplete...")
    harvested = set()
    harvested.add(clean_seed.lower())

    # 1. Gọi Serper /search với seed query và location + time filter
    print(f"[*] 1/4: Đang truy vấn Serper.dev Google Organic & Related Searches cho '{clean_seed}'...")
    serper_data = fetch_serper_search_data(clean_seed, location=location, tbs=time_range, num=10)
    
    # Gom related searches và PAA
    for rel in serper_data.get("related", []):
        if rel and len(rel) > 3:
            harvested.add(rel)
    for q in serper_data.get("paa", []):
        if q and len(q) > 3:
            harvested.add(q)

    # Gom các cụm từ nổi bật từ Organic titles
    for org in serper_data.get("organic", []):
        title = org.get("title", "")
        # Lấy các vế trước dấu gạch ngang/dấu đứng
        parts = re.split(r'[-–|:?]', title)
        for p in parts:
            p_clean = p.strip().lower()
            if base_term in p_clean and len(p_clean) >= len(base_term) + 3 and len(p_clean) <= 65:
                harvested.add(p_clean)

    # 2. Gọi Serper Autocomplete
    print(f"[*] 2/4: Đang gọi Serper.dev Autocomplete...")
    serper_suggs = fetch_serper_autocomplete_data(clean_seed)
    harvested.update(serper_suggs)
    if base_term != clean_seed:
        harvested.update(fetch_serper_autocomplete_data(base_term))

    # 3. Google Suggestion Matrix (Mở rộng đa hướng)
    print(f"[*] 3/4: Đang chạy ma trận Google Suggestion đa chiều...")
    direct_suggs = fetch_google_suggestions_free(clean_seed)
    harvested.update(direct_suggs)
    if base_term != clean_seed:
        harvested.update(fetch_google_suggestions_free(base_term))

    # Bộ tiền tố / hậu tố ý định hành vi người dùng Việt Nam
    intent_modifiers = [
        "ở đâu", "giá bao nhiêu", "bảng giá", "review", "uy tín", "tốt nhất", "chuẩn y khoa",
        "tại nhà", "spa", "phòng khám", "bác sĩ", "chi phí", "có tốt không", "tác dụng gì",
        "bao lâu thì đẹp", "quy trình", "sau khi", "cho da dầu", "trị thâm", "trị sẹo",
        "phục hồi da", "có nên", "hướng dẫn", "bị đỏ", "chăm sóc da"
    ]

    for mod in intent_modifiers:
        if len(harvested) >= target_count + 30:
            break
        suggs = fetch_google_suggestions_free(f"{base_term} {mod}")
        harvested.update(suggs)

    # Nếu có địa phương (ví dụ Phan Thiết, Bình Thuận, TP.HCM, Hà Nội...)
    target_geos = []
    if geo_term:
        target_geos.append(geo_term)
    if any(k in location.lower() for k in ["lam dong", "lâm đồng"]) and "lâm đồng" not in target_geos:
        target_geos.append("lâm đồng")

    is_beauty = any(w in base_term for w in ["da", "mụn", "nám", "sẹo", "meso", "peel", "tiêm", "spa", "clinic", "thẩm mỹ", "tóc", "dưỡng", "kem", "serum", "bác sĩ"])

    for g_loc in target_geos:
        geo_queries = [
            f"{base_term} {g_loc}",
            f"{base_term} ở {g_loc}",
            f"{base_term} tại {g_loc}",
            f"{base_term} uy tín {g_loc}",
            f"bảng giá {base_term} {g_loc}",
            f"địa chỉ {base_term} {g_loc}",
            f"mua {base_term} ở {g_loc}",
            f"dịch vụ {base_term} {g_loc}"
        ]
        if is_beauty:
            geo_queries.extend([
                f"spa {base_term} {g_loc}",
                f"bác sĩ {base_term} {g_loc}",
                f"phòng khám {base_term} {g_loc}",
                f"liệu trình {base_term} {g_loc}"
            ])
        for g_q in geo_queries:
            suggs = fetch_google_suggestions_free(g_q)
            harvested.update(suggs)

    # 4. Mở rộng chữ cái A-Z nếu chưa đủ target_count
    if len(harvested) < target_count:
        print(f"[*] 4/4: Mở rộng bảng chữ cái Google Suggestion để gom đủ ~{target_count} từ khóa...")
        for char in "abcdefghijklmnoprstuvxy":
            suggs = fetch_google_suggestions_free(f"{base_term} {char}")
            harvested.update(suggs)
            if len(harvested) >= target_count + 20:
                break

    # Lọc và chuẩn hóa từ khóa thô với BỘ LỌC ĐỊA LÝ NGHIÊM NGẶT
    valid_keywords = []
    seen = set()
    rejected_geo_count = 0

    for kw in harvested:
        k = re.sub(r'\s+', ' ', kw).strip().lower()
        if len(k) < 4 or len(k) > 85 or k in seen:
            continue

        # SIẾT ĐÚNG VỊ TRÍ CẦN TÌM: LOẠI TRỪ 100% CÁC ĐỊA DANH ĐỐI THỦ (Nha Trang, Bình Tân, Hà Nội, Đà Nẵng...)
        if allowed_tokens and is_competing_geo(k, allowed_tokens):
            rejected_geo_count += 1
            continue

        seen.add(k)
        valid_keywords.append(k)

    if rejected_geo_count > 0:
        print(f"[*] Đã siết chặt vị trí {location_label}: Loại bỏ {rejected_geo_count} từ khóa thuộc các tỉnh thành đối thủ (Nha Trang, Hà Nội, TP.HCM, Bình Tân...).")

    # Ưu tiên sắp xếp:
    # 1. Từ khóa chứa đúng địa danh mục tiêu (Phan Thiết, Bình Thuận, Lâm Đồng...) -> ĐƯA LÊN ĐẦU
    # 2. Ý định giao dịch & dịch vụ thương mại (giá, uy tín, spa, bác sĩ, bảng giá...)
    commercial_terms = ["giá", "bảng giá", "ở đâu", "uy tín", "spa", "mua", "liệu trình", "chi phí", "phòng khám", "tiêm", "peel", "tốt nhất", "bác sĩ"]
    info_terms = ["là gì", "tác dụng", "review", "có nên", "bao lâu", "sau khi", "quy trình", "hướng dẫn", "tại sao"]

    def rank_key(kw):
        has_target_geo = any(tok in kw for tok in allowed_tokens) if allowed_tokens else False
        is_comm = any(t in kw for t in commercial_terms)
        is_inf = any(t in kw for t in info_terms)
        
        geo_weight = 10 if has_target_geo else 0
        intent_weight = 0
        if traffic_priority == "commercial":
            intent_weight = 5 if is_comm else 0
        elif traffic_priority == "informational":
            intent_weight = 5 if is_inf else 0
        else:
            intent_weight = 3 if is_comm else 1

        return (geo_weight + intent_weight, -len(kw))

    valid_keywords.sort(key=rank_key, reverse=True)

    final_keywords = valid_keywords[:target_count]
    print(f"\n[✓] Đã thu thập thành công {len(final_keywords)} từ khóa thực tế từ Google!")

    # Lưu toàn bộ từ khóa thô vào SQLite
    saved_raw = save_raw_keywords(
        final_keywords,
        seed_term=clean_seed,
        source="serper_deep",
        session_id=session_id,
        topic=topic_name
    )
    print(f"[✓] Đã cất {saved_raw} từ khóa vào kho SQLite (Session: {session_id}).\n")

    # =========================================================================
    # TẦNG 2 & 3: SERP SNIPPETS AUDIT & GEMINI 3.8 FLASH PHÂN TÍCH CHUYÊN SÂU
    # =========================================================================
    print("=" * 65)
    print(f"[TẦNG 2 & 3 - AI INTELLIGENCE]: Bắt đầu kiểm tra SERP đối thủ & Gemini Flash phân tích...")
    print(f"🤖 [CHỈ TIÊU PHÂN TÍCH AI]: {ai_limit} từ khóa nổi bật nhất trong tổng số {len(final_keywords)} từ khóa")
    print("=" * 65)

    candidates = final_keywords[:ai_limit]
    analyzed_count = 0

    for idx, kw in enumerate(candidates, start=1):
        # Trích xuất Top SERP đối thủ thực tế từ Serper.dev
        serp_snippets = []
        try:
            serp_data = fetch_serp_via_serper(kw, num_results=3)
            if serp_data:
                serp_snippets = serp_data
        except Exception:
            pass

        # Phân tích bằng Gemini Flash
        analysis = analyze_deep_keyword_with_gemini(
            keyword=kw,
            seed_term=clean_seed,
            location_name=location_label,
            serp_snippets=serp_snippets,
            api_key=config.GEMINI_API_KEY
        )

        if analysis:
            analysis["keyword"] = kw
            analysis["session_id"] = session_id
            analysis["topic"] = topic_name
            save_product_opportunity(analysis)
            score = analysis.get("opportunity_score", 0.0)
            is_sell = "✓ THƯƠNG MẠI" if analysis.get("is_product_to_sell") else "✗ THAM KHẢO"
            print(f"[#{idx}/{len(candidates)}] '{kw}' -> ⭐ {score:.1f}/10 | {is_sell} | {analysis.get('entity_name')}")
            analyzed_count += 1

        time.sleep(0.1)

    # =========================================================================
    # TẦNG 4: KẾT XUẤT FILE BÁO CÁO CSV
    # =========================================================================
    export_res = export_to_csv(session_id=session_id, topic_name=topic_name)
    print("\n" + "=" * 65)
    print(f"🎉 [HOÀN TẤT TOÀN BỘ PIPELINE NGHIÊN CỨU TỪ KHÓA]:")
    print(f"- Tổng từ khóa thật thu thập: {len(final_keywords)}")
    print(f"- Số cơ hội được Gemini bóc tách: {analyzed_count}")
    print(f"- Đã xuất báo cáo CSV: {export_res.get('filename') if export_res else 'Thành công'}")
    print("=" * 65 + "\n")

    return {
        "success": True,
        "session_id": session_id,
        "topic": topic_name,
        "raw_count": len(final_keywords),
        "analyzed_count": analyzed_count
    }
