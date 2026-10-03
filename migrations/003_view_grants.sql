-- app_rw may read the audit views and nothing else on them.
-- Idempotent. Does not change default privileges or grants for other roles.
-- The app applies this on startup when the connected role can.
-- Otherwise apply it yourself as the database owner.

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON app.audit_current, app.audit_live, app.audit_llm_call_current FROM app_rw;

GRANT SELECT ON app.audit_current, app.audit_live, app.audit_llm_call_current TO app_rw;
