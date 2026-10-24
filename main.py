
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sqlite3


# ---------- Domain model ----------

@dataclass(frozen=True)
class Expense:
    amount_paise: int
    category: str
    expense_date: date
    description: str = ""

    def __post_init__(self):
        if self.amount_paise <= 0:
            raise ValueError("Amount must be greater than zero.")

        if not self.category.strip():
            raise ValueError("Category cannot be empty.")

        if len(self.category.strip()) > 50:
            raise ValueError("Category cannot exceed 50 characters.")

        if len(self.description) > 500:
            raise ValueError("Description cannot exceed 500 characters.")

    @classmethod
    def create(cls, amount, category, expense_date, description=""):
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, ValueError):
            raise ValueError("Enter a valid amount.") from None

        if not value.is_finite() or value <= 0:
            raise ValueError("Amount must be positive and finite.")

        paise = value * 100
        if paise != paise.to_integral_value():
            raise ValueError("Amount cannot have more than 2 decimal places.")

        try:
            parsed_date = date.fromisoformat(expense_date)
        except (ValueError, TypeError):
            raise ValueError("Date must be YYYY-MM-DD.") from None

        return cls(
            amount_paise=int(paise),
            category=category.strip(),
            expense_date=parsed_date,
            description=description.strip(),
        )

    @property
    def amount(self):
        return Decimal(self.amount_paise) / 100


# ---------- Persistence layer ----------

class ExpenseRepository:
    def __init__(self, database_path="expenses.db"):
        self.database_path = str(database_path)
        self._initialize_database()

    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_database(self):
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS expenses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    amount_paise INTEGER NOT NULL CHECK (amount_paise > 0),
                    category TEXT NOT NULL CHECK (length(trim(category)) > 0),
                    expense_date TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT ''
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_expenses_date
                ON expenses(expense_date)
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS idx_expenses_category
                ON expenses(category)
            """)

    def add(self, expense):
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO expenses
                    (amount_paise, category, expense_date, description)
                VALUES (?, ?, ?, ?)
                """,
                (
                    expense.amount_paise,
                    expense.category,
                    expense.expense_date.isoformat(),
                    expense.description,
                ),
            )
            return cursor.lastrowid

    def list_all(self):
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT amount_paise, category, expense_date, description
                FROM expenses
                ORDER BY expense_date DESC, id DESC
            """).fetchall()

        return [self._to_expense(row) for row in rows]

    def filter_by_category(self, category):
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT amount_paise, category, expense_date, description
                FROM expenses
                WHERE category = ? COLLATE NOCASE
                ORDER BY expense_date DESC, id DESC
                """,
                (category.strip(),),
            ).fetchall()

        return [self._to_expense(row) for row in rows]

    def calculate_total(self):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(amount_paise), 0) AS total "
                "FROM expenses"
            ).fetchone()
        return row["total"]

    def category_summary(self):
        with self._connect() as connection:
            rows = connection.execute("""
                SELECT category, SUM(amount_paise) AS total
                FROM expenses
                GROUP BY category
                ORDER BY total DESC
            """).fetchall()

        return {row["category"]: row["total"] for row in rows}

    @staticmethod
    def _to_expense(row):
        return Expense(
            amount_paise=row["amount_paise"],
            category=row["category"],
            expense_date=date.fromisoformat(row["expense_date"]),
            description=row["description"],
        )


# ---------- Business logic ----------

class ExpenseService:
    def __init__(self, repository):
        self._repository = repository

    def add_expense(self, amount, category, expense_date, description=""):
        expense = Expense.create(
            amount, category, expense_date, description
        )
        return self._repository.add(expense)

    def get_expenses(self):
        return self._repository.list_all()

    def get_by_category(self, category):
        if not category.strip():
            raise ValueError("Category cannot be empty.")
        return self._repository.filter_by_category(category)

    def get_total(self):
        return self._repository.calculate_total()

    def get_category_summary(self):
        return self._repository.category_summary()


# ---------- User interface ----------

class ExpenseTrackerApp:
    def __init__(self, service):
        self._service = service

    @staticmethod
    def _format_money(paise):
        return f"₹{Decimal(paise) / 100:,.2f}"

    def run(self):
        while True:
            print("\n=== Expense Tracker ===")
            print("1. Add expense")
            print("2. List expenses")
            print("3. Total expenses")
            print("4. Category summary")
            print("5. Filter by category")
            print("0. Exit")

            choice = input("Choose an option: ").strip()

            try:
                if choice == "1":
                    self._add_expense()
                elif choice == "2":
                    self._list_expenses(self._service.get_expenses())
                elif choice == "3":
                    print("Total:", self._format_money(
                        self._service.get_total()
                    ))
                elif choice == "4":
                    for category, total in (
                        self._service.get_category_summary().items()
                    ):
                        print(category, self._format_money(total))
                elif choice == "5":
                    category = input("Category: ")
                    self._list_expenses(
                        self._service.get_by_category(category)
                    )
                elif choice == "0":
                    print("Goodbye!")
                    break
                else:
                    print("Invalid choice.")
            except (ValueError, sqlite3.Error) as error:
                print("Error:", error)

    def _add_expense(self):
        amount = input("Amount (e.g. 250.50): ")
        category = input("Category: ")
        expense_date = input("Date (YYYY-MM-DD): ")
        description = input("Description: ")

        expense_id = self._service.add_expense(
            amount, category, expense_date, description
        )
        print(f"Expense saved. ID: {expense_id}")

    def _list_expenses(self, expenses):
        if not expenses:
            print("No expenses found.")
            return

        for expense in expenses:
            print(
                f"{expense.expense_date} | {expense.category} | "
                f"{self._format_money(expense.amount_paise)} | "
                f"{expense.description}"
            )


def main():
    database_path = Path(__file__).with_name("expenses.db")
    repository = ExpenseRepository(database_path)
    service = ExpenseService(repository)
    app = ExpenseTrackerApp(service)
    app.run()


if __name__ == "__main__":
    main()
