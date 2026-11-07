import sys
import argparse
from pathlib import Path
from database import init_db, get_stats, get_top_opportunities, export_to_csv
from scrapers.seed_generator import harvest_all_raw_keywords
from pipeline.filter_engine import run_pre_filtering
from pipeline.gemini_analyzer import run_gemini_analysis_batch

# Đảm bảo UTF-8 cho Windows Terminal
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

def print_banner():
    print("""
========================================================================
   🌿 DERM & SKIN KEYWORD OPPORTUNITY HUNTER - GEMINI FLASH 🌿
   Pipeline 4 Tầng: Modifier Matrix -> Pre-filter -> Gemini AI -> SQLite
========================================================================
""")

def display_stats():
    stats = get_stats()
    print("\n📊 [BÁO CÁO THỐNG KÊ KHO DỮ LIỆU SQLITE]:")
    print(f"  • Tổng từ khóa thô thu thập:   {stats['total_raw_keywords']}")
    print(f"  • Từ khóa bị loại rác/chuỗi lớn: {stats['filtered_out']}")
    print(f"  • Sản phẩm cơ hội đã phân tích: {stats['analyzed_opportunities']}")
    print(f"  • Cơ hội vàng tiềm năng cao (>=7): {stats['sweet_spot_gems']}")
    print("-" * 60)

def display_top_opportunities(limit=15):
    items = get_top_opportunities(min_score=6.0, limit=limit)
    if not items:
        print("\n[!] Chưa có cơ hội nào đạt điểm >= 6.0 hoặc chưa chạy Tầng 3 (AI).")
        return
        
    print(f"\n💎 [TOP {len(items)} CƠ HỘI SẢN PHẨM TIỀM NĂNG NHẤT (SWEET SPOT)]:\n")
    print(f"{'Điểm':<6} | {'Tên Sản Phẩm / Hoạt Chất':<28} | {'Từ Khóa Tìm Kiếm':<32} | {'Ý Định':<12}")
    print("-" * 85)
    for it in items:
        score = f"{it['opportunity_score']:.1f}/10"
        name = it['entity_name'][:26]
        kw = it['keyword'][:30]
        intent = it['search_intent'][:10]
        print(f"{score:<6} | {name:<28} | {kw:<32} | {intent:<12}")
        print(f"   └─ Tóm tắt AI: {it['ai_summary']}")
        print()

def run_full_pipeline(max_seeds=30, ai_limit=15, api_key=None, custom_prompt=""):
    """Chạy toàn diện 4 tầng của hệ thống."""
    print("\n>>> BẮT ĐẦU CHẠY PIPELINE 4 TẦNG TỰ ĐỘNG <<<\n")
    if custom_prompt:
        print(f"🎯 [PROMPT ĐỊNH HƯỚNG]: {custom_prompt}\n")
    # Tầng 1
    harvest_all_raw_keywords(max_seeds=max_seeds, custom_prompt=custom_prompt, api_key=api_key)
    # Tầng 2
    run_pre_filtering()
    # Tầng 3
    run_gemini_analysis_batch(limit=ai_limit, api_key=api_key, custom_prompt=custom_prompt)
    # Tầng 4
    display_stats()
    display_top_opportunities(limit=10)
    csv_file = export_to_csv()
    print(f"\n[✓] Đã xuất file báo cáo đầy đủ: {csv_file}")

def main():
    parser = argparse.ArgumentParser(description="Derm Keyword Opportunity Hunter with Gemini Flash")
    parser.add_argument("--all", action="store_true", help="Chạy toàn bộ pipeline từ Tầng 1 -> Tầng 4")
    parser.add_argument("--harvest", action="store_true", help="Chỉ chạy Tầng 1: Thu thập từ khóa thô")
    parser.add_argument("--filter", action="store_true", help="Chỉ chạy Tầng 2: Lọc rác & blacklist")
    parser.add_argument("--ai", action="store_true", help="Chỉ chạy Tầng 3: AI Gemini phân tích")
    parser.add_argument("--top", action="store_true", help="Xem danh sách Top cơ hội sản phẩm")
    parser.add_argument("--export", action="store_true", help="Xuất báo cáo ra file CSV")
    parser.add_argument("--stats", action="store_true", help="Xem thống kê database")
    parser.add_argument("--api-key", type=str, default="", help="Cung cấp Gemini API Key")
    parser.add_argument("--prompt", type=str, default="", help="Định hướng bằng ngôn ngữ tự nhiên (Custom Prompt)")
    parser.add_argument("--seeds", type=int, default=25, help="Số lượng hạt giống ma trận quét")
    parser.add_argument("--limit", type=int, default=15, help="Số lượng từ khóa phân tích AI")
    
    args = parser.parse_args()
    
    # Khởi tạo SQLite DB nếu chưa có
    init_db()
    
    print_banner()
    
    # Nếu có flags
    if args.all:
        run_full_pipeline(max_seeds=args.seeds, ai_limit=args.limit, api_key=args.api_key, custom_prompt=args.prompt)
        return
    elif args.harvest:
        harvest_all_raw_keywords(max_seeds=args.seeds, custom_prompt=args.prompt, api_key=args.api_key)
        return
    elif args.filter:
        run_pre_filtering()
        return
    elif args.ai:
        run_gemini_analysis_batch(limit=args.limit, api_key=args.api_key, custom_prompt=args.prompt)
        return
    elif args.top:
        display_top_opportunities()
        return
    elif args.export:
        path = export_to_csv()
        print(f"[✓] Đã xuất file thành công: {path}")
        return
    elif args.stats:
        display_stats()
        return

    # Giao diện dòng lệnh tương tác Menu nếu không truyền flag
    while True:
        display_stats()
        print("LỰA CHỌN THAO TÁC:")
        print("  1. Chạy TOÀN BỘ Pipeline 4 Tầng tự động (Khuyên dùng)")
        print("  2. Tầng 1: Thu thập từ khóa thô (Data Ingestion)")
        print("  3. Tầng 2: Lọc rác & Brand lớn (Pre-filtering)")
        print("  4. Tầng 3: Gemini AI phân tích cơ hội sản phẩm")
        print("  5. Xem Top cơ hội sản phẩm tiềm năng (Sweet Spot)")
        print("  6. Xuất báo cáo ra file CSV / Excel")
        print("  0. Thoát")
        
        choice = input("\nNhập số lựa chọn của bạn (0-6): ").strip()
        if choice == "1":
            run_full_pipeline()
        elif choice == "2":
            harvest_all_raw_keywords()
        elif choice == "3":
            run_pre_filtering()
        elif choice == "4":
            api_input = input("Nhập Gemini API Key (hoặc nhấn Enter để dùng mặc định/dry-run): ").strip()
            run_gemini_analysis_batch(api_key=api_input or None)
        elif choice == "5":
            display_top_opportunities()
        elif choice == "6":
            path = export_to_csv()
            print(f"[✓] File CSV đã được lưu tại: {path}")
        elif choice == "0":
            print("Tạm biệt!")
            break
        else:
            print("[!] Lựa chọn không hợp lệ, vui lòng thử lại.")
        input("\nNhấn Enter để tiếp tục...")

if __name__ == "__main__":
    main()
