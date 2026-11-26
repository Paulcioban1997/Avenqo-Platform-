#!/usr/bin/env bash
set -euo pipefail

vercel_environment="${VERCEL_ENV:-}"
app_environment="${AVENQO_ENVIRONMENT:-${ENVIRONMENT:-${NEXT_PUBLIC_AVENQO_ENVIRONMENT:-}}}"
git_ref="${VERCEL_GIT_COMMIT_REF:-}"

if [[ "${vercel_environment,,}" == preview ||
      "${app_environment,,}" == sandbox ||
      "$git_ref" == promotion/sandbox ||
      "$git_ref" == integration/avenqo-sandbox-latest-20261113 ]]; then
  printf '%s\n' 'https://avenqo-platform-sandbox.up.railway.app/api/v1'
elif [[ "${vercel_environment,,}" == production || "${app_environment,,}" == production ]]; then
  printf '%s\n' 'https://api.avenqo.ca/api/v1'
else
  printf '%s\n' "${API_BASE_URL:-/api/v1}"
fi
