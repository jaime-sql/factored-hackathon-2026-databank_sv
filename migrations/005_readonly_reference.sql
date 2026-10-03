-- app_rw may read reference prices and assumptions, and nothing else on them.
-- Idempotent. Apply as the database owner. The app does not run this file.
-- Does not change grants for any other table or role.

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON app.llm_price, app.analytics_assumption FROM app_rw;

GRANT SELECT ON app.llm_price, app.analytics_assumption TO app_rw;
