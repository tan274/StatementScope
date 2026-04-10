import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "statementscope.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id          TEXT PRIMARY KEY,
            date        TEXT,
            description TEXT,
            amount      REAL,
            direction   TEXT,
            category    TEXT,
            balance     REAL,
            source_file TEXT,
            provider    TEXT
        )
    """)
    conn.commit()
    conn.close()


def save_transactions(transactions: list[dict]):
    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        """
        INSERT OR IGNORE INTO transactions
            (id, date, description, amount, direction, category, balance, source_file, provider)
        VALUES
            (:id, :date, :description, :amount, :direction, :category, :balance, :source_file, :provider)
        """,
        transactions,
    )
    conn.commit()
    conn.close()


def load_transactions() -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM transactions").fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_categories(transactions: list[dict]):
    conn = sqlite3.connect(DB_PATH)
    conn.executemany(
        "UPDATE transactions SET category = :category WHERE id = :id",
        [{"id": t["id"], "category": t.get("category")} for t in transactions],
    )
    conn.commit()
    conn.close()


def clear_transactions():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM transactions")
    conn.commit()
    conn.close()
