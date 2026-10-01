-- Test-traffic flag. Idempotent. The app applies this on startup when the
-- connected role is allowed to alter app tables. Otherwise apply it yourself
-- as the database owner, the same way as 001. The app does not delete rows.

ALTER TABLE app.cases ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false;

ALTER TABLE app.audit_case ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false;

ALTER TABLE app.audit_llm_call ADD COLUMN IF NOT EXISTS is_test boolean NOT NULL DEFAULT false;

CREATE OR REPLACE VIEW app.audit_current
WITH (security_invoker = true) AS
SELECT a.*
FROM app.audit_case AS a
WHERE NOT EXISTS (
  SELECT 1
  FROM app.audit_case AS newer
  WHERE newer.supersedes_audit_id = a.audit_id
);

CREATE OR REPLACE VIEW app.audit_llm_call_current
WITH (security_invoker = true) AS
SELECT a.*
FROM app.audit_llm_call AS a
WHERE NOT EXISTS (
  SELECT 1
  FROM app.audit_llm_call AS newer
  WHERE newer.supersedes_audit_id = a.audit_id
);

GRANT SELECT ON app.audit_current TO app_rw;
GRANT SELECT ON app.audit_llm_call_current TO app_rw;
