import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Thư mục gốc dự án: nếu đóng gói PyInstaller thì lấy thư mục chứa file .exe
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

ENV_PATH = BASE_DIR / ".env"

# Thư mục lưu cấu hình vĩnh viễn trong User AppData (không bao giờ bị xóa khi cài đè hoặc cập nhật app)
APPDATA_DIR = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming"))) / "DermKeywordHunter"
APPDATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_JSON = APPDATA_DIR / "settings.json"

# Nạp file settings.json từ AppData nếu có
appdata_settings = {}
if SETTINGS_JSON.exists():
    try:
        with open(SETTINGS_JSON, "r", encoding="utf-8") as f:
            appdata_settings = json.load(f)
    except Exception:
        appdata_settings = {}

# Nạp file .env nếu có
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=True)

# Đường dẫn Database SQLite
DATABASE_PATH = appdata_settings.get("db_path") or os.getenv("DATABASE_PATH", str(BASE_DIR / "product_opportunities.db"))

# Gemini API Configuration
GEMINI_API_KEY = appdata_settings.get("gemini_key") or os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = appdata_settings.get("gemini_model") or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Serper.dev API Configuration (Top 5 Google SERP & Thẩm định đối thủ)
SERPER_API_KEY = appdata_settings.get("serper_key") or os.getenv("SERPER_API_KEY", "")

def save_env_config(gemini_key=None, gemini_model=None, serper_key=None):
    """Lưu cài đặt vĩnh viễn vào User AppData và file .env, cập nhật biến môi trường."""
    global GEMINI_API_KEY, GEMINI_MODEL, SERPER_API_KEY, appdata_settings
    
    # 1. Cập nhật dictionary AppData
    if gemini_key is not None:
        GEMINI_API_KEY = gemini_key.strip()
        appdata_settings["gemini_key"] = GEMINI_API_KEY
        os.environ["GEMINI_API_KEY"] = GEMINI_API_KEY

    if gemini_model is not None:
        GEMINI_MODEL = gemini_model.strip()
        appdata_settings["gemini_model"] = GEMINI_MODEL
        os.environ["GEMINI_MODEL"] = GEMINI_MODEL

    if serper_key is not None:
        SERPER_API_KEY = serper_key.strip()
        appdata_settings["serper_key"] = SERPER_API_KEY
        os.environ["SERPER_API_KEY"] = SERPER_API_KEY

    # Ghi vào file settings.json (bền vững qua các lần cập nhật app)
    try:
        with open(SETTINGS_JSON, "w", encoding="utf-8") as f:
            json.dump(appdata_settings, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[!] Lỗi ghi {SETTINGS_JSON}: {e}")

    # 2. Đồng bộ song song vào file .env ở thư mục ứng dụng
    current_lines = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    current_lines[k.strip()] = v.strip()
                    
    current_lines["GEMINI_API_KEY"] = GEMINI_API_KEY
    current_lines["GEMINI_MODEL"] = GEMINI_MODEL
    current_lines["SERPER_API_KEY"] = SERPER_API_KEY

    try:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write("# Tự động đồng bộ bởi Derm Keyword Hunter Pro\n")
            for k, v in current_lines.items():
                f.write(f"{k}={v}\n")
    except Exception:
        pass
            
    return True

# Danh sách Brand / Chuỗi bán lẻ lớn cần loại bỏ (Blacklist) để tránh cạnh tranh trực diện
BLACKLIST_RETAILERS = [
    "hasaki",
    "long châu",
    "long chau",
    "nhathuoclongchau",
    "pharmacity",
    "an khang",
    "nhathuocankhang",
    "tiki",
    "shopee",
    "lazada",
    "amazon",
    "watsons",
    "guardian",
    "thegioiskinfood",
    "bachhoaxanh",
    "vinmart",
    "winmart"
]

# TẦNG 1: MA TRẬN TỪ KHÓA (MODIFIER MATRIX) CHO DA CƠ THỂ, MỸ PHẨM, THUỐC DA LIỄU
PRODUCT_FORMATS = [
    "kem bôi",
    "serum",
    "viên uống",
    "sữa tắm",
    "gel tắm",
    "lotion",
    "kem dưỡng thể",
    "thuốc mỡ",
    "dung dịch xịt",
    "xà phòng",
    "xà bông",
    "tẩy tế bào chết body",
    "tinh dầu",
    "cao bôi"
]

SKIN_CONCERNS = [
    "viêm nang lông",
    "mụn lưng",
    "mụn mông",
    "viêm da cơ địa",
    "chàm da",
    "eczema",
    "vảy nến",
    "nấm da",
    "lang ben",
    "hắc lào",
    "ghẻ nước",
    "dày sừng nang lông",
    "da rắn",
    "khô da nứt nẻ",
    "thâm mông",
    "thâm nách",
    "thâm đầu gối",
    "thâm cùi chỏ",
    "rạn da body",
    "ngứa da body",
    "viêm lỗ chân lông",
    "trắng da body"
]

COMMERCIAL_INTENTS = [
    "giá bao nhiêu",
    "mua ở đâu",
    "review",
    "chính hãng",
    "trị dứt điểm",
    "tốt nhất hiện nay",
    "loại nào tốt",
    "cách dùng",
    "hiệu quả không",
    "có tốt không"
]
