-- Judge console actions store source = 'judge' on app.audit_case.
-- Nullable text, default NULL. Public chat rows stay NULL.
-- Idempotent. Apply as the database owner. The app does not run this file.
-- source is appended as the last column of app.audit_live.
-- CREATE OR REPLACE cannot reorder or drop columns. Do not replace
-- app.audit_current and do not change grants on the audit tables.
-- Rows tagged by the judge console stay in this view.

ALTER TABLE app.audit_case ADD COLUMN IF NOT EXISTS source text DEFAULT NULL;

-- Keep the column list app.audit_live already has (cur.* plus demo_attack
-- from 004). source is appended at the end.
CREATE OR REPLACE VIEW app.audit_live
WITH (security_invoker = true) AS
SELECT cur.*,
       EXISTS (
         SELECT 1 FROM app.audit_case AS flagged
         WHERE flagged.audit_id = cur.audit_id AND flagged.demo_attack
       ) AS demo_attack,
       (
         SELECT origin.source
         FROM app.audit_case AS origin
         WHERE origin.audit_id = cur.audit_id
       ) AS source
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
