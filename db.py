"""SQLite helpers for CareerTrack."""
import sqlite3
from contextlib import closing

# Columns added after the first version. They are appended to existing
# databases automatically, so old data is kept.
EXTRA_COLUMNS = {
    "date_applied": "TEXT",
    "source": "TEXT",
    "notes": "TEXT",
}


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(path):
    """Create the table if needed and migrate older databases."""
    with closing(connect(path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company TEXT NOT NULL,
                position TEXT NOT NULL,
                status TEXT NOT NULL
            )
            """
        )
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(applications)")}
        for name, col_type in EXTRA_COLUMNS.items():
            if name not in existing:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {name} {col_type}")
        conn.commit()
