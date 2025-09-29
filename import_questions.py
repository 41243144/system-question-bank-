
import re
import sys
import sqlite3
import argparse
from pathlib import Path
from typing import List, Tuple, Dict, Optional

LABEL_Q = "題目："
LABEL_YOUR = "你的答案："
LABEL_CORRECT = "正確答案："
LABEL_SCORE = "得分："  # optional

def normalize_text(s: str) -> str:
    """Trim and collapse all whitespace to single spaces for dedup."""
    import re
    return re.sub(r"\s+", " ", s.strip())

def detect_type(question: str) -> str:
    """填空題 if contains [__N__], else 選擇題."""
    return "填空題" if re.search(r"\[__\d+__\]", question) else "選擇題"

def determine_chapter(path: Path, fallback: Optional[str]) -> str:
    """Find 'chN' in filename or parents; else use fallback or 'unknown'."""
    import re
    # search in the path parts from leaf to root
    for part in [path.stem] + list(path.parts[::-1]):
        m = re.search(r"\bch(\d{1,2})\b", part, flags=re.IGNORECASE)
        if m:
            n = int(m.group(1))
            if 0 <= n <= 10:
                return f"ch{n}"
    return fallback if fallback else "unknown"

def parse_blocks(text: str) -> List[Dict[str, object]]:
    """
    Parse the loose Q/A format into a list of dicts with keys:
      question:str, your:List[str], correct:List[str]
    Robust to inline '正確答案：xxx' and blank lines.
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

        # Start of a new question
        if line.startswith(LABEL_Q):
            # finalize previous
            flush()
            q = line[len(LABEL_Q):].strip()
            cur = {"question": q, "your": [], "correct": []}
            i += 1
            continue

        # Your answer
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

        # Correct answer
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

DDL = r"""
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
"""

def upsert_entries(db_path: Path, entries: List[Dict[str, object]], chapter: str, source_file: str) -> Dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    conn.executescript(DDL)
    cur = conn.cursor()

    inserted_q = 0
    skipped_q = 0
    skipped_unanswered = 0
    inserted_a = 0

    for e in entries:
        q = (e.get("question") or "").strip()
        correct = [a.strip() for a in e.get("correct", []) if a.strip() != ""]

        # Skip if no correct answer or '未作答'
        if len(correct) == 0 or (len(correct) == 1 and correct[0] == "未作答"):
            skipped_unanswered += 1
            continue

        q_norm = normalize_text(q)
        q_type = detect_type(q)

        # Insert question (ignore duplicates)
        cur.execute(
            "INSERT OR IGNORE INTO questions (chapter, q_text, q_text_norm, q_type, source_file) "
            "VALUES (?, ?, ?, ?, ?)",
            (chapter, q, q_norm, q_type, source_file),
        )
        if cur.rowcount == 1:
            inserted_q += 1
            q_id = cur.lastrowid
        else:
            # fetch existing id
            cur.execute(
                "SELECT id FROM questions WHERE chapter=? AND q_text_norm=?",
                (chapter, q_norm),
            )
            row = cur.fetchone()
            if not row:
                # Extremely unlikely due to race; treat as skip
                skipped_q += 1
                continue
            q_id = row[0]
            skipped_q += 1  # duplicate question, no update as requested

        # Insert answers with stable positions
        for idx, ans in enumerate(correct, start=1):
            cur.execute(
                "INSERT OR IGNORE INTO answers (question_id, position, answer_text) "
                "VALUES (?, ?, ?)",
                (q_id, idx, ans),
            )
            if cur.rowcount == 1:
                inserted_a += 1

    conn.commit()
    conn.close()
    return {
        "inserted_questions": inserted_q,
        "duplicates_skipped": skipped_q,
        "skipped_unanswered": skipped_unanswered,
        "inserted_answers": inserted_a,
    }

def gather_files(paths: List[str]) -> List[Path]:
    files = []
    for p in paths:
        path = Path(p)
        if path.is_file():
            files.append(path)
        elif path.is_dir():
            files.extend([f for f in path.rglob("*.txt") if f.is_file()])
    return files

def main():
    ap = argparse.ArgumentParser(description="Import OS questions into SQLite.")
    ap.add_argument("paths", nargs="+", help="Text files or directories to import")
    ap.add_argument("--db", default="questions.db", help="SQLite DB file path")
    ap.add_argument("--chapter", default=None, help="Override chapter tag (e.g., ch0..ch10)")
    ap.add_argument("--encoding", default="utf-8", help="File encoding")
    args = ap.parse_args()

    db_path = Path(args.db)
    files = gather_files(args.paths)
    if not files:
        print("No input files found.", file=sys.stderr)
        sys.exit(1)

    grand_totals = {"inserted_questions":0,"duplicates_skipped":0,"skipped_unanswered":0,"inserted_answers":0}

    for f in files:
        chapter = determine_chapter(f, args.chapter)
        text = f.read_text(encoding=args.encoding, errors="ignore")
        entries = parse_blocks(text)
        stats = upsert_entries(db_path, entries, chapter, str(f))
        print(f"[{f.name}] -> chapter={chapter} : {stats}")
        for k,v in stats.items():
            grand_totals[k] += v

    print("TOTAL:", grand_totals)

if __name__ == "__main__":
    main()
