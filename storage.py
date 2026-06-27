"""Storage layer for Auto Apply Job using Supabase."""

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from config import (
    APP_ROOT,
    APPLICATION_DB_FILE,
    APPLICATION_LOG_FILE,
    QUESTION_MEMORY_FILE,
    STATUS_FILE,
    get_daily_application_target,
    get_candidate_profile,
)

# Try to import Supabase, fall back to SQLite if not available
try:
    from __future__ import
    #from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

# Supabase client singleton
_supabase_client: Optional[Client] = None


def get_supabase_client() -> Optional[Client]:
    """Get or create Supabase client."""
    global _supabase_client

    if not SUPABASE_AVAILABLE:
        return None

    import os
    url = os.getenv("SUPABASE_URL") or os.getenv("VITE_SUPABASE_URL")
    key = (
        os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_ANON_KEY")
        or os.getenv("VITE_SUPABASE_ANON_KEY")
    )

    if not url or not key:
        return None

    if _supabase_client is None:
        _supabase_client = create_client(url, key)

    return _supabase_client


def use_supabase() -> bool:
    """Check if Supabase should be used for storage."""
    return get_supabase_client() is not None


# =============================================================================
# JSON File Fallback Functions
# =============================================================================


def read_json_file(path: Path, default_value):
    """Read JSON file with fallback."""
    if not path.exists():
        return default_value

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_value


def write_json_file(path: Path, payload):
    """Write JSON file."""
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


# =============================================================================
# Status Records
# =============================================================================


def load_status_record() -> dict:
    """Load agent status record."""
    return read_json_file(STATUS_FILE, {})


def save_status_record(status: dict) -> None:
    """Save agent status record."""
    write_json_file(STATUS_FILE, status)


def clear_status_record() -> None:
    """Clear agent status record."""
    try:
        STATUS_FILE.unlink(missing_ok=True)
    except OSError:
        pass


# =============================================================================
# Application History
# =============================================================================


def load_application_history() -> dict:
    """Load application history."""
    return read_json_file(APPLICATION_LOG_FILE, {"applications": []})


def record_application_event(
    job_context: dict,
    status: str,
    reason: Optional[str] = None,
    artifacts: Optional[dict] = None,
) -> None:
    """Record an application event."""
    event = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "status": status,
        "reason": reason,
        "url": job_context.get("url"),
        "company_name": job_context.get("company_name"),
        "job_title": job_context.get("job_title"),
        "verified": job_context.get("verified"),
        "verification_source": job_context.get("verification_source"),
        "artifacts": artifacts or {},
    }

    # Always write to local file for compatibility
    history = load_application_history()
    history.setdefault("applications", []).append(event)
    write_json_file(APPLICATION_LOG_FILE, history)

    # Also store in Supabase if available
    client = get_supabase_client()
    if client:
        try:
            client.table("applications").insert({
                "created_at": event["timestamp"],
                "status": status,
                "reason": reason,
                "url": event["url"],
                "company_name": event["company_name"],
                "job_title": event["job_title"],
                "verified": event["verified"] or False,
                "verification_source": event["verification_source"],
                "score": job_context.get("score"),
                "artifacts": event["artifacts"],
                "gap_analysis": (artifacts or {}).get("gap_analysis"),
            }).execute()
        except Exception:
            # Silently fail - local storage is primary
            pass

    # Also write to SQLite for local queries
    _record_application_event_sqlite(event, job_context, artifacts)


def _record_application_event_sqlite(event: dict, job_context: dict, artifacts: Optional[dict]) -> None:
    """Record application event in SQLite."""
    import sqlite3

    try:
        conn = sqlite3.connect(APPLICATION_DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT,
                url TEXT,
                company_name TEXT,
                job_title TEXT,
                verified INTEGER,
                verification_source TEXT,
                score INTEGER,
                source TEXT,
                artifacts_json TEXT NOT NULL,
                gap_analysis_json TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO applications (
                timestamp, status, reason, url, company_name, job_title, verified, verification_source,
                score, source, artifacts_json, gap_analysis_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["timestamp"],
                event["status"],
                event["reason"],
                event["url"],
                event["company_name"],
                event["job_title"],
                1 if event["verified"] else 0,
                event["verification_source"],
                job_context.get("score"),
                job_context.get("source", "runtime"),
                json.dumps(event["artifacts"]),
                json.dumps((artifacts or {}).get("gap_analysis")) if (artifacts or {}).get("gap_analysis") else None,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def count_successful_applications_today() -> int:
    """Count successful applications for today."""
    today = date.today().isoformat()

    client = get_supabase_client()
    if client:
        try:
            result = client.table("applications").select("id", count="exact").eq("status", "success").gte("created_at", f"{today}T00:00:00").execute()
            return result.count or 0
        except Exception:
            pass

    # Fallback to local file
    history = load_application_history()
    return sum(
        1
        for entry in history.get("applications", [])
        if entry.get("status") == "success" and str(entry.get("timestamp", "")).startswith(today)
    )


def list_recent_application_events(limit: int = 100) -> list[dict]:
    """List recent application events."""
    client = get_supabase_client()
    if client:
        try:
            result = client.table("applications").select("*").order("created_at", desc=True).limit(limit).execute()
            return [
                {
                    "timestamp": row.get("created_at"),
                    "status": row.get("status"),
                    "reason": row.get("reason"),
                    "url": row.get("url"),
                    "company_name": row.get("company_name"),
                    "job_title": row.get("job_title"),
                    "verified": row.get("verified") or False,
                    "verification_source": row.get("verification_source"),
                    "score": row.get("score"),
                    "source": row.get("source"),
                    "artifacts": row.get("artifacts") or {},
                    "gap_analysis": row.get("gap_analysis"),
                }
                for row in result.data
            ]
        except Exception:
            pass

    # Fallback to SQLite
    import sqlite3
    try:
        conn = sqlite3.connect(APPLICATION_DB_FILE)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT timestamp, status, reason, url, company_name, job_title, verified,
                   verification_source, score, source, artifacts_json, gap_analysis_json
            FROM applications
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()

        return [
            {
                "timestamp": row["timestamp"],
                "status": row["status"],
                "reason": row["reason"],
                "url": row["url"],
                "company_name": row["company_name"],
                "job_title": row["job_title"],
                "verified": bool(row["verified"]),
                "verification_source": row["verification_source"],
                "score": row["score"],
                "source": row["source"],
                "artifacts": json.loads(row["artifacts_json"] or "{}"),
                "gap_analysis": json.loads(row["gap_analysis_json"] or "null"),
            }
            for row in rows
        ]
    except Exception:
        return []


# =============================================================================
# Question Memory
# =============================================================================


def normalize_question_text(question_text: str) -> str:
    """Normalize question text for comparison."""
    return re.sub(r"\s+", " ", (question_text or "").strip().lower())


def load_question_memory() -> dict:
    """Load question memory from file and database."""
    file_memory = read_json_file(QUESTION_MEMORY_FILE, {"questions": []})
    file_questions = file_memory.get("questions", [])
    memory_by_question = {}

    for entry in file_questions:
        normalized = normalize_question_text(entry.get("question"))
        if not normalized or not entry.get("answer"):
            continue
        memory_by_question[normalized] = {
            "question": entry.get("question", "").strip(),
            "answer": entry.get("answer", "").strip(),
            "source": entry.get("source", "file"),
            "updated_at": entry.get("updated_at", ""),
        }

    # Also load from Supabase if available
    client = get_supabase_client()
    if client:
        try:
            result = client.table("question_memory").select("*").execute()
            for row in result.data:
                normalized = normalize_question_text(row.get("question_text", ""))
                if normalized:
                    memory_by_question[normalized] = {
                        "question": row.get("question_text", ""),
                        "answer": row.get("answer_text", ""),
                        "source": row.get("source", "supabase"),
                        "updated_at": row.get("updated_at", ""),
                    }
        except Exception:
            pass

    # Also load from SQLite
    import sqlite3
    try:
        conn = sqlite3.connect(APPLICATION_DB_FILE)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS question_memory (
                normalized_question TEXT PRIMARY KEY,
                question_text TEXT NOT NULL,
                answer_text TEXT NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        rows = conn.execute(
            "SELECT normalized_question, question_text, answer_text, source, updated_at FROM question_memory"
        ).fetchall()
        conn.close()

        for row in rows:
            memory_by_question[row["normalized_question"]] = {
                "question": row["question_text"],
                "answer": row["answer_text"],
                "source": row["source"],
                "updated_at": row["updated_at"],
            }
    except Exception:
        pass

    return memory_by_question


def save_question_memory(question_text: str, answer_text: str, source: str = "manual") -> None:
    """Save a question-answer pair to memory."""
    normalized = normalize_question_text(question_text)
    if not normalized or not (answer_text or "").strip():
        return

    timestamp = datetime.now().isoformat(timespec="seconds")

    # Save to Supabase if available
    client = get_supabase_client()
    if client:
        try:
            # Check if exists
            existing = client.table("question_memory").select("id").eq("normalized_question", normalized).execute()
            if existing.data:
                client.table("question_memory").update({
                    "question_text": question_text.strip(),
                    "answer_text": answer_text.strip(),
                    "source": source,
                    "updated_at": timestamp,
                }).eq("normalized_question", normalized).execute()
            else:
                client.table("question_memory").insert({
                    "normalized_question": normalized,
                    "question_text": question_text.strip(),
                    "answer_text": answer_text.strip(),
                    "source": source,
                    "updated_at": timestamp,
                }).execute()
        except Exception:
            pass

    # Save to SQLite
    import sqlite3
    try:
        conn = sqlite3.connect(APPLICATION_DB_FILE)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS question_memory (
                normalized_question TEXT PRIMARY KEY,
                question_text TEXT NOT NULL,
                answer_text TEXT NOT NULL,
                source TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO question_memory (normalized_question, question_text, answer_text, source, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(normalized_question) DO UPDATE SET
                question_text=excluded.question_text,
                answer_text=excluded.answer_text,
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (normalized, question_text.strip(), answer_text.strip(), source, timestamp),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

    # Update local file for compatibility
    memory = load_question_memory()
    questions = sorted(memory.values(), key=lambda item: item["question"].lower())
    write_json_file(QUESTION_MEMORY_FILE, {"questions": questions})


def build_question_memory_context() -> str:
    """Build context string from question memory for prompts."""
    memory = load_question_memory()
    if not memory:
        return ""

    lines = ["Known reusable screening answers:"]
    for entry in sorted(memory.values(), key=lambda item: item["question"].lower()):
        lines.append(f"- {entry['question']}: {entry['answer']}")
    return "\n".join(lines)


# =============================================================================
# Initialization
# =============================================================================


def initialize_application_store() -> None:
    """Initialize local SQLite tables."""
    import sqlite3
    conn = sqlite3.connect(APPLICATION_DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            reason TEXT,
            url TEXT,
            company_name TEXT,
            job_title TEXT,
            verified INTEGER,
            verification_source TEXT,
            score INTEGER,
            source TEXT,
            artifacts_json TEXT NOT NULL,
            gap_analysis_json TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS question_memory (
            normalized_question TEXT PRIMARY KEY,
            question_text TEXT NOT NULL,
            answer_text TEXT NOT NULL,
            source TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def print_daily_progress() -> None:
    """Print daily application progress."""
    successes = count_successful_applications_today()
    target = get_daily_application_target()
    print(f"[*] Daily verified application progress: {successes}/{target}")
