-- Dirty read, session B.
-- Выполнять после A1 из 01_dirty_read_session_a.sql.

SET SESSION TRANSACTION ISOLATION LEVEL READ UNCOMMITTED;
START TRANSACTION;

UPDATE accounts
SET balance = 50
WHERE id = 1;

SELECT 'B1: changed balance but not committed' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;

-- Пауза: теперь выполнить A2.

ROLLBACK;

SELECT 'B2: rolled back, real balance again' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;
