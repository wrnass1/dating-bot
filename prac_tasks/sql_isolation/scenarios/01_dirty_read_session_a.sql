-- Dirty read, session A.
-- Перед сценарием выполнить sql/00_schema.sql.

SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

SELECT 'A1: initial balance' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;

-- Пауза: теперь выполнить B1-B2 из 01_dirty_read_session_b.sql.

SELECT 'A2: dirty read, B has not committed yet' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;

-- Пауза: теперь выполнить B3 ROLLBACK.

SELECT 'A3: after B rollback' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;

COMMIT;
