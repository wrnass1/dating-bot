-- Phantom read, session A.
-- Перед сценарием выполнить sql/00_schema.sql.

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'A1: first count of new orders' AS step, COUNT(*) AS new_orders
FROM orders
WHERE status = 'new';

-- Пауза: теперь выполнить весь файл 03_phantom_read_session_b.sql.

SELECT 'A2: second count in same transaction' AS step, COUNT(*) AS new_orders
FROM orders
WHERE status = 'new';

SELECT 'A3: visible rows' AS step, id, customer_name, amount, status
FROM orders
WHERE status = 'new'
ORDER BY id;

COMMIT;
