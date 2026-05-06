-- Non-repeatable read, session A.
-- Перед сценарием выполнить sql/00_schema.sql.

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT 'A1: first read' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;

-- Пауза: теперь выполнить весь файл 02_non_repeatable_read_session_b.sql.

SELECT 'A2: second read in same transaction' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;

COMMIT;
