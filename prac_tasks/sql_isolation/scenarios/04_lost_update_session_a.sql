-- Lost update, session A.
-- Перед сценарием выполнить sql/00_schema.sql.

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance INTO @old_balance_a
FROM accounts
WHERE id = 1;

SELECT 'A1: read balance into local variable' AS step, @old_balance_a AS old_balance;

-- Пауза: теперь выполнить B1 из 04_lost_update_session_b.sql.

UPDATE accounts
SET balance = @old_balance_a + 10
WHERE id = 1;

SELECT 'A2: wrote old_balance + 10' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;

COMMIT;

SELECT 'A3: committed' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;

-- Пауза: теперь выполнить B2-B4.
