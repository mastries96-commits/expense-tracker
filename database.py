import sqlite3
import calendar
from contextlib import contextmanager
from typing import Optional, Dict, List

from config import DB_PATH


class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS months (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    year        INTEGER NOT NULL,
                    month       INTEGER NOT NULL,
                    salary      REAL    DEFAULT 0,
                    status      TEXT    DEFAULT 'active',
                    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at   TIMESTAMP,
                    UNIQUE(year, month)
                );

                CREATE TABLE IF NOT EXISTS fixed_costs (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    month_id  INTEGER NOT NULL,
                    name      TEXT    NOT NULL,
                    amount    REAL    NOT NULL,
                    FOREIGN KEY (month_id) REFERENCES months(id)
                );

                CREATE TABLE IF NOT EXISTS expenses (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    month_id      INTEGER NOT NULL,
                    category      TEXT    NOT NULL,
                    amount        REAL    NOT NULL,
                    description   TEXT    DEFAULT '',
                    expense_date  DATE    NOT NULL,
                    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (month_id) REFERENCES months(id)
                );
            """)

    # ── Month operations ──────────────────────────────────────────────────────

    def get_active_month(self) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM months WHERE status='active' ORDER BY year DESC, month DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def create_or_get_month(self, year: int, month: int, salary: float) -> int:
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM months WHERE year=? AND month=?", (year, month)
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE months SET salary=?, status='active', closed_at=NULL WHERE id=?",
                    (salary, existing["id"])
                )
                return existing["id"]
            cursor = conn.execute(
                "INSERT INTO months (year, month, salary, status) VALUES (?,?,?,'active')",
                (year, month, salary)
            )
            return cursor.lastrowid

    def close_month(self, month_id: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE months SET status='closed', closed_at=CURRENT_TIMESTAMP WHERE id=?",
                (month_id,)
            )

    def get_all_months(self) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM months ORDER BY year DESC, month DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Fixed costs ───────────────────────────────────────────────────────────

    def add_fixed_costs(self, month_id: int, costs: Dict[str, float]):
        with self._conn() as conn:
            conn.execute("DELETE FROM fixed_costs WHERE month_id=?", (month_id,))
            conn.executemany(
                "INSERT INTO fixed_costs (month_id, name, amount) VALUES (?,?,?)",
                [(month_id, name, amount) for name, amount in costs.items()]
            )

    # ── Expenses ──────────────────────────────────────────────────────────────

    def add_expense(self, month_id: int, category: str,
                    amount: float, description: str, expense_date) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO expenses (month_id, category, amount, description, expense_date) "
                "VALUES (?,?,?,?,?)",
                (month_id, category, amount, description, str(expense_date))
            )
            return cur.lastrowid

    def delete_expense(self, expense_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))

    def find_expense(self, month_id: int, category: str, amount: float):
        """Most recent expense in the month matching category + amount."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM expenses WHERE month_id=? AND category=? AND ABS(amount - ?) < 0.01 "
                "ORDER BY created_at DESC LIMIT 1",
                (month_id, category, amount)
            ).fetchone()
            return dict(row) if row else None

    def get_last_expense(self, month_id: int):
        """Most recently added expense in the month."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM expenses WHERE month_id=? ORDER BY created_at DESC LIMIT 1",
                (month_id,)
            ).fetchone()
            return dict(row) if row else None

    def update_expense_description(self, expense_id: int, description: str):
        with self._conn() as conn:
            conn.execute(
                "UPDATE expenses SET description=? WHERE id=?",
                (description, expense_id)
            )

    def update_expense_category(self, expense_id: int, category: str, description: str = None):
        with self._conn() as conn:
            if description is not None:
                conn.execute(
                    "UPDATE expenses SET category=?, description=? WHERE id=?",
                    (category, description, expense_id)
                )
            else:
                conn.execute(
                    "UPDATE expenses SET category=? WHERE id=?",
                    (category, expense_id)
                )

    def get_expenses_summary(self, month_id: int) -> Dict[str, float]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT category, SUM(amount) as total FROM expenses "
                "WHERE month_id=? GROUP BY category ORDER BY total DESC",
                (month_id,)
            ).fetchall()
            return {r["category"]: r["total"] for r in rows}

    # ── Aggregates ────────────────────────────────────────────────────────────

    def get_balance(self, month_id: int) -> float:
        with self._conn() as conn:
            row = conn.execute("SELECT salary FROM months WHERE id=?", (month_id,)).fetchone()
            if not row:
                return 0.0
            salary = row["salary"]

            fixed = conn.execute(
                "SELECT COALESCE(SUM(amount),0) total FROM fixed_costs WHERE month_id=?",
                (month_id,)
            ).fetchone()["total"]

            spent = conn.execute(
                "SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE month_id=?",
                (month_id,)
            ).fetchone()["total"]

            return salary - fixed - spent

    def get_last_closed_month(self) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM months WHERE status='closed' ORDER BY closed_at DESC LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def delete_month_cascade(self, month_id: int):
        with self._conn() as conn:
            conn.execute("DELETE FROM expenses WHERE month_id=?", (month_id,))
            conn.execute("DELETE FROM fixed_costs WHERE month_id=?", (month_id,))
            conn.execute("DELETE FROM months WHERE id=?", (month_id,))

    def reopen_month(self, month_id: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE months SET status='active', closed_at=NULL WHERE id=?",
                (month_id,)
            )

    def get_month_details(self, month_id: int) -> Dict:
        with self._conn() as conn:
            month = conn.execute("SELECT * FROM months WHERE id=?", (month_id,)).fetchone()
            if not month:
                return {}
            fixed = conn.execute(
                "SELECT * FROM fixed_costs WHERE month_id=?", (month_id,)
            ).fetchall()
            expenses = conn.execute(
                "SELECT * FROM expenses WHERE month_id=? ORDER BY expense_date, created_at",
                (month_id,)
            ).fetchall()
            return {
                "month": dict(month),
                "fixed_costs": [dict(r) for r in fixed],
                "expenses": [dict(r) for r in expenses],
            }
