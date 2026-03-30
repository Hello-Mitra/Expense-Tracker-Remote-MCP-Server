from fastmcp import FastMCP
import os
import sqlite3
import json
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
if os.environ.get('DATA_DIR'):
    DATA_DIR = os.environ.get('DATA_DIR')
elif os.name == 'nt':  # Windows
    DATA_DIR = os.path.dirname(__file__)
else:  # Linux/Mac (cloud)
    DATA_DIR = '/tmp'

DB_PATH = os.path.join(DATA_DIR, 'expenses.db')
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), 'categories.json')

print(f"Database path: {DB_PATH}")

# ── Server ─────────────────────────────────────────────────────────────────────
mcp = FastMCP("Expense Tracker Server")

# ── Database Init ──────────────────────────────────────────────────────────────
def init_db():
    try:
        with sqlite3.connect(DB_PATH) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute('''
                CREATE TABLE IF NOT EXISTS expenses (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    date        TEXT    NOT NULL,
                    amount      REAL    NOT NULL,
                    quantity    REAL    NOT NULL DEFAULT 1,
                    category    TEXT    NOT NULL,
                    subcategory TEXT    DEFAULT '',
                    note        TEXT    DEFAULT ''
                )
            ''')
            # migrate existing table if quantity column missing
            try:
                c.execute("ALTER TABLE expenses ADD COLUMN quantity REAL NOT NULL DEFAULT 1")
                print("✅ Migrated: added quantity column")
            except sqlite3.OperationalError:
                pass  # column already exists
            # test write access
            c.execute("INSERT OR IGNORE INTO expenses(date, amount, quantity, category) VALUES ('test', 0, 1, 'test')")
            c.execute("DELETE FROM expenses WHERE category = 'test'")
            print(f"✅ Database ready at {DB_PATH}")
    except Exception as e:
        print(f"❌ Database error: {e}")
        raise

init_db()

# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def add_expense(date: str, amount: float, category: str,
                quantity: float = 1, subcategory: str = '',
                note: str = '') -> dict:
    """
    Add a new expense entry to the database.
    amount = price per unit
    quantity = number of units (default 1)
    total = amount * quantity (calculated automatically)
    """
    try:
        total = amount * quantity
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(
                "INSERT INTO expenses (date, amount, quantity, category, subcategory, note) VALUES (?,?,?,?,?,?)",
                (date, amount, quantity, category, subcategory, note)
            )
        return {
            "status": "success",
            "id": cur.lastrowid,
            "amount_per_unit": amount,
            "quantity": quantity,
            "total": total,
            "message": "Expense added successfully"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def get_expenses(start_date: str, end_date: str) -> list:
    """Retrieve all expense entries within an inclusive date range from the database"""
    try:
        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute('''
                SELECT id, date, amount, quantity,
                       ROUND(amount * quantity, 2) AS total,
                       category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
                ORDER BY date DESC, id DESC
            ''', (start_date, end_date))
            cols = [col[0] for col in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def delete_expense(
    expense_id: Optional[int] = None,
    date: Optional[str] = None,
    category: Optional[str] = None,
    subcategory: Optional[str] = None,
    amount: Optional[float] = None
) -> dict:
    """
    Delete expenses flexibly based on one or more filters.
    At least one filter must be provided.
    Filters are combined with AND logic.

    Examples:
    - delete by id: expense_id=5
    - delete by category: category='Food'
    - delete by date + category: date='2024-01-15', category='Food'
    - delete by amount: amount=500.0
    """
    if not any([expense_id, date, category, subcategory, amount]):
        return {"status": "error", "message": "At least one filter must be provided"}

    try:
        conditions = []
        params = []

        if expense_id is not None:
            conditions.append("id = ?")
            params.append(expense_id)
        if date is not None:
            conditions.append("date = ?")
            params.append(date)
        if category is not None:
            conditions.append("category = ?")
            params.append(category)
        if subcategory is not None:
            conditions.append("subcategory = ?")
            params.append(subcategory)
        if amount is not None:
            conditions.append("amount = ?")
            params.append(amount)

        query = f"DELETE FROM expenses WHERE {' AND '.join(conditions)}"

        with sqlite3.connect(DB_PATH) as c:
            cur = c.execute(query, params)
            deleted_count = cur.rowcount

        return {
            "status": "success",
            "deleted_count": deleted_count,
            "message": f"{deleted_count} expense(s) deleted successfully"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def summarize_by_category(start_date: str, end_date: str,
                       category: Optional[str] = None) -> list:
    """Summarize total expenses by category within an inclusive date range"""
    try:
        with sqlite3.connect(DB_PATH) as c:
            query = '''
                SELECT category,
                       SUM(amount * quantity)   AS total_amount,
                       SUM(quantity)            AS total_quantity,
                       COUNT(*)                 AS total_count,
                       AVG(amount * quantity)   AS avg_amount,
                       MIN(amount * quantity)   AS min_amount,
                       MAX(amount * quantity)   AS max_amount
                FROM expenses
                WHERE date BETWEEN ? AND ?
            '''
            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY category ORDER BY total_amount DESC"

            cur = c.execute(query, params)
            cols = [col[0] for col in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def summarize_by_subcategory(start_date: str, end_date: str,
                              category: Optional[str] = None) -> list:
    """Summarize total expenses by subcategory within an inclusive date range"""
    try:
        with sqlite3.connect(DB_PATH) as c:
            query = '''
                SELECT category,
                       subcategory,
                       SUM(amount * quantity)   AS total_amount,
                       SUM(quantity)            AS total_quantity,
                       COUNT(*)                 AS total_count,
                       AVG(amount * quantity)   AS avg_amount,
                       MIN(amount * quantity)   AS min_amount,
                       MAX(amount * quantity)   AS max_amount
                FROM expenses
                WHERE date BETWEEN ? AND ?
            '''
            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " GROUP BY category, subcategory ORDER BY category ASC, total_amount DESC"

            cur = c.execute(query, params)
            cols = [col[0] for col in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def summarize_by_date(start_date: str, end_date: str,
                      group_by: str = 'day') -> list:
    """
    Summarize total expenses grouped by date period.
    group_by options: 'day', 'month', 'year'
    """
    try:
        group_formats = {
            'day':   '%Y-%m-%d',
            'month': '%Y-%m',
            'year':  '%Y'
        }

        if group_by not in group_formats:
            return {"status": "error", "message": "group_by must be 'day', 'month', or 'year'"}

        fmt = group_formats[group_by]

        with sqlite3.connect(DB_PATH) as c:
            query = f'''
                SELECT strftime('{fmt}', date)  AS period,
                       SUM(amount * quantity)   AS total_amount,
                       SUM(quantity)            AS total_quantity,
                       COUNT(*)                 AS total_count,
                       AVG(amount * quantity)   AS avg_amount
                FROM expenses
                WHERE date BETWEEN ? AND ?
                GROUP BY period
                ORDER BY period ASC
            '''
            cur = c.execute(query, (start_date, end_date))
            cols = [col[0] for col in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)}


@mcp.tool()
def get_top_expenses(start_date: str, end_date: str,
                     limit: int = 10,
                     category: Optional[str] = None) -> list:
    """Get top N highest expenses within a date range"""
    try:
        with sqlite3.connect(DB_PATH) as c:
            query = '''
                SELECT id, date, amount, quantity,
                       ROUND(amount * quantity, 2) AS total,
                       category, subcategory, note
                FROM expenses
                WHERE date BETWEEN ? AND ?
            '''
            params = [start_date, end_date]

            if category:
                query += " AND category = ?"
                params.append(category)

            query += " ORDER BY (amount * quantity) DESC LIMIT ?"
            params.append(limit)

            cur = c.execute(query, params)
            cols = [col[0] for col in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ── Resource ───────────────────────────────────────────────────────────────────

@mcp.resource("expense://categories", mime_type="application/json")
def get_categories() -> str:
    """Read the list of categories and subcategories"""
    default_categories = {
        "categories": [
            "Food & Dining",
            "Transportation",
            "Shopping",
            "Entertainment",
            "Bills & Utilities",
            "Healthcare",
            "Travel",
            "Education",
            "Business",
            "Other"
        ]
    }
    try:
        with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return json.dumps(default_categories, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Entry Point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8002)