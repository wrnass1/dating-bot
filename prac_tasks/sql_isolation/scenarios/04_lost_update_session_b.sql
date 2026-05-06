-- Lost update, session B.
-- Выполнять параллельно с 04_lost_update_session_a.sql.

SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;
START TRANSACTION;

SELECT balance INTO @old_balance_b
FROM accounts
WHERE id = 1;

SELECT 'B1: read balance into local variable' AS step, @old_balance_b AS old_balance;

-- Пауза: теперь выполнить A2-A3.

UPDATE accounts
SET balance = @old_balance_b + 20
WHERE id = 1;

SELECT 'B2: wrote stale old_balance + 20' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;

COMMIT;

SELECT 'B3: final value, A update is lost' AS step, id, owner_name, balance
FROM accounts
WHERE id = 1;
