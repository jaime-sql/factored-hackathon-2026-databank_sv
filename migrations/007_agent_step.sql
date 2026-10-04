-- One row per AI agent step (tool call, final answer, or fallback). Append-only.
-- Idempotent. Apply as the database owner. The app never runs this file;
-- a missing table only skips the step rows and the agent keeps answering.
-- No customer text is stored here: tool name, counts, timings and flags only.

CREATE TABLE IF NOT EXISTS app.audit_agent_step (
  audit_id text PRIMARY KEY,
  conversation_id text NOT NULL,
  case_id text,
  step integer NOT NULL,
  tool text NOT NULL,
  tokens_in integer NOT NULL DEFAULT 0,
  tokens_out integer NOT NULL DEFAULT 0,
  latency_ms integer NOT NULL DEFAULT 0,
  fallback boolean NOT NULL DEFAULT false,
  outcome text,
  model text,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  is_test boolean NOT NULL DEFAULT false,
  is_eval_case boolean NOT NULL DEFAULT false,
  eval_run_id text
);

CREATE INDEX IF NOT EXISTS audit_agent_step_conversation_idx
  ON app.audit_agent_step (conversation_id);

ALTER TABLE app.audit_agent_step ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.audit_agent_step FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS audit_agent_step_app_rw_select ON app.audit_agent_step;
DROP POLICY IF EXISTS audit_agent_step_app_rw_insert ON app.audit_agent_step;
CREATE POLICY audit_agent_step_app_rw_select ON app.audit_agent_step
  FOR SELECT TO app_rw USING (true);
CREATE POLICY audit_agent_step_app_rw_insert ON app.audit_agent_step
  FOR INSERT TO app_rw WITH CHECK (true);

GRANT SELECT, INSERT ON app.audit_agent_step TO app_rw;
REVOKE UPDATE, DELETE, TRUNCATE ON app.audit_agent_step FROM app_rw;
