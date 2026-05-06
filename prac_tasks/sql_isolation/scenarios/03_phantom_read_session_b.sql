-- Phantom read, session B.
-- Выполнять после A1 из 03_phantom_read_session_a.sql.

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

INSERT INTO orders (customer_name, amount, status)
VALUES ('Carol', 90, 'new');

COMMIT;

SELECT 'B1: inserted and committed new order' AS step, id, customer_name, amount, status
FROM orders
WHERE customer_name = 'Carol';
