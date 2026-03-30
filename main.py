from fastmcp import FastMCP
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'expenses.db')
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), 'categories.json')

mcp = FastMCP("Expense Tracker Server")

def init_db():
    with sqlite3.connect(DB_PATH) as c:
        c.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        ''')

init_db()

@mcp.tool()
def add_expense(date: str, amount: float, category: str, subcategory: str, note: str = '') -> str:
    """Add a new expense entry to the database"""
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute('''
            INSERT INTO expenses (date, amount, category, subcategory, note)
            VALUES (?, ?, ?, ?, ?)
        ''', 
        (date, amount, category, subcategory, note)
        )
    return {"status": "success", "id:": cur.lastrowid}


@mcp.tool()
def get_expenses(start_date: str, end_date: str):
    """Retrieve all expense entries within an inclusive date range from the database"""
    with sqlite3.connect(DB_PATH) as c:
        cur = c.execute('''
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY id ASC
        ''', (start_date, end_date)
        )
        cols = [col[0] for col in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@mcp.tool()
def summarize_expenses(start_date: str, end_date: str, category: str = None):
    """Summarize total expenses by category within an inclusive date range"""
    with sqlite3.connect(DB_PATH) as c:
        query = ('''
            SELECT category, SUM(amount) as total_amount
            FROM expenses
            WHERE date BETWEEN ? AND ?
        ''')

        params = [start_date, end_date]

        if category:
            query += ' AND category = ?'
            params.append(category)

        query += ' GROUP BY category ORDER BY category ASC'
        cur = c.execute(query, params)
        cols = [col[0] for col in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


@mcp.resource("expense://categories", mime_type="application/json")
def get_categories():
    """Read the list of categories and subcategories from a JSON file and return it as a dictionary"""
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return f.read()

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8002)