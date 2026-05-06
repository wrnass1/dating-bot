DROP TABLE IF EXISTS audit_events;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS accounts;

CREATE TABLE accounts (
  id INT PRIMARY KEY,
  owner_name VARCHAR(100) NOT NULL,
  balance INT NOT NULL,
  CHECK (balance >= 0)
) ENGINE = InnoDB;

CREATE TABLE orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  customer_name VARCHAR(100) NOT NULL,
  amount INT NOT NULL,
  status VARCHAR(20) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;

CREATE TABLE audit_events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  event_name VARCHAR(100) NOT NULL,
  details VARCHAR(255) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;

INSERT INTO accounts (id, owner_name, balance) VALUES
  (1, 'Alice', 100),
  (2, 'Bob', 200);

INSERT INTO orders (customer_name, amount, status) VALUES
  ('Alice', 40, 'new'),
  ('Bob', 70, 'paid');

INSERT INTO audit_events (event_name, details) VALUES
  ('setup', 'Initial data loaded');

SELECT 'schema is ready' AS result;
SELECT * FROM accounts ORDER BY id;
SELECT * FROM orders ORDER BY id;
