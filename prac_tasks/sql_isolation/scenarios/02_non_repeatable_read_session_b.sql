-- Non-repeatable read, session B.
-- Выполнять после A1 из 02_non_repeatable_read_session_a.sql.

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

UPDATE accounts
SET balance = 150
WHERE id = 1;

COMMIT;

SELECT 'B1: committed new balance' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;
