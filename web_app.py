import sqlite3
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-in-production'  # 用於 flash 訊息

# 資料庫路徑
DB_PATH = Path(__file__).parent / "questions.db"

# 上傳檔案設定
UPLOAD_FOLDER = Path(__file__).parent / "uploads"
ALLOWED_EXTENSIONS = {'txt'}

# 確保上傳目錄存在
UPLOAD_FOLDER.mkdir(exist_ok=True)

# 匯入相關常數 (來自 import_questions.py)
LABEL_Q = "題目："
LABEL_YOUR = "你的答案："
LABEL_CORRECT = "正確答案："
LABEL_SCORE = "得分："  # optional

def get_db_connection():
    """取得資料庫連線"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # 讓結果可以像字典一樣存取
    return conn

def get_chapters() -> List[str]:
    """取得所有章節"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT chapter FROM questions ORDER BY chapter")
    chapters = [row[0] for row in cursor.fetchall()]
    conn.close()
    return chapters

def get_questions_by_chapter(chapter: str) -> List[Dict[str, Any]]:
    """根據章節取得題目和答案"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 取得該章節的所有題目
    cursor.execute("""
        SELECT id, q_text, q_type, source_file, created_at 
        FROM questions 
        WHERE chapter = ? 
        ORDER BY id
    """, (chapter,))
    
    questions = []
    for row in cursor.fetchall():
        question_id = row[0]
        
        # 取得該題目的所有答案
        cursor.execute("""
            SELECT answer_text, position 
            FROM answers 
            WHERE question_id = ? 
            ORDER BY position
        """, (question_id,))
        
        answers = [answer_row[0] for answer_row in cursor.fetchall()]
        
        questions.append({
            'id': question_id,
            'question': row[1],
            'type': row[2],
            'source_file': row[3],
            'created_at': row[4],
            'answers': answers
        })
    
    conn.close()
    return questions

def get_all_questions() -> List[Dict[str, Any]]:
    """取得所有題目"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT q.id, q.chapter, q.q_text, q.q_type, q.source_file, q.created_at
        FROM questions q
        ORDER BY q.chapter, q.id
    """)
    
    questions = []
    for row in cursor.fetchall():
        question_id = row[0]
        
        # 取得該題目的所有答案
        cursor.execute("""
            SELECT answer_text, position 
            FROM answers 
            WHERE question_id = ? 
            ORDER BY position
        """, (question_id,))
        
        answers = [answer_row[0] for answer_row in cursor.fetchall()]
        
        questions.append({
            'id': question_id,
            'chapter': row[1],
            'question': row[2],
            'type': row[3],
            'source_file': row[4],
            'created_at': row[5],
            'answers': answers
        })
    
    conn.close()
    return questions

def search_questions(keyword: str) -> List[Dict[str, Any]]:
    """搜尋題目"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT q.id, q.chapter, q.q_text, q.q_type, q.source_file, q.created_at
        FROM questions q
        WHERE q.q_text LIKE ? OR q.chapter LIKE ?
        ORDER BY q.chapter, q.id
    """, (f'%{keyword}%', f'%{keyword}%'))
    
    questions = []
    for row in cursor.fetchall():
        question_id = row[0]
        
        # 取得該題目的所有答案
        cursor.execute("""
            SELECT answer_text, position 
            FROM answers 
            WHERE question_id = ? 
            ORDER BY position
        """, (question_id,))
        
        answers = [answer_row[0] for answer_row in cursor.fetchall()]
        
        questions.append({
            'id': question_id,
            'chapter': row[1],
            'question': row[2],
            'type': row[3],
            'source_file': row[4],
            'created_at': row[5],
            'answers': answers
        })
    
    conn.close()
    return questions

def get_statistics() -> Dict[str, Any]:
    """取得統計資訊"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 總題數
    cursor.execute("SELECT COUNT(*) FROM questions")
    total_questions = cursor.fetchone()[0]
    
    # 各章節題數
    cursor.execute("""
        SELECT chapter, COUNT(*) as count
        FROM questions 
        GROUP BY chapter 
        ORDER BY chapter
    """)
    chapter_stats = dict(cursor.fetchall())
    
    # 題目類型統計
    cursor.execute("""
        SELECT q_type, COUNT(*) as count
        FROM questions 
        GROUP BY q_type
    """)
    type_stats = dict(cursor.fetchall())
    
    conn.close()
    
    return {
        'total_questions': total_questions,
        'chapter_stats': chapter_stats,
        'type_stats': type_stats
    }

def allowed_file(filename):
    """檢查檔案類型是否允許"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def normalize_text(s: str) -> str:
    """正規化文字用於去重"""
    return re.sub(r"\s+", " ", s.strip())

def detect_type(question: str) -> str:
    """填空題 if contains [__N__], else 選擇題."""
    return "填空題" if re.search(r"\[__\d+__\]", question) else "選擇題"

def determine_chapter(path: Path, fallback: Optional[str]) -> str:
    """找到檔案名或目錄中的 'chN'"""
    # 從檔案名和路徑中搜尋
    for part in [path.stem] + list(path.parts[::-1]):
        m = re.search(r"\bch(\d{1,2})\b", part, flags=re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 10:
                return f"ch{n}"
    return fallback if fallback else "unknown"

def parse_blocks(text: str) -> List[Dict[str, object]]:
    """
    解析題目格式為字典列表
    """
    lines = [l.rstrip("\n") for l in text.splitlines()]
    entries = []
    cur = None

    def flush():
        nonlocal cur, entries
        if cur:
            entries.append(cur)
            cur = None

    i = 0
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()

        # 新題目開始
        if line.startswith(LABEL_Q):
            flush()
            q = line[len(LABEL_Q):].strip()
            cur = {"question": q, "your": [], "correct": []}
            i += 1
            continue

        # 你的答案
        if line.startswith(LABEL_YOUR) and cur is not None:
            rest = line[len(LABEL_YOUR):].strip()
            answers = []
            if rest:
                answers.append(rest)
            i += 1
            while i < len(lines):
                peek = lines[i].strip()
                if (peek.startswith(LABEL_CORRECT) or
                    peek.startswith(LABEL_Q) or
                    peek.startswith(LABEL_SCORE)):
                    break
                if peek != "":
                    answers.append(peek)
                i += 1
            cur["your"] = answers
            continue

        # 正確答案
        if line.startswith(LABEL_CORRECT) and cur is not None:
            rest = line[len(LABEL_CORRECT):].strip()
            answers = []
            if rest:
                answers.append(rest)
            i += 1
            while i < len(lines):
                peek = lines[i].strip()
                if (peek.startswith(LABEL_Q) or
                    peek.startswith(LABEL_SCORE) or
                    peek.startswith(LABEL_YOUR)):
                    break
                if peek != "":
                    answers.append(peek)
                i += 1
            cur["correct"] = answers
            continue

        i += 1

    flush()
    return entries

def create_tables():
    """建立資料庫表格"""
    conn = get_db_connection()
    conn.executescript("""
    PRAGMA foreign_keys = ON;
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        chapter TEXT NOT NULL,
        q_text TEXT NOT NULL,
        q_text_norm TEXT NOT NULL,
        q_type TEXT NOT NULL CHECK (q_type IN ('選擇題','填空題')),
        source_file TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(chapter, q_text_norm)
    );
    CREATE TABLE IF NOT EXISTS answers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        answer_text TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(question_id, position, answer_text),
        FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
    );
    """)
    conn.close()

def import_questions_from_entries(entries: List[Dict[str, object]], chapter: str, source_file: str) -> Dict[str, int]:
    """將解析後的題目匯入資料庫"""
    create_tables()  # 確保表格存在
    
    conn = get_db_connection()
    cursor = conn.cursor()

    inserted_q = 0
    skipped_q = 0
    skipped_unanswered = 0
    inserted_a = 0

    for e in entries:
        q = (e.get("question") or "").strip()
        correct = [a.strip() for a in e.get("correct", []) if a.strip() != ""]

        # 跳過沒有正確答案或'未作答'的題目
        if len(correct) == 0 or (len(correct) == 1 and correct[0] == "未作答"):
            skipped_unanswered += 1
            continue

        q_norm = normalize_text(q)
        q_type = detect_type(q)

        # 插入題目 (忽略重複)
        cursor.execute(
            "INSERT OR IGNORE INTO questions (chapter, q_text, q_text_norm, q_type, source_file) "
            "VALUES (?, ?, ?, ?, ?)",
            (chapter, q, q_norm, q_type, source_file),
        )
        if cursor.rowcount == 1:
            inserted_q += 1
            q_id = cursor.lastrowid
        else:
            # 取得現有 id
            cursor.execute(
                "SELECT id FROM questions WHERE chapter=? AND q_text_norm=?",
                (chapter, q_norm),
            )
            row = cursor.fetchone()
            if not row:
                skipped_q += 1
                continue
            q_id = row[0]
            skipped_q += 1

        # 插入答案
        for idx, ans in enumerate(correct, start=1):
            cursor.execute(
                "INSERT OR IGNORE INTO answers (question_id, position, answer_text) "
                "VALUES (?, ?, ?)",
                (q_id, idx, ans),
            )
            if cursor.rowcount == 1:
                inserted_a += 1

    conn.commit()
    conn.close()
    return {
        "inserted_questions": inserted_q,
        "duplicates_skipped": skipped_q,
        "skipped_unanswered": skipped_unanswered,
        "inserted_answers": inserted_a,
    }

@app.route('/')
def index():
    """首頁"""
    stats = get_statistics()
    chapters = get_chapters()
    return render_template('index.html', stats=stats, chapters=chapters)

@app.route('/chapter/<chapter>')
def view_chapter(chapter):
    """查看特定章節的題目"""
    questions = get_questions_by_chapter(chapter)
    return render_template('chapter.html', chapter=chapter, questions=questions)

@app.route('/all')
def view_all():
    """查看所有題目"""
    questions = get_all_questions()
    return render_template('all_questions.html', questions=questions)

@app.route('/search')
def search():
    """搜尋題目"""
    keyword = request.args.get('q', '').strip()
    if keyword:
        questions = search_questions(keyword)
        return render_template('search_results.html', questions=questions, keyword=keyword)
    return render_template('search.html')

@app.route('/api/chapters')
def api_chapters():
    """API: 取得所有章節"""
    return jsonify(get_chapters())

@app.route('/api/chapter/<chapter>')
def api_chapter(chapter):
    """API: 取得特定章節的題目"""
    return jsonify(get_questions_by_chapter(chapter))

@app.route('/api/stats')
def api_stats():
    """API: 取得統計資訊"""
    return jsonify(get_statistics())

@app.route('/api/search')
def api_search():
    """API: 搜尋題目"""
    keyword = request.args.get('q', '').strip()
    if keyword:
        return jsonify(search_questions(keyword))
    return jsonify([])

@app.route('/import', methods=['GET', 'POST'])
def import_questions():
    """匯入題目功能"""
    if request.method == 'POST':
        chapter = request.form.get('chapter', '').strip()
        import_method = request.form.get('import_method', 'file')
        
        if not chapter:
            flash('請輸入章節名稱', 'error')
            return redirect(request.url)
        
        # 驗證章節格式
        if not re.match(r'^ch\d{1,2}$', chapter.lower()):
            flash('章節格式不正確，請使用 ch1, ch2, ... 等格式', 'error')
            return redirect(request.url)
            
        content = None
        source_info = None
        
        # 根據匯入方式處理內容
        if import_method == 'text':
            # 直接貼入文字
            content = request.form.get('text_content', '').strip()
            if not content:
                flash('請貼入題目內容', 'error')
                return redirect(request.url)
            source_info = 'Direct Text Input'
            
        else:
            # 檔案上傳
            if 'file' not in request.files:
                flash('請選擇要上傳的檔案', 'error')
                return redirect(request.url)
            
            file = request.files['file']
            
            if file.filename == '':
                flash('請選擇要上傳的檔案', 'error')
                return redirect(request.url)
            
            if file and allowed_file(file.filename):
                try:
                    content = file.read().decode('utf-8-sig', errors='ignore')
                    source_info = file.filename
                except Exception as e:
                    flash(f'讀取檔案時發生錯誤：{str(e)}', 'error')
                    return redirect(request.url)
            else:
                flash('不支援的檔案格式，請上傳 .txt 檔案', 'error')
                return redirect(request.url)
        
        # 處理內容
        if content:
            try:
                # 解析題目
                entries = parse_blocks(content)
                
                if not entries:
                    flash('內容中沒有找到有效的題目', 'error')
                    return redirect(request.url)
                
                # 匯入資料庫
                stats = import_questions_from_entries(entries, chapter.lower(), source_info)
                
                # 顯示結果
                flash(f'匯入完成！新增 {stats["inserted_questions"]} 題，跳過重複 {stats["duplicates_skipped"]} 題，跳過未作答 {stats["skipped_unanswered"]} 題', 'success')
                
                return redirect(url_for('view_chapter', chapter=chapter.lower()))
                
            except Exception as e:
                flash(f'匯入時發生錯誤：{str(e)}', 'error')
                return redirect(request.url)
    
    # GET 請求：顯示匯入頁面
    stats = get_statistics()
    return render_template('import.html', stats=stats)

@app.route('/import/help')
def import_help():
    """匯入說明頁面"""
    return render_template('import_help.html')

@app.route('/api/import/preview', methods=['POST'])
def api_import_preview():
    """API: 預覽匯入內容"""
    import_method = request.form.get('import_method', 'file')
    content = None
    
    if import_method == 'text':
        # 文字輸入預覽
        content = request.form.get('text_content', '').strip()
        if not content:
            return jsonify({'error': '沒有輸入內容'}), 400
    else:
        # 檔案上傳預覽
        if 'file' not in request.files:
            return jsonify({'error': '沒有檔案'}), 400
        
        file = request.files['file']
        if file.filename == '' or not allowed_file(file.filename):
            return jsonify({'error': '無效的檔案'}), 400
        
        try:
            content = file.read().decode('utf-8-sig', errors='ignore')
        except Exception as e:
            return jsonify({'error': f'讀取檔案時發生錯誤: {str(e)}'}), 500
    
    try:
        entries = parse_blocks(content)
        
        preview_data = []
        for entry in entries[:5]:  # 只顯示前5題
            preview_data.append({
                'question': entry.get('question', ''),
                'type': detect_type(entry.get('question', '')),
                'answers': entry.get('correct', [])
            })
        
        return jsonify({
            'total_questions': len(entries),
            'preview': preview_data,
            'method': import_method
        })
    except Exception as e:
        return jsonify({'error': f'解析內容時發生錯誤: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)