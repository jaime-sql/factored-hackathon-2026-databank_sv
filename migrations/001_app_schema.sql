-- Harbor Desk application schema.
-- Apply this yourself as the database owner. The app does not run it.
-- The app connects as app_rw (LOGIN, no BYPASSRLS). Put that role's URL in
-- Cloud Run Secret Manager. Do not commit the URL.
-- app_rw can read public data tables and cannot write them.
-- app_rw has no grant on the eval schema.
-- Audit tables are append-only: INSERT and SELECT only.
-- Case and handoff tables allow UPDATE. Nothing allows DELETE.

CREATE SCHEMA IF NOT EXISTS app;

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_rw') THEN
    CREATE ROLE app_rw NOINHERIT LOGIN;
  END IF;
END $$;

ALTER ROLE app_rw SET statement_timeout = '15s';
ALTER ROLE app_rw SET search_path = app, public;

GRANT USAGE ON SCHEMA app TO app_rw;
GRANT USAGE ON SCHEMA public TO app_rw;

GRANT SELECT ON
  public.customers,
  public.transactions,
  public.fraud_features,
  public.synthetic_duplicates,
  public.meta
TO app_rw;

REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON
  public.customers,
  public.transactions,
  public.fraud_features,
  public.synthetic_duplicates,
  public.meta
FROM app_rw;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'eval') THEN
    EXECUTE 'REVOKE ALL ON SCHEMA eval FROM app_rw';
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA eval FROM app_rw';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS app.cases (
  case_id text PRIMARY KEY,
  customer_key text NOT NULL,
  transaction_key text,
  state text NOT NULL,
  language text NOT NULL,
  case_type text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  latest_audit_id text,
  is_eval_case boolean NOT NULL DEFAULT false,
  eval_run_id text,
  case_source text,
  CONSTRAINT cases_case_source_known CHECK (
    case_source IS NULL OR case_source IN (
      'sample', 'synthetic_dup', 'red_team', 'ood_sv_text', 'pt_translated'
    )
  )
);

CREATE TABLE IF NOT EXISTS app.audit_case (
  audit_id text PRIMARY KEY,
  case_id text NOT NULL,
  supersedes_audit_id text REFERENCES app.audit_case (audit_id),
  recorded_at timestamptz NOT NULL DEFAULT now(),
  case_type text NOT NULL,
  customer_segment text,
  final_resolution_status text,
  case_created_at timestamptz NOT NULL,
  case_closed_at timestamptz,
  decision text,
  automation_attempted boolean NOT NULL,
  handoff_reason text,
  handoff_packet_complete boolean,
  language text NOT NULL,
  country text,
  accent_group text,
  rule_or_model_version text,
  prompt_version text,
  fraud_score numeric,
  model_risk_score numeric,
  guardrail_flags text[] NOT NULL DEFAULT '{}',
  is_eval_case boolean NOT NULL DEFAULT false,
  eval_run_id text,
  case_source text,
  CONSTRAINT audit_case_source_known CHECK (
    case_source IS NULL OR case_source IN (
      'sample', 'synthetic_dup', 'red_team', 'ood_sv_text', 'pt_translated'
    )
  )
);

CREATE INDEX IF NOT EXISTS audit_case_case_id_idx ON app.audit_case (case_id);
CREATE INDEX IF NOT EXISTS audit_case_supersedes_idx ON app.audit_case (supersedes_audit_id);

CREATE TABLE IF NOT EXISTS app.audit_llm_call (
  audit_id text PRIMARY KEY,
  llm_call_id text NOT NULL,
  case_id text NOT NULL,
  supersedes_audit_id text REFERENCES app.audit_llm_call (audit_id),
  recorded_at timestamptz NOT NULL DEFAULT now(),
  case_type text,
  model text NOT NULL,
  input_tokens integer NOT NULL DEFAULT 0,
  output_tokens integer NOT NULL DEFAULT 0,
  latency_ms integer NOT NULL DEFAULT 0,
  call_started_at timestamptz NOT NULL,
  call_purpose text NOT NULL,
  call_status text NOT NULL,
  retry_attempt smallint NOT NULL DEFAULT 0,
  prompt_version text,
  is_eval_case boolean NOT NULL DEFAULT false,
  eval_run_id text
);

CREATE INDEX IF NOT EXISTS audit_llm_call_case_id_idx ON app.audit_llm_call (case_id);

CREATE TABLE IF NOT EXISTS app.audit_event (
  audit_id text PRIMARY KEY,
  case_id text NOT NULL,
  supersedes_audit_id text REFERENCES app.audit_event (audit_id),
  recorded_at timestamptz NOT NULL DEFAULT now(),
  trace_id text NOT NULL,
  kind text NOT NULL,
  name text NOT NULL,
  detail_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  verification_status text
);

CREATE INDEX IF NOT EXISTS audit_event_case_id_idx ON app.audit_event (case_id);

CREATE TABLE IF NOT EXISTS app.handoff (
  handoff_id text PRIMARY KEY,
  case_id text NOT NULL UNIQUE,
  status text NOT NULL,
  packet jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  claimed_by text,
  resolution_note text
);

CREATE TABLE IF NOT EXISTS app.confirmation (
  confirmation_id text PRIMARY KEY,
  case_id text NOT NULL,
  action text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (case_id, action)
);

CREATE TABLE IF NOT EXISTS app.card_block (
  block_id text PRIMARY KEY,
  case_id text NOT NULL,
  customer_key text NOT NULL,
  product_key text NOT NULL,
  transaction_key text NOT NULL,
  status text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS app.llm_price (
  model text NOT NULL,
  usd_per_1m_input numeric NOT NULL,
  usd_per_1m_output numeric NOT NULL,
  effective_from date NOT NULL,
  source_url text NOT NULL,
  PRIMARY KEY (model, effective_from)
);

CREATE TABLE IF NOT EXISTS app.analytics_assumption (
  key text PRIMARY KEY,
  value numeric NOT NULL,
  note text NOT NULL
);

-- Latest row in each supersession chain. The eval runner joins labels on case_id.
-- security_invoker keeps RLS of the caller (app_rw) in force for console queries.
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

INSERT INTO app.llm_price (model, usd_per_1m_input, usd_per_1m_output, effective_from, source_url)
VALUES
  ('gpt-4o-mini', 0.15, 0.60, DATE '2026-09-29', 'https://openai.com/api/pricing/'),
  ('openai/gpt-4o-mini', 0.15, 0.60, DATE '2026-09-29', 'https://openrouter.ai/models')
ON CONFLICT (model, effective_from) DO NOTHING;

INSERT INTO app.analytics_assumption (key, value, note) VALUES
  ('wage_low_usd_per_hour', 6, 'ASSUMPTION from cost projection'),
  ('wage_mid_usd_per_hour', 12, 'ASSUMPTION from cost projection'),
  ('wage_high_usd_per_hour', 20, 'ASSUMPTION from cost projection'),
  ('queja_handle_seconds', 434.6, 'ASSUMPTION handle time'),
  ('disputes_per_month', 377.49, 'historical average, projection only')
ON CONFLICT (key) DO NOTHING;

ALTER TABLE app.cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.cases FORCE ROW LEVEL SECURITY;
ALTER TABLE app.audit_case ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.audit_case FORCE ROW LEVEL SECURITY;
ALTER TABLE app.audit_llm_call ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.audit_llm_call FORCE ROW LEVEL SECURITY;
ALTER TABLE app.audit_event ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.audit_event FORCE ROW LEVEL SECURITY;
ALTER TABLE app.handoff ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.handoff FORCE ROW LEVEL SECURITY;
ALTER TABLE app.confirmation ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.confirmation FORCE ROW LEVEL SECURITY;
ALTER TABLE app.card_block ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.card_block FORCE ROW LEVEL SECURITY;
ALTER TABLE app.llm_price ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.llm_price FORCE ROW LEVEL SECURITY;
ALTER TABLE app.analytics_assumption ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.analytics_assumption FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS cases_app_rw_select ON app.cases;
DROP POLICY IF EXISTS cases_app_rw_insert ON app.cases;
DROP POLICY IF EXISTS cases_app_rw_update ON app.cases;
CREATE POLICY cases_app_rw_select ON app.cases FOR SELECT TO app_rw USING (true);
CREATE POLICY cases_app_rw_insert ON app.cases FOR INSERT TO app_rw WITH CHECK (true);
CREATE POLICY cases_app_rw_update ON app.cases FOR UPDATE TO app_rw USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS handoff_app_rw_select ON app.handoff;
DROP POLICY IF EXISTS handoff_app_rw_insert ON app.handoff;
DROP POLICY IF EXISTS handoff_app_rw_update ON app.handoff;
CREATE POLICY handoff_app_rw_select ON app.handoff FOR SELECT TO app_rw USING (true);
CREATE POLICY handoff_app_rw_insert ON app.handoff FOR INSERT TO app_rw WITH CHECK (true);
CREATE POLICY handoff_app_rw_update ON app.handoff FOR UPDATE TO app_rw USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS audit_case_app_rw_select ON app.audit_case;
DROP POLICY IF EXISTS audit_case_app_rw_insert ON app.audit_case;
CREATE POLICY audit_case_app_rw_select ON app.audit_case FOR SELECT TO app_rw USING (true);
CREATE POLICY audit_case_app_rw_insert ON app.audit_case FOR INSERT TO app_rw WITH CHECK (true);

DROP POLICY IF EXISTS audit_llm_app_rw_select ON app.audit_llm_call;
DROP POLICY IF EXISTS audit_llm_app_rw_insert ON app.audit_llm_call;
CREATE POLICY audit_llm_app_rw_select ON app.audit_llm_call FOR SELECT TO app_rw USING (true);
CREATE POLICY audit_llm_app_rw_insert ON app.audit_llm_call FOR INSERT TO app_rw WITH CHECK (true);

DROP POLICY IF EXISTS audit_event_app_rw_select ON app.audit_event;
DROP POLICY IF EXISTS audit_event_app_rw_insert ON app.audit_event;
CREATE POLICY audit_event_app_rw_select ON app.audit_event FOR SELECT TO app_rw USING (true);
CREATE POLICY audit_event_app_rw_insert ON app.audit_event FOR INSERT TO app_rw WITH CHECK (true);

DROP POLICY IF EXISTS confirmation_app_rw_select ON app.confirmation;
DROP POLICY IF EXISTS confirmation_app_rw_insert ON app.confirmation;
CREATE POLICY confirmation_app_rw_select ON app.confirmation FOR SELECT TO app_rw USING (true);
CREATE POLICY confirmation_app_rw_insert ON app.confirmation FOR INSERT TO app_rw WITH CHECK (true);

DROP POLICY IF EXISTS card_block_app_rw_select ON app.card_block;
DROP POLICY IF EXISTS card_block_app_rw_insert ON app.card_block;
CREATE POLICY card_block_app_rw_select ON app.card_block FOR SELECT TO app_rw USING (true);
CREATE POLICY card_block_app_rw_insert ON app.card_block FOR INSERT TO app_rw WITH CHECK (true);

DROP POLICY IF EXISTS llm_price_app_rw_select ON app.llm_price;
CREATE POLICY llm_price_app_rw_select ON app.llm_price FOR SELECT TO app_rw USING (true);

DROP POLICY IF EXISTS assumption_app_rw_select ON app.analytics_assumption;
CREATE POLICY assumption_app_rw_select ON app.analytics_assumption FOR SELECT TO app_rw USING (true);

GRANT SELECT, INSERT, UPDATE ON app.cases TO app_rw;
GRANT SELECT, INSERT, UPDATE ON app.handoff TO app_rw;
REVOKE DELETE ON app.cases FROM app_rw;
REVOKE DELETE ON app.handoff FROM app_rw;

GRANT SELECT, INSERT ON app.audit_case TO app_rw;
GRANT SELECT, INSERT ON app.audit_llm_call TO app_rw;
GRANT SELECT, INSERT ON app.audit_event TO app_rw;
REVOKE UPDATE, DELETE ON app.audit_case FROM app_rw;
REVOKE UPDATE, DELETE ON app.audit_llm_call FROM app_rw;
REVOKE UPDATE, DELETE ON app.audit_event FROM app_rw;

GRANT SELECT, INSERT ON app.confirmation TO app_rw;
GRANT SELECT, INSERT ON app.card_block TO app_rw;
REVOKE UPDATE, DELETE ON app.confirmation FROM app_rw;
REVOKE UPDATE, DELETE ON app.card_block FROM app_rw;
REVOKE DELETE ON app.llm_price FROM app_rw;
REVOKE DELETE ON app.analytics_assumption FROM app_rw;

GRANT SELECT ON app.audit_current TO app_rw;
GRANT SELECT ON app.audit_llm_call_current TO app_rw;
GRANT SELECT ON app.llm_price TO app_rw;
GRANT SELECT ON app.analytics_assumption TO app_rw;

-- security_invoker requires the caller to be able to read the base table.
-- eval_rw is granted the view and, inside the same existence check, SELECT on
-- app.audit_case plus a SELECT policy so the join is not an empty RLS result.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'eval_rw') THEN
    GRANT USAGE ON SCHEMA app TO eval_rw;
    GRANT SELECT ON app.audit_current TO eval_rw;
    GRANT SELECT ON app.audit_case TO eval_rw;
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'app' AND tablename = 'audit_case' AND policyname = 'audit_case_eval_rw_select'
    ) THEN
      CREATE POLICY audit_case_eval_rw_select ON app.audit_case
        FOR SELECT TO eval_rw USING (true);
    END IF;
  END IF;
END $$;
