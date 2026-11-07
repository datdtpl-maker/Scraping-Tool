import sqlite3
import json
import csv
import re
import datetime
from pathlib import Path
from config import DATABASE_PATH, BASE_DIR

def get_connection():
    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
    except Exception:
        pass
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Bảng 1: Lưu trữ từ khóa thô thu thập được từ các nguồn (Google Suggest, Scraper...)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS raw_keywords (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT UNIQUE NOT NULL,
        seed_term TEXT,
        source TEXT DEFAULT 'google_suggest',
        session_id TEXT,
        topic TEXT,
        is_filtered INTEGER DEFAULT 0,
        filter_reason TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Bảng 2: product_opportunities - Lưu trữ cơ hội sản phẩm sau khi AI Gemini phân tích
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS product_opportunities (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT UNIQUE NOT NULL,
        search_volume INTEGER DEFAULT 1000,
        competition_level TEXT DEFAULT 'LOW',
        is_product_to_sell INTEGER DEFAULT 1,
        entity_name TEXT,
        ai_summary TEXT,
        opportunity_score REAL DEFAULT 0.0,
        search_intent TEXT DEFAULT 'COMMERCIAL',
        category TEXT DEFAULT 'Da cơ thể & Da liễu',
        serp_snippets TEXT,
        session_id TEXT,
        topic TEXT,
        status TEXT DEFAULT 'analyzed',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # Migration an toàn nếu bảng cũ chưa có cột session_id, topic
    try:
        cursor.execute("PRAGMA table_info(raw_keywords)")
        raw_cols = [c[1] for c in cursor.fetchall()]
        if "session_id" not in raw_cols:
            cursor.execute("ALTER TABLE raw_keywords ADD COLUMN session_id TEXT;")
        if "topic" not in raw_cols:
            cursor.execute("ALTER TABLE raw_keywords ADD COLUMN topic TEXT;")
            
        cursor.execute("PRAGMA table_info(product_opportunities)")
        opp_cols = [c[1] for c in cursor.fetchall()]
        if "session_id" not in opp_cols:
            cursor.execute("ALTER TABLE product_opportunities ADD COLUMN session_id TEXT;")
        if "topic" not in opp_cols:
            cursor.execute("ALTER TABLE product_opportunities ADD COLUMN topic TEXT;")
    except Exception:
        pass
    
    # Index để truy vấn siêu nhanh
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_keyword ON raw_keywords(keyword);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_session ON raw_keywords(session_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_raw_filtered ON raw_keywords(is_filtered);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_opp_score ON product_opportunities(opportunity_score DESC);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_opp_session ON product_opportunities(session_id);")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_opp_keyword ON product_opportunities(keyword);")
    
    conn.commit()
    conn.close()

def save_raw_keywords(keyword_list, seed_term="", source="google_suggest", session_id="", topic=""):
    """Lưu từ khóa thô, nếu từ khóa đã tồn tại thì cập nhật session_id và topic hiện tại."""
    conn = get_connection()
    cursor = conn.cursor()
    inserted_count = 0
    for kw in keyword_list:
        kw_clean = kw.strip().lower()
        if not kw_clean:
            continue
        try:
            cursor.execute("""
                INSERT INTO raw_keywords (keyword, seed_term, source, session_id, topic)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(keyword) DO UPDATE SET
                    session_id = excluded.session_id,
                    topic = excluded.topic
            """, (kw_clean, seed_term, source, session_id, topic))
            if cursor.rowcount > 0:
                inserted_count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return inserted_count

def mark_keyword_filtered(keyword, reason):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE raw_keywords SET is_filtered = 1, filter_reason = ? WHERE keyword = ?",
        (reason, keyword.lower().strip())
    )
    conn.commit()
    conn.close()

def get_unfiltered_raw_keywords(limit=50, session_id=""):
    """Lấy danh sách từ khóa chưa qua Tầng 3 đa dạng mọi nhóm sản phẩm (Round-Robin, không dồn cục vào 1 hạt giống)."""
    conn = get_connection()
    cursor = conn.cursor()
    
    if session_id:
        cursor.execute("""
            SELECT r.id, r.keyword, r.seed_term, r.session_id, r.topic 
            FROM raw_keywords r
            LEFT JOIN product_opportunities p ON r.keyword = p.keyword AND p.session_id = ?
            WHERE r.is_filtered = 0 AND r.session_id = ? AND (p.id IS NULL OR p.opportunity_score = 0)
            ORDER BY RANDOM()
        """, (session_id, session_id))
    else:
        cursor.execute("""
            SELECT r.id, r.keyword, r.seed_term, r.session_id, r.topic 
            FROM raw_keywords r
            LEFT JOIN product_opportunities p ON r.keyword = p.keyword
            WHERE r.is_filtered = 0 AND p.id IS NULL
            ORDER BY RANDOM()
        """)
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        return []

    # Phân bổ Round-Robin theo từng seed_term để mỗi ngành hàng/sản phẩm đều có đại diện
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        s_term = r["seed_term"] or "general"
        groups[s_term].append(dict(r))

    selected = []
    while len(selected) < limit and any(groups.values()):
        for s_term in list(groups.keys()):
            if groups[s_term]:
                selected.append(groups[s_term].pop(0))
                if len(selected) >= limit:
                    break
            else:
                del groups[s_term]

    return selected

def save_product_opportunity(data: dict):
    kw = (data.get("keyword", "") or "").lower().strip()
    if not kw:
        return
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO product_opportunities (
            keyword,
            search_volume,
            competition_level,
            is_product_to_sell,
            entity_name,
            ai_summary,
            opportunity_score,
            search_intent,
            category,
            serp_snippets,
            session_id,
            topic,
            status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        kw,
        data.get("search_volume", 1000),
        data.get("competition_level", "LOW"),
        1 if data.get("is_product_to_sell", True) else 0,
        data.get("entity_name", ""),
        data.get("ai_summary", ""),
        float(data.get("opportunity_score", 0.0)),
        data.get("search_intent", "COMMERCIAL"),
        data.get("category", "Da cơ thể & Da liễu"),
        json.dumps(data.get("serp_snippets", []), ensure_ascii=False),
        data.get("session_id", ""),
        data.get("topic", ""),
        data.get("status", "analyzed")
    ))
    conn.commit()
    conn.close()

def get_all_topics():
    """Lấy danh sách tất cả các chủ đề / đợt quét đã từng thực hiện."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            COALESCE(session_id, 'legacy') as session_id,
            COALESCE(NULLIF(topic, ''), 'Mặc định (Chung)') as topic_name,
            COUNT(*) as total_items,
            SUM(CASE WHEN opportunity_score >= 7.0 THEN 1 ELSE 0 END) as gems_count,
            MAX(created_at) as last_updated
        FROM product_opportunities
        GROUP BY COALESCE(session_id, 'legacy')
        ORDER BY last_updated DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def delete_session(session_id: str):
    """Xóa toàn bộ từ khóa và cơ hội thuộc về một đợt quét cụ thể."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM product_opportunities WHERE session_id = ?;", (session_id,))
    cursor.execute("DELETE FROM raw_keywords WHERE session_id = ?;", (session_id,))
    conn.commit()
    conn.close()
    return True

def rename_topic(session_id: str, new_name: str) -> bool:
    """Đổi tên hiển thị của một chủ đề/đợt quét trong SQLite."""
    if not session_id or not new_name.strip():
        return False
    clean_name = new_name.strip()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE product_opportunities SET topic = ? WHERE session_id = ?;", (clean_name, session_id))
    cursor.execute("UPDATE raw_keywords SET topic = ? WHERE session_id = ?;", (clean_name, session_id))
    conn.commit()
    conn.close()
    return True

def get_top_opportunities(min_score=6.0, limit=50, session_id=None, search_query="", search_intent=""):
    """Lấy danh sách cơ hội, lọc chính xác theo session_id, từ khóa tìm kiếm và ý định tìm kiếm."""
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT keyword, entity_name, opportunity_score, search_intent, category, ai_summary, is_product_to_sell, session_id, topic, created_at
        FROM product_opportunities
        WHERE opportunity_score >= ?
    """
    params = [min_score]
    if session_id and session_id != "all":
        query += " AND session_id = ?"
        params.append(session_id)
    if search_intent and search_intent != "all":
        query += " AND UPPER(search_intent) = ?"
        params.append(search_intent.upper())
    if search_query:
        query += " AND (keyword LIKE ? OR entity_name LIKE ? OR ai_summary LIKE ?)"
        term = f"%{search_query}%"
        params.extend([term, term, term])
    query += " ORDER BY opportunity_score DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats(session_id=None):
    """Lấy thống kê. Nếu có session_id thì thống kê riêng cho session đó, ngược lại toàn cục."""
    conn = get_connection()
    cursor = conn.cursor()
    if session_id and session_id != "all":
        cursor.execute("SELECT COUNT(*) FROM raw_keywords WHERE session_id = ?", (session_id,))
        total_raw = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM raw_keywords WHERE session_id = ? AND is_filtered = 1", (session_id,))
        filtered_raw = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM product_opportunities WHERE session_id = ?", (session_id,))
        total_opportunities = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM product_opportunities WHERE session_id = ? AND is_product_to_sell = 1 AND opportunity_score >= 7.0", (session_id,))
        sweet_spot_count = cursor.fetchone()[0]
    else:
        cursor.execute("SELECT COUNT(*) FROM raw_keywords")
        total_raw = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM raw_keywords WHERE is_filtered = 1")
        filtered_raw = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM product_opportunities")
        total_opportunities = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM product_opportunities WHERE is_product_to_sell = 1 AND opportunity_score >= 7.0")
        sweet_spot_count = cursor.fetchone()[0]
        
    conn.close()
    return {
        "total_raw_keywords": total_raw,
        "filtered_out": filtered_raw,
        "analyzed_opportunities": total_opportunities,
        "sweet_spot_gems": sweet_spot_count
    }

def export_to_csv(session_id=None, topic_name=None, export_dir=None):
    """Xuất file CSV ra thư mục rõ ràng, trả về đường dẫn tuyệt đối, thư mục và số lượng bản ghi."""
    if not export_dir:
        export_dir = Path(BASE_DIR) / "Bao_Cao_Xuat"
    else:
        export_dir = Path(export_dir)
        
    export_dir.mkdir(parents=True, exist_ok=True)
    
    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_topic = "Tat_Ca"
    if topic_name and topic_name.strip():
        clean_topic = re.sub(r'[^\w\s-]', '', topic_name).strip().replace(' ', '_')[:30]
        
    filename = f"Bao_Cao_Co_Hoi_{clean_topic}_{now_str}.csv"
    full_path = export_dir / filename
    
    conn = get_connection()
    cursor = conn.cursor()
    
    if session_id and session_id != "all":
        cursor.execute("""
            SELECT keyword, entity_name, opportunity_score, search_intent, category, is_product_to_sell, topic, ai_summary, created_at
            FROM product_opportunities
            WHERE session_id = ?
            ORDER BY opportunity_score DESC
        """, (session_id,))
    else:
        cursor.execute("""
            SELECT keyword, entity_name, opportunity_score, search_intent, category, is_product_to_sell, topic, ai_summary, created_at
            FROM product_opportunities
            ORDER BY opportunity_score DESC
        """)
        
    rows = cursor.fetchall()
    conn.close()
    
    with open(full_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["Từ Khóa", "Tên Sản Phẩm / Hoạt Chất", "Điểm Cơ Hội (1-10)", "Ý Định Tìm Kiếm", "Danh Mục", "Là Sản Phẩm Bán Được", "Chủ Đề / Đợt Quét", "AI Tóm Tắt Công Dụng", "Ngày Phân Tích"])
        for r in rows:
            writer.writerow([
                r["keyword"],
                r["entity_name"],
                r["opportunity_score"],
                r["search_intent"],
                r["category"],
                "Có" if r["is_product_to_sell"] == 1 else "Không",
                r["topic"] or "Chung",
                r["ai_summary"],
                r["created_at"]
            ])
            
    return {
        "filepath": str(full_path.resolve()),
        "folder": str(export_dir.resolve()),
        "filename": filename,
        "count": len(rows)
    }
