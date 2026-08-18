"""
Storage layer. SQLite for now — no server to set up, it's just a file.
Swap to Postgres later ONLY if you actually hit a real limitation
(concurrent writes, multiple services needing access). Don't do it early.
"""

import sqlite3
import os
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "leads.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            address TEXT,
            phone TEXT,
            website TEXT,
            date_found TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def save_lead(company: dict):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        INSERT INTO leads (company_name, address, phone, website, date_found)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            company["company_name"],
            company["address"],
            company["phone"],
            company["website"],
            str(date.today()),
        ),
    )
    conn.commit()
    conn.close()


def get_all_leads() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM leads").fetchall()
    conn.close()
    return [dict(row) for row in rows]


if __name__ == "__main__":
    # Quick manual test: python src/store.py
    init_db()
    print("DB initialized at", DB_PATH)
    print("Current leads:", get_all_leads())
