# Derm & Skin Keyword Opportunity Hunter (Gemini Flash & SQLite)

Hệ thống tự động "Đãi vàng từ khóa" 4 tầng cho ngành hàng **Da cơ thể người, Dược mỹ phẩm và Thuốc da liễu**, sử dụng mô hình **Gemini 2.5 Flash / 3.8 Flash** và cơ sở dữ liệu **SQLite** lưu cục bộ trên máy tính.

---

## 🏛️ Kiến Trúc Hệ Thống (4 Tầng Pipeline)

```
[Khoang 1: Cái Vớt]           [Khoang 2: Cái Lọc]           [Khoang 3: AI Gemini Flash]        [Khoang 4: Cất Kho]
Thu thập từ khóa thô    --->   Lọc rác & Blacklist   --->   SERP Top 5 & JSON Schema    --->   SQLite Local DB
(Modifier Matrix + Suggest)    (Volume / Bỏ Brand lớn)       (is_product_to_sell, score)       (product_opportunities)
```

1. **Tầng 1 (Data Ingestion):**
   - Sinh tập hợp ma trận Modifier Matrix: `[Định dạng SP] + [Bệnh lý/Vấn đề da body] + [Ý định mua sắm]`.
   - Kết hợp thu thập từ khóa thời gian thực từ Google Suggest/Autocomplete và cào danh mục thuốc & dược mỹ phẩm chuyên ngành.
2. **Tầng 2 (Pre-filtering):**
   - Loại bỏ rác, query quá ngắn hoặc quá dài.
   - Loại bỏ các từ khóa chứa chuỗi bán lẻ lớn (Hasaki, Long Châu, Pharmacity, Tiki, Shopee, Amazon...) để tránh đối đầu trực diện.
3. **Tầng 3 (Enrichment & AI Intelligence):**
   - Lấy Top 5 kết quả Google SERP (hỗ trợ Serper.dev API hoặc chế độ Grounding).
   - Đẩy vào mô hình **Gemini Flash** với cấu trúc dữ liệu chặt chẽ (JSON Schema / Pydantic):
     - `entity_name`: Tên sản phẩm, thương hiệu hoặc hoạt chất thực tế.
     - `is_product_to_sell`: Xác nhận có phải sản phẩm vật lý thương mại để bán không.
     - `ai_summary`: Tóm tắt công dụng, đối tượng khách hàng mục tiêu.
     - `opportunity_score`: Điểm cơ hội từ 1.0 đến 10.0.
     - `search_intent`: TRANSACTIONAL, COMMERCIAL, INFORMATIONAL.
4. **Tầng 4 (Storage & Reporting):**
   - Lưu trữ trực tiếp tại file SQLite local: `product_opportunities.db`.
   - Hỗ trợ xuất dữ liệu ra file CSV/Excel `opportunities_report.csv` để chọn sản phẩm bán hàng.

---

## 🚀 Hướng Dẫn Sử Dụng

### 1. Cài đặt môi trường
Dự án chạy trên Python 3.10+ (Đã cài sẵn `google-genai`, `requests`, `pydantic`, `beautifulsoup4`, `sqlite3`).

### 2. Thiết lập API Key
Tạo file `.env` hoặc truyền biến môi trường:
```bash
set GEMINI_API_KEY=AIzaSy...
```
*(Nếu chưa có API Key, hệ thống vẫn hỗ trợ chạy chế độ Heuristic Dry-Run để kiểm tra toàn bộ luồng).*

### 3. Lệnh chạy nhanh

* **Chạy toàn bộ pipeline tự động (Khuyên dùng):**
  ```powershell
  python main.py --all
  ```

* **Chạy từng tầng độc lập:**
  ```powershell
  python main.py --harvest   # Tầng 1: Thu thập từ khóa
  python main.py --filter    # Tầng 2: Lọc rác & Brand lớn
  python main.py --ai        # Tầng 3: Gemini Flash phân tích
  ```

* **Xem Top cơ hội tiềm năng & Xuất báo cáo:**
  ```powershell
  python main.py --top       # Xem Top sản phẩm điểm cao
  python main.py --export    # Xuất file CSV
  python main.py --stats     # Xem thống kê database
  ```
