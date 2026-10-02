-- Demo-attack flag. Idempotent. Desk metrics keep these rows out of audit_live.
-- is_test stays independent: a break-it click is demo_attack, and is_test
-- only when the session is in test mode.
-- Reply drafts are audit rows that supersede themselves, so they stay in
-- audit_case without replacing the routing tip.

ALTER TABLE app.cases ADD COLUMN IF NOT EXISTS demo_attack boolean NOT NULL DEFAULT false;

ALTER TABLE app.audit_case ADD COLUMN IF NOT EXISTS demo_attack boolean NOT NULL DEFAULT false;

ALTER TABLE app.audit_llm_call ADD COLUMN IF NOT EXISTS demo_attack boolean NOT NULL DEFAULT false;

ALTER TABLE app.cases ADD COLUMN IF NOT EXISTS reply_draft text;

ALTER TABLE app.cases ADD COLUMN IF NOT EXISTS reply_sent text;

CREATE OR REPLACE VIEW app.audit_live
WITH (security_invoker = true) AS
SELECT cur.*
FROM app.audit_current AS cur
WHERE cur.eval_run_id IS NULL
  AND NOT EXISTS (
    SELECT 1 FROM app.audit_case AS src
    WHERE src.audit_id = cur.audit_id AND src.is_test
  )
  AND NOT EXISTS (
    SELECT 1 FROM app.audit_case AS src
    WHERE src.audit_id = cur.audit_id AND src.demo_attack
  )
  AND NOT EXISTS (
    SELECT 1 FROM app.cases AS marked_case
    WHERE marked_case.case_id = cur.case_id AND marked_case.demo_attack
  )
  AND NOT EXISTS (
    SELECT 1 FROM app.test_cases AS marked
    WHERE marked.case_id = cur.case_id
  );

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON app.audit_live FROM app_rw;
GRANT SELECT ON app.audit_live TO app_rw;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eval_rw') THEN
    GRANT SELECT ON app.audit_live TO eval_rw;
  END IF;
END $$;
