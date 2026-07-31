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
                    transcript TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
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
            conn.commit()

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
                        transcript,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        transcript,
                        created_at,
                    ),
                )
                conn.commit()
