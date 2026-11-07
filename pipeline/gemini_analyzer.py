import os
import json
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL
from pipeline.serp_fetcher import get_serp_snippets
from database import save_product_opportunity, get_unfiltered_raw_keywords

class ProductOpportunitySchema(BaseModel):
    keyword: str = Field(description="Từ khóa gốc đang phân tích")
    is_product_to_sell: bool = Field(description="True nếu đây là một sản phẩm vật lý thương mại có thể mua bán được")
    entity_name: str = Field(description="Tên sản phẩm cụ thể, thương hiệu, hoạt chất hoặc công nghệ thực tế")
    ai_summary: str = Field(description="Tóm tắt công dụng sản phẩm, đối tượng khách hàng mục tiêu và vấn đề được giải quyết")
    opportunity_score: float = Field(description="Điểm tiềm năng cơ hội từ 1.0 đến 10.0")
    search_intent: str = Field(description="Ý định tìm kiếm: TRANSACTIONAL, COMMERCIAL, INFORMATIONAL")
    category: str = Field(description="Phân loại ngành hàng phù hợp")

def analyze_keyword_with_gemini(keyword: str, api_key: str = None, custom_prompt: str = "", topic_mode: str = "topic_1") -> dict:
    """TẦNG 3: Dùng mô hình Gemini Flash phân tích bóc tách cơ hội sản phẩm theo từng Ngành Hàng."""
    active_key = api_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    snippets = get_serp_snippets(keyword)
    snippets_text = "\n".join([f"- Tiêu đề: {s['title']} | Mô tả: {s['snippet']}" for s in snippets])
    
    # Kịch bản khi chưa có API Key: Giả lập phân tích chuẩn Schema để test pipeline
    if not active_key:
        if topic_mode == "topic_2":
            is_sellable = any(term in keyword.lower() for term in ["nồi", "máy", "bếp", "robot", "quạt", "lò", "ấm", "bàn ủi", "bàn là", "hút bụi"])
            return {
                "keyword": keyword,
                "is_product_to_sell": is_sellable,
                "entity_name": keyword.title(),
                "ai_summary": f"Thiết bị điện tử gia dụng liên quan đến: {keyword}. Giải pháp gia đình tiện ích thông minh.",
                "opportunity_score": 8.0 if is_sellable else 4.0,
                "search_intent": "COMMERCIAL" if is_sellable else "INFORMATIONAL",
                "category": "Thiết bị nhà bếp" if any(t in keyword for t in ["nồi", "bếp", "lò", "ấm", "ép", "xay"]) else "Gia dụng làm sạch & nhà cửa",
                "serp_snippets": snippets,
                "status": "simulated_need_api_key"
            }
        else:
            is_sellable = any(term in keyword.lower() for term in ["kem", "serum", "thuốc", "sữa tắm", "gel", "lotion", "xà phòng", "viên uống"])
            return {
                "keyword": keyword,
                "is_product_to_sell": is_sellable,
                "entity_name": keyword.title(),
                "ai_summary": f"Sản phẩm chăm sóc/điều trị da liên quan đến: {keyword}. Phục vụ khách hàng có vấn đề về da liễu hoặc chăm sóc cơ thể.",
                "opportunity_score": 8.0 if is_sellable else 4.0,
                "search_intent": "COMMERCIAL" if is_sellable else "INFORMATIONAL",
                "category": "Thuốc da liễu" if "thuốc" in keyword else ("Da cơ thể" if "sữa tắm" in keyword or "body" in keyword else "Dược mỹ phẩm"),
                "serp_snippets": snippets,
                "status": "simulated_need_api_key"
            }
        
    client = genai.Client(api_key=active_key)
    
    custom_instruction = ""
    if custom_prompt.strip():
        custom_instruction = f"""
ĐẶC BIỆT CHÚ Ý ĐỊNH HƯỚNG TỪ NGƯỜI DÙNG:
"{custom_prompt.strip()}"
"""

    if topic_mode == "topic_2":
        prompt = f"""
Bạn là chuyên gia phân tích thị trường ngành Đồ Điện Tử Gia Dụng, Thiết Bị Nhà Bếp và Gia Dụng Thông Minh.
Nhiệm vụ của bạn là phân tích từ khóa tìm kiếm của người tiêu dùng và các kết quả SERP trên Google để xác định cơ hội kinh doanh sản phẩm vật lý ngành gia dụng/điện tử.
{custom_instruction}
Từ khóa người dùng tìm kiếm: "{keyword}"

Dữ liệu kết quả Google (SERP):
{snippets_text}

Hãy đánh giá và trích xuất thông tin theo đúng JSON Schema:
1. `is_product_to_sell`: True nếu là thiết bị/đồ gia dụng vật lý cụ thể để bán (ví dụ: nồi chiên, robot hút bụi, máy ép chậm, bàn ủi hơi nước, máy sấy tóc, máy lọc không khí...).
2. `entity_name`: Tên thiết bị, dòng sản phẩm, thương hiệu hoặc công nghệ nổi bật (ví dụ: Nồi chiên không dầu hơi nước 8L, Robot hút bụi tự giặt giẻ, Máy sấy tóc ion âm tốc độ cao...).
3. `ai_summary`: Tóm tắt 2-3 câu ngắn gọn về tính năng công nghệ, giải pháp tiện ích cho gia đình và góc USP cạnh tranh.
4. `opportunity_score`: Chấm điểm từ 1.0 đến 10.0 (Điểm cao nếu nhu cầu tìm mua cao, tiện ích thiết thực và có tiềm năng bán tốt).
5. `search_intent`: TRANSACTIONAL, COMMERCIAL, hoặc INFORMATIONAL.
6. `category`: Thiết bị nhà bếp | Gia dụng làm sạch & nhà cửa | Điện tử cá nhân & gia đình.
"""
    else:
        prompt = f"""
Bạn là chuyên gia phân tích thị trường Dược mỹ phẩm, Sản phẩm Da liễu và Chăm sóc da cơ thể (Body skin).
Nhiệm vụ của bạn là phân tích từ khóa tìm kiếm của người dùng và các kết quả SERP trên Google để xác định cơ hội kinh doanh sản phẩm vật lý.
{custom_instruction}
Từ khóa người dùng tìm kiếm: "{keyword}"

Dữ liệu kết quả Google (SERP):
{snippets_text}

Hãy đánh giá và trích xuất thông tin theo đúng JSON Schema:
1. `is_product_to_sell`: Có phải sản phẩm vật lý cụ thể để bán không? (Nếu chỉ là bệnh lý trừu tượng hoặc tin tức chung chung thì False).
2. `entity_name`: Tên thương hiệu, tên thương mại hoặc hoạt chất chính (ví dụ: Urea 10%, Zaraporo Rohto, Acid Fusidic, Klenzit C, Cerave SA...).
3. `ai_summary`: Tóm tắt 2-3 câu ngắn gọn về công dụng, đối tượng sử dụng và hiệu quả giải quyết vấn đề da.
4. `opportunity_score`: Chấm điểm từ 1.0 đến 10.0 (Điểm cao nếu có nhu cầu mua sắm thực tế, sản phẩm ngách ít đối thủ lớn và khớp định hướng).
5. `search_intent`: TRANSACTIONAL, COMMERCIAL, hoặc INFORMATIONAL.
6. `category`: Da cơ thể | Dược mỹ phẩm | Thuốc da liễu.
"""

    models_to_try = [GEMINI_MODEL]
    if GEMINI_MODEL != "gemini-2.5-flash":
        models_to_try.append("gemini-2.5-flash")
    if "gemini-2.0-flash" not in models_to_try:
        models_to_try.append("gemini-2.0-flash")

    for target_model in models_to_try:
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ProductOpportunitySchema,
                    temperature=0.2
                )
            )
            data = json.loads(response.text)
            data["serp_snippets"] = snippets
            return data
        except Exception as e:
            if target_model == models_to_try[-1]:
                print(f"[!] Lỗi khi gọi Gemini API ({target_model}) cho từ khóa '{keyword}': {e}")
            continue
    return None

def run_gemini_analysis_batch(limit=20, api_key: str = None, custom_prompt: str = "", topic_mode: str = "topic_1", session_id: str = "", topic: str = "") -> int:
    """TẦNG 3: Chạy phân tích AI cho các từ khóa đã vượt qua vòng lọc Tầng 2 theo từng Ngành Hàng."""
    print("=" * 60)
    print("🤖 [TẦNG 3 - AI INTELLIGENCE]: GEMINI FLASH PHÂN TÍCH CƠ HỘI SẢN PHẨM...")
    print(f"🏷️ [NGÀNH HÀNG]: {'Chủ đề 2: Đồ Điện Tử Gia Dụng' if topic_mode == 'topic_2' else 'Chủ đề 1: Da Liễu & Dược Mỹ Phẩm'}")
    if topic:
        print(f"📁 [CHỦ ĐỀ ĐỢT QUÉT]: {topic}")
    print("=" * 60)
    
    active_key = api_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY")
    if not active_key:
        print("⚠️ [CHÚ Ý]: Chưa tìm thấy GEMINI_API_KEY. Đang chạy ở chế độ KIỂM THỬ HEURISTIC (Dry-Run).")
    else:
        print(f"[*] Sử dụng Gemini Model: {GEMINI_MODEL} với API Key đã cung cấp.")
        
    candidates = get_unfiltered_raw_keywords(limit=limit, session_id=session_id)
    if not candidates:
        print("[!] Không có từ khóa mới cần phân tích. Hãy chạy Tầng 1 và Tầng 2 trước.")
        return 0
        
    print(f"[*] Bắt đầu phân tích batch {len(candidates)} từ khóa thuộc chủ đề này...")
    analyzed_count = 0
    
    for idx, item in enumerate(candidates, start=1):
        kw = item["keyword"]
        result = analyze_keyword_with_gemini(kw, api_key=active_key, custom_prompt=custom_prompt, topic_mode=topic_mode)
        if result:
            result["session_id"] = session_id or item.get("session_id", "")
            result["topic"] = topic or item.get("topic", "")
            save_product_opportunity(result)
            score = result.get("opportunity_score", 0)
            is_sell = "✓ BÁN ĐƯỢC" if result.get("is_product_to_sell") else "✗ KHÔNG BÁN"
            print(f"[{idx}/{len(candidates)}] '{kw}' -> Score: {score}/10 | {is_sell} | {result.get('entity_name')}")
            analyzed_count += 1
            
    print(f"\n[✓] Hoàn thành phân tích Tầng 3! Đã cất {analyzed_count} cơ hội vào SQLite.")
    return analyzed_count
