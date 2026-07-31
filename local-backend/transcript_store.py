import os
import sqlite3
import threading
from datetime import datetime, timezone


class TranscriptStore:
    def __init__(self, db_path):
        self.db_path = db_path
        self._lock = threading.Lock()
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    wav_path TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    duration_seconds REAL NOT NULL,
                    sample_rate INTEGER NOT NULL,
                    channels INTEGER NOT NULL,
                    sample_width INTEGER NOT NULL,
                    segment_index INTEGER NOT NULL DEFAULT 1,
                    segment_started_at TEXT NOT NULL DEFAULT '',
                    segment_ended_at TEXT NOT NULL DEFAULT '',
                    word_count INTEGER NOT NULL DEFAULT 0,
                    char_count INTEGER NOT NULL DEFAULT 0,
                    avg_rms REAL NOT NULL DEFAULT 0,
                    peak_abs INTEGER NOT NULL DEFAULT 0,
                    stt_model TEXT NOT NULL DEFAULT '',
                    stt_input_gain REAL NOT NULL DEFAULT 1.0,
                    transcript TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._ensure_column(conn, "segment_index", "INTEGER NOT NULL DEFAULT 1")
            self._ensure_column(conn, "segment_started_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "segment_ended_at", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "word_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "char_count", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "avg_rms", "REAL NOT NULL DEFAULT 0")
            self._ensure_column(conn, "peak_abs", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "stt_model", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "stt_input_gain", "REAL NOT NULL DEFAULT 1.0")
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transcripts_started_at
                ON transcripts(started_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transcripts_session_id
                ON transcripts(session_id)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_transcripts_created_at
                ON transcripts(created_at)
                """
            )
            conn.commit()

    def _ensure_column(self, conn, column_name, column_sql):
        rows = conn.execute("PRAGMA table_info(transcripts)").fetchall()
        existing = {row[1] for row in rows}
        if column_name not in existing:
            conn.execute(f"ALTER TABLE transcripts ADD COLUMN {column_name} {column_sql}")

    def add_transcript(
        self,
        session_id,
        wav_path,
        started_at,
        ended_at,
        duration_seconds,
        sample_rate,
        channels,
        sample_width,
        segment_index,
        segment_started_at,
        segment_ended_at,
        word_count,
        char_count,
        avg_rms,
        peak_abs,
        stt_model,
        stt_input_gain,
        transcript,
    ):
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO transcripts (
                        session_id,
                        wav_path,
                        started_at,
                        ended_at,
                        duration_seconds,
                        sample_rate,
                        channels,
                        sample_width,
                        segment_index,
                        segment_started_at,
                        segment_ended_at,
                        word_count,
                        char_count,
                        avg_rms,
                        peak_abs,
                        stt_model,
                        stt_input_gain,
                        transcript,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        wav_path,
                        started_at,
                        ended_at,
                        duration_seconds,
                        sample_rate,
                        channels,
                        sample_width,
                        segment_index,
                        segment_started_at,
                        segment_ended_at,
                        word_count,
                        char_count,
                        avg_rms,
                        peak_abs,
                        stt_model,
                        stt_input_gain,
                        transcript,
                        created_at,
                    ),
                )
                conn.commit()

    def list_transcripts(self, search=None, limit=50, offset=0):
        safe_limit = max(1, min(int(limit), 200))
        safe_offset = max(0, int(offset))
        query = """
            SELECT
                id,
                session_id,
                wav_path,
                started_at,
                ended_at,
                duration_seconds,
                segment_index,
                segment_started_at,
                segment_ended_at,
                transcript,
                word_count,
                char_count,
                avg_rms,
                peak_abs,
                stt_model,
                stt_input_gain,
                created_at
            FROM transcripts
        """
        args = []
        if search:
            query += " WHERE transcript LIKE ?"
            args.append(f"%{search}%")
        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        args.extend([safe_limit, safe_offset])

        with self._lock:
            with self._connect() as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(query, args).fetchall()
                if search:
                    total = conn.execute(
                        "SELECT COUNT(*) FROM transcripts WHERE transcript LIKE ?", (f"%{search}%",)
                    ).fetchone()[0]
                else:
                    total = conn.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]

        return [dict(row) for row in rows], int(total)
