import os
import time
from datetime import datetime
from decimal import Decimal

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError


def env(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None or v == "":
        raise RuntimeError(f"Missing required env var: {name}")
    return v


def wait_for_db(engine, timeout_s: int = 60) -> None:
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


def seed_minimal(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(SCHEMA_SQL))

        # Seed customers
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

        # Seed products
        for name, price in [
            ("Keyboard", Decimal("50.00")),
            ("Mouse", Decimal("25.00")),
            ("Monitor", Decimal("200.00")),
        ]:
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


def scenario_1_place_order(engine) -> int:
    """
    Scenario 1:
      1) Insert into Orders
      2) Insert rows into OrderItems with Quantity + Subtotal
      3) Update Orders.TotalAmount = SUM(OrderItems.Subtotal)
    """
    customer_email = "ivan.petrov@example.com"

    # Example order: 2x Keyboard, 1x Mouse
    items = [
        {"product_name": "Keyboard", "qty": 2},
        {"product_name": "Mouse", "qty": 1},
    ]

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

        for item in items:
            product = conn.execute(
                text(
                    """
                    SELECT ProductID, Price
                    FROM Products
                    WHERE ProductName = :name
                    FOR UPDATE
                    """
                ),
                {"name": item["product_name"]},
            ).mappings().one()

            subtotal = (Decimal(product["price"]) * Decimal(item["qty"])).quantize(Decimal("0.01"))
            conn.execute(
                text(
                    """
                    INSERT INTO OrderItems (OrderID, ProductID, Quantity, Subtotal)
                    VALUES (:oid, :pid, :qty, :subtotal)
                    """
                ),
                {"oid": order_id, "pid": product["productid"], "qty": item["qty"], "subtotal": subtotal},
            )

        total = conn.execute(
            text("SELECT COALESCE(SUM(Subtotal), 0) FROM OrderItems WHERE OrderID = :oid"),
            {"oid": order_id},
        ).scalar_one()

        conn.execute(
            text("UPDATE Orders SET TotalAmount = :total WHERE OrderID = :oid"),
            {"total": total, "oid": order_id},
        )

    return int(order_id)


def scenario_2_update_customer_email(engine) -> None:
    """
    Scenario 2:
      Atomic update of customer email.
    """
    old_email = "ivan.petrov@example.com"
    new_email = "ivan.petrov+updated@example.com"

    with engine.begin() as conn:
        # Lock whichever record exists (old or already-updated email)
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


def scenario_3_add_product(engine) -> int:
    """
    Scenario 3:
      Atomic insert of a new product.
    """
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
            {"name": "USB-C Cable", "price": Decimal("9.99")},
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
    db_url = env("DATABASE_URL")
    engine = create_engine(db_url, pool_pre_ping=True, future=True)
    wait_for_db(engine, timeout_s=int(os.getenv("DB_WAIT_TIMEOUT_S", "60")))

    seed_minimal(engine)

    print("\n--- Scenario 1: place order (transaction) ---")
    order_id = scenario_1_place_order(engine)
    print_state(engine, order_id=order_id)

    print("\n--- Scenario 2: update customer email (transaction) ---")
    scenario_2_update_customer_email(engine)
    print_state(engine, order_id=order_id)

    print("\n--- Scenario 3: add product (transaction) ---")
    pid = scenario_3_add_product(engine)
    print(f"\nInserted product id: {pid}")
    print_state(engine, order_id=order_id)


if __name__ == "__main__":
    main()

