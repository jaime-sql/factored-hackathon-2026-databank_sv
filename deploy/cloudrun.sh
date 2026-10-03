#!/usr/bin/env bash
# Deploy Harbor Desk to the live Cloud Run service as a NO-TRAFFIC tagged revision.
#
#   deploy/cloudrun.sh [TAG] [GIT_REF]
#
# TAG      revision tag, default "next" -> https://TAG---databank-sv-app-4oixi2h3ua-uc.a.run.app
# GIT_REF  commit to build, default origin/main. The image is built from
#          `git archive GIT_REF`, so local edits never reach the build.
#
# Running this never moves live traffic. To promote a checked revision:
#   gcloud run services update-traffic databank-sv-app --region us-central1 \
#     --project databank-sv-123456 --to-revisions REVISION=100
#
# Secrets are read from Secret Manager by the service; this script never reads,
# prints, or writes their values:
#   admin-token        -> DEMO_AGENT_TOKEN
#   demo-judge-token   -> DEMO_JUDGE_TOKEN
#   qa-test-token      -> QA_TEST_TOKEN
#   eval-runner-token  -> EVAL_RUNNER_TOKEN
#   database-url       -> DATABASE_URL
#   session-secret     -> SESSION_SECRET
#   openai-api-key     -> OPENAI_API_KEY
#
# Overrides: GCP_PROJECT, GCP_REGION, SERVICE_NAME, IMAGE_REPO.
# DRY_RUN=1 prints the gcloud commands instead of running them.

set -euo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '2,25p' "$0"
  exit 0
fi

TAG="${1:-next}"
GIT_REF="${2:-origin/main}"
GCP_PROJECT="${GCP_PROJECT:-databank-sv-123456}"
GCP_REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="${SERVICE_NAME:-databank-sv-app}"
IMAGE_REPO="${IMAGE_REPO:-${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT}/databank-sv/app}"

if [[ ! "${TAG}" =~ ^[a-z][a-z0-9-]{0,45}$ ]]; then
  echo "TAG must be lowercase letters, digits or '-', starting with a letter." >&2
  exit 1
fi

SECRETS="DEMO_AGENT_TOKEN=admin-token:latest"
SECRETS+=",DEMO_JUDGE_TOKEN=demo-judge-token:latest"
SECRETS+=",QA_TEST_TOKEN=qa-test-token:latest"
SECRETS+=",EVAL_RUNNER_TOKEN=eval-runner-token:latest"
SECRETS+=",DATABASE_URL=database-url:latest"
SECRETS+=",SESSION_SECRET=session-secret:latest"
SECRETS+=",OPENAI_API_KEY=openai-api-key:latest"

run() {
  if [[ "${DRY_RUN:-0}" == "1" ]]; then
    printf '+'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

repo_root="$(git rev-parse --show-toplevel)"
if [[ "${DRY_RUN:-0}" != "1" ]]; then
  git -C "${repo_root}" fetch --quiet origin
fi
sha="$(git -C "${repo_root}" rev-parse --short=7 "${GIT_REF}^{commit}")"
image="${IMAGE_REPO}:${sha}"

src="$(mktemp -d)"
trap 'rm -rf "${src}"' EXIT
git -C "${repo_root}" archive "${GIT_REF}" | tar -x -C "${src}"

echo "Building ${GIT_REF} (${sha}) from git archive."
# --async plus polling: the deploy account cannot stream build logs, which makes a
# blocking `builds submit` exit 1 even when the build succeeds.
if [[ "${DRY_RUN:-0}" == "1" ]]; then
  run gcloud builds submit "${src}" --project "${GCP_PROJECT}" --tag "${image}" --async
else
  build_id="$(gcloud builds submit "${src}" --project "${GCP_PROJECT}" --tag "${image}" \
    --async --format='value(id)')"
  status="QUEUED"
  while [[ "${status}" == "QUEUED" || "${status}" == "WORKING" ]]; do
    sleep 10
    status="$(gcloud builds describe "${build_id}" --project "${GCP_PROJECT}" --format='value(status)')"
  done
  if [[ "${status}" != "SUCCESS" ]]; then
    echo "Build ${build_id} ended with ${status}." >&2
    exit 1
  fi
  echo "Build ${build_id}: SUCCESS"
fi

echo "Deploying ${sha} to ${SERVICE_NAME} as tag '${TAG}' with no traffic."
run gcloud run deploy "${SERVICE_NAME}" \
  --image "${image}" \
  --project "${GCP_PROJECT}" \
  --region "${GCP_REGION}" \
  --platform managed \
  --no-traffic \
  --tag "${TAG}" \
  --allow-unauthenticated \
  --port 8080 \
  --min-instances 1 \
  --max-instances 4 \
  --memory 1Gi \
  --cpu 1 \
  --concurrency 80 \
  --timeout 60 \
  --cpu-boost \
  --set-env-vars ENVIRONMENT=production \
  --set-secrets "${SECRETS}"
