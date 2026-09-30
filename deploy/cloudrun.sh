#!/usr/bin/env bash
# Deploy Harbor Desk to Cloud Run.
#
# DATABASE_URL is read from the environment and uploaded to Secret Manager.
# The service receives the secret name, not the URL. This script does not
# write the URL into the repo or print it.
#
# Required in the environment:
#   GCP_PROJECT
#   DATABASE_URL          app_rw connection string
#   SESSION_SECRET        at least 32 characters, not the dev default
# Optional:
#   EVAL_RUNNER_TOKEN
#   DEMO_AGENT_TOKEN      required in production when Clerk keys are absent
#   CLERK_SECRET_KEY / CLERK_PUBLISHABLE_KEY
#   GCP_REGION (default us-central1)
#   SERVICE_NAME (default harbor-desk)
#   LLM_PROVIDER (default template)

set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,20p' "$0"
  exit 0
fi

: "${GCP_PROJECT:?Set GCP_PROJECT}"
: "${DATABASE_URL:?Set DATABASE_URL in the environment. It is stored in Secret Manager.}"
: "${SESSION_SECRET:?Set SESSION_SECRET}"

if [[ "${#SESSION_SECRET}" -lt 32 || "${SESSION_SECRET}" == "dev-insecure-session-secret" ]]; then
  echo "SESSION_SECRET must be a non-default value of at least 32 characters." >&2
  exit 1
fi

GCP_REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-harbor-desk}"
LLM_PROVIDER="${LLM_PROVIDER:-template}"

upsert_secret() {
  local name="$1"
  local value="$2"
  if gcloud secrets describe "${name}" --project "${GCP_PROJECT}" >/dev/null 2>&1; then
    printf '%s' "${value}" | gcloud secrets versions add "${name}" \
      --project "${GCP_PROJECT}" --data-file=- >/dev/null
  else
    printf '%s' "${value}" | gcloud secrets create "${name}" \
      --project "${GCP_PROJECT}" --replication-policy=automatic --data-file=- >/dev/null
  fi
}

db_secret="${SERVICE_NAME}-database-url"
session_secret="${SERVICE_NAME}-session-secret"
upsert_secret "${db_secret}" "${DATABASE_URL}"
upsert_secret "${session_secret}" "${SESSION_SECRET}"

secrets="DATABASE_URL=${db_secret}:latest,SESSION_SECRET=${session_secret}:latest"
env_vars="ENVIRONMENT=production|LLM_PROVIDER=${LLM_PROVIDER}"

if [[ -n "${EVAL_RUNNER_TOKEN:-}" ]]; then
  eval_secret="${SERVICE_NAME}-eval-runner-token"
  upsert_secret "${eval_secret}" "${EVAL_RUNNER_TOKEN}"
  secrets="${secrets},EVAL_RUNNER_TOKEN=${eval_secret}:latest"
fi
if [[ -n "${DEMO_AGENT_TOKEN:-}" ]]; then
  agent_secret="${SERVICE_NAME}-demo-agent-token"
  upsert_secret "${agent_secret}" "${DEMO_AGENT_TOKEN}"
  secrets="${secrets},DEMO_AGENT_TOKEN=${agent_secret}:latest"
fi
if [[ -n "${CLERK_SECRET_KEY:-}" ]]; then
  clerk_secret="${SERVICE_NAME}-clerk-secret"
  upsert_secret "${clerk_secret}" "${CLERK_SECRET_KEY}"
  secrets="${secrets},CLERK_SECRET_KEY=${clerk_secret}:latest"
fi
if [[ -n "${CLERK_PUBLISHABLE_KEY:-}" ]]; then
  env_vars="${env_vars}|CLERK_PUBLISHABLE_KEY=${CLERK_PUBLISHABLE_KEY}"
fi
if [[ -n "${OPENAI_API_KEY:-}" ]]; then
  openai_secret="${SERVICE_NAME}-openai-key"
  upsert_secret "${openai_secret}" "${OPENAI_API_KEY}"
  secrets="${secrets},OPENAI_API_KEY=${openai_secret}:latest"
fi

echo "Deploying ${SERVICE_NAME} to ${GCP_REGION}. Database credentials stay in Secret Manager."

gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --project "${GCP_PROJECT}" \
  --region "${GCP_REGION}" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --min-instances 0 \
  --max-instances 4 \
  --memory 512Mi \
  --cpu 1 \
  --timeout 60 \
  --set-secrets "${secrets}" \
  --set-env-vars "^|^${env_vars}"
