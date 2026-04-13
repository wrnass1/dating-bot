import os
import time
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS Customers (
  CustomerID  SERIAL PRIMARY KEY,
  FirstName   TEXT NOT NULL,
  LastName    TEXT NOT NULL,
  Email       TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS Products (
  ProductID    SERIAL PRIMARY KEY,
  ProductName  TEXT NOT NULL,
  Price        NUMERIC(12,2) NOT NULL CHECK (Price >= 0),
  UNIQUE (ProductName)
);

CREATE TABLE IF NOT EXISTS Orders (
  OrderID      SERIAL PRIMARY KEY,
  CustomerID   INTEGER NOT NULL REFERENCES Customers(CustomerID),
  OrderDate    TIMESTAMP NOT NULL,
  TotalAmount  NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (TotalAmount >= 0)
);

CREATE TABLE IF NOT EXISTS OrderItems (
  OrderItemID  SERIAL PRIMARY KEY,
  OrderID      INTEGER NOT NULL REFERENCES Orders(OrderID) ON DELETE CASCADE,
  ProductID    INTEGER NOT NULL REFERENCES Products(ProductID),
  Quantity     INTEGER NOT NULL CHECK (Quantity > 0),
  Subtotal     NUMERIC(12,2) NOT NULL CHECK (Subtotal >= 0)
);
"""


def must_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if not value:
        raise RuntimeError(f"Missing required env var: {name}")
    return value


def wait_for_db(engine, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    last_err: Exception | None = None
    while time.time() < deadline:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except OperationalError as e:
            last_err = e
            time.sleep(1)
    raise RuntimeError(f"DB not ready after {timeout_s}s: {last_err}")


def seed(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(SCHEMA_SQL))

        conn.execute(
            text(
                """
                INSERT INTO Customers (FirstName, LastName, Email)
                VALUES (:fn, :ln, :email)
                ON CONFLICT (Email) DO NOTHING
                """
            ),
            {"fn": "Ivan", "ln": "Petrov", "email": "ivan.petrov@example.com"},
        )

        base_products = [
            ("Keyboard", Decimal("50.00")),
            ("Mouse", Decimal("25.00")),
            ("Monitor", Decimal("200.00")),
        ]
        for name, price in base_products:
            conn.execute(
                text(
                    """
                    INSERT INTO Products (ProductName, Price)
                    VALUES (:name, :price)
                    ON CONFLICT (ProductName) DO NOTHING
                    """
                ),
                {"name": name, "price": price},
            )


def money(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


def place_order(engine, customer_email: str, items: list[tuple[str, int]]) -> int:
    if not items:
        raise ValueError("Order must contain at least one item")

    with engine.begin() as conn:
        customer_id = conn.execute(
            text("SELECT CustomerID FROM Customers WHERE Email = :email FOR UPDATE"),
            {"email": customer_email},
        ).scalar_one()

        order_id = conn.execute(
            text(
                """
                INSERT INTO Orders (CustomerID, OrderDate, TotalAmount)
                VALUES (:cid, :od, 0)
                RETURNING OrderID
                """
            ),
            {"cid": customer_id, "od": datetime.utcnow()},
        ).scalar_one()

        total = Decimal("0.00")
        for product_name, qty in items:
            row = conn.execute(
                text(
                    """
                    SELECT ProductID AS product_id, Price AS price
                    FROM Products
                    WHERE ProductName = :name
                    FOR UPDATE
                    """
                ),
                {"name": product_name},
            ).mappings().one()

            subtotal = money(Decimal(row["price"]) * Decimal(qty))
            total += subtotal
            conn.execute(
                text(
                    """
                    INSERT INTO OrderItems (OrderID, ProductID, Quantity, Subtotal)
                    VALUES (:oid, :pid, :qty, :subtotal)
                    """
                ),
                {"oid": order_id, "pid": row["product_id"], "qty": qty, "subtotal": subtotal},
            )

        conn.execute(
            text("UPDATE Orders SET TotalAmount = :total WHERE OrderID = :oid"),
            {"total": money(total), "oid": order_id},
        )

    return int(order_id)


def update_customer_email(engine, old_email: str, new_email: str) -> None:
    with engine.begin() as conn:
        customer_id = conn.execute(
            text(
                """
                SELECT CustomerID
                FROM Customers
                WHERE Email IN (:old_email, :new_email)
                ORDER BY (Email = :new_email) DESC
                LIMIT 1
                FOR UPDATE
                """
            ),
            {"old_email": old_email, "new_email": new_email},
        ).scalar_one()

        conn.execute(
            text("UPDATE Customers SET Email = :new_email WHERE CustomerID = :cid"),
            {"new_email": new_email, "cid": customer_id},
        )


def upsert_product(engine, name: str, price: Decimal) -> int:
    with engine.begin() as conn:
        product_id = conn.execute(
            text(
                """
                INSERT INTO Products (ProductName, Price)
                VALUES (:name, :price)
                ON CONFLICT (ProductName) DO UPDATE SET Price = EXCLUDED.Price
                RETURNING ProductID
                """
            ),
            {"name": name, "price": money(price)},
        ).scalar_one()
    return int(product_id)


def print_state(engine, order_id: int | None = None) -> None:
    with engine.connect() as conn:
        customers = conn.execute(
            text("SELECT CustomerID, FirstName, LastName, Email FROM Customers ORDER BY CustomerID")
        ).mappings().all()
        products = conn.execute(
            text("SELECT ProductID, ProductName, Price FROM Products ORDER BY ProductID")
        ).mappings().all()

        print("\nCustomers:")
        for c in customers:
            print(dict(c))

        print("\nProducts:")
        for p in products:
            print(dict(p))

        if order_id is not None:
            order = conn.execute(
                text("SELECT OrderID, CustomerID, OrderDate, TotalAmount FROM Orders WHERE OrderID = :oid"),
                {"oid": order_id},
            ).mappings().one()
            items = conn.execute(
                text(
                    """
                    SELECT oi.OrderItemID, oi.ProductID, p.ProductName, oi.Quantity, oi.Subtotal
                    FROM OrderItems oi
                    JOIN Products p ON p.ProductID = oi.ProductID
                    WHERE oi.OrderID = :oid
                    ORDER BY oi.OrderItemID
                    """
                ),
                {"oid": order_id},
            ).mappings().all()

            print("\nOrder:")
            print(dict(order))
            print("\nOrderItems:")
            for it in items:
                print(dict(it))


def main() -> None:
    db_url = must_env("DATABASE_URL")
    engine = create_engine(db_url, pool_pre_ping=True, future=True)
    wait_for_db(engine, timeout_s=int(os.getenv("DB_WAIT_TIMEOUT_S", "60")))

    seed(engine)

    print("\n Сценарий 1: размещение заказа (транзакция)")
    order_id = place_order(
        engine,
        customer_email="ivan.petrov@example.com",
        items=[("Keyboard", 2), ("Mouse", 1)],
    )
    print_state(engine, order_id=order_id)

    print("\n Сценарий 2: обновление email клиента (транзакция)")
    update_customer_email(
        engine,
        old_email="ivan.petrov@example.com",
        new_email="ivan.petrov+updated@example.com",
    )
    print_state(engine, order_id=order_id)

    print("\n--- Scenario 3: add product (transaction) ---")
    pid = upsert_product(engine, name="USB-C Cable", price=Decimal("9.99"))
    print(f"\nInserted product id: {pid}")
    print_state(engine, order_id=order_id)


if __name__ == "__main__":
    main()

