-- Test-traffic flag and the desk's live audit view. Idempotent.
-- The app applies this on startup when the connected role can change app
-- objects. Otherwise apply it yourself as the database owner, the same way
-- as 001. is_test is written only when a row is inserted.
-- This file does not replace app.audit_current and does not change grants
-- on the audit tables. The eval runner keeps reading that view.
-- Desk metrics read app.audit_live.

ALTER TABLE app.cases ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false;

ALTER TABLE app.audit_case ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false;

ALTER TABLE app.audit_llm_call ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS app.test_cases (
  case_id text PRIMARY KEY,
  marked_at timestamptz NOT NULL DEFAULT now(),
  reason text
);

ALTER TABLE app.test_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.test_cases FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS test_cases_app_rw_select ON app.test_cases;
DROP POLICY IF EXISTS test_cases_app_rw_insert ON app.test_cases;
CREATE POLICY test_cases_app_rw_select ON app.test_cases FOR SELECT TO app_rw USING (true);
CREATE POLICY test_cases_app_rw_insert ON app.test_cases FOR INSERT TO app_rw WITH CHECK (true);

GRANT SELECT, INSERT ON app.test_cases TO app_rw;
REVOKE UPDATE, DELETE ON app.test_cases FROM app_rw;

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
    SELECT 1 FROM app.test_cases AS marked
    WHERE marked.case_id = cur.case_id
  );

GRANT SELECT ON app.audit_live TO app_rw;

-- security_invoker on audit_live also needs SELECT on test_cases, or a
-- marked case id is invisible to the caller and leaks into the view.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eval_rw') THEN
    GRANT USAGE ON SCHEMA app TO eval_rw;
    GRANT SELECT ON app.audit_live TO eval_rw;
    GRANT SELECT ON app.test_cases TO eval_rw;
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'app' AND tablename = 'test_cases' AND policyname = 'test_cases_eval_rw_select'
    ) THEN
      CREATE POLICY test_cases_eval_rw_select ON app.test_cases
        FOR SELECT TO eval_rw USING (true);
    END IF;
  END IF;
END $$;
