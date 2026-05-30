#!/usr/bin/env bash
# local_test.sh — 로컬 Claude Code on Bedrock 에서 web-search 게이트웨이만 격리 테스트.
#   1) .env 로드 → Cognito M2M 토큰 발급
#   2) web-search 만 담은 임시 MCP config 작성
#   3) claude --strict-mcp-config 로 격리 세션 실행 (다른 MCP 서버 전부 무시)
# 사용 (프로젝트 어디서든): ./infra/web-search-gateway/local_test.sh
# 끝나면 임시 config 자동 삭제. 기존 MCP 설정은 전혀 안 건드림.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# .env 탐색: 스크립트와 같은 폴더 → 상위 디렉토리(최대 5단계). 평면 폴더/ repo 구조 모두 지원.
ENV_FILE=""
_d="$SCRIPT_DIR"
for _ in 1 2 3 4 5; do
  if [[ -f "$_d/.env" ]]; then ENV_FILE="$_d/.env"; break; fi
  _d="$(dirname "$_d")"
done
[[ -n "$ENV_FILE" ]] || { echo "❌ .env 를 찾을 수 없음 — local_test.sh 와 같은 폴더(또는 상위)에 .env 를 두세요"; exit 1; }
echo "ℹ️  .env: $ENV_FILE"
set -a; source "$ENV_FILE"; set +a
: "${GATEWAY_URL:?GATEWAY_URL 비어있음 — deploy.sh 실행 필요}"
: "${COGNITO_DOMAIN:?COGNITO_DOMAIN 비어있음}"
: "${COGNITO_CLIENT_ID:?}" ; : "${COGNITO_CLIENT_SECRET:?}" ; : "${COGNITO_GATEWAY_SCOPE:?}"

REGION="${AWS_REGION:-us-east-1}"

echo "① Cognito 토큰 발급…"
export TOKEN
TOKEN=$(curl -s -X POST \
  "https://${COGNITO_DOMAIN}.auth.${REGION}.amazoncognito.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "${COGNITO_CLIENT_ID}:${COGNITO_CLIENT_SECRET}" \
  -d "grant_type=client_credentials&scope=${COGNITO_GATEWAY_SCOPE}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
[[ -n "$TOKEN" ]] || { echo "❌ 토큰 발급 실패 — COGNITO_* 값 확인"; exit 1; }
echo "   ✅ token len=${#TOKEN}"

CFG=/tmp/web-search-mcp-test.json
python3 - "$CFG" <<'PY'
import os, sys, json
json.dump({"mcpServers": {"web-search": {"type": "http", "url": os.environ["GATEWAY_URL"],
    "headers": {"Authorization": "Bearer " + os.environ["TOKEN"]}}}}, open(sys.argv[1], "w"))
PY
echo "② 임시 config: $CFG (web-search 단독)"

# Bedrock + 모델 (이미 설정돼 있으면 그대로 존중)
export CLAUDE_CODE_USE_BEDROCK=1
export AWS_REGION="$REGION"
export ANTHROPIC_MODEL="${ANTHROPIC_MODEL:-global.anthropic.claude-sonnet-4-6}"
export ANTHROPIC_SMALL_FAST_MODEL="${ANTHROPIC_SMALL_FAST_MODEL:-global.anthropic.claude-haiku-4-5-20251001-v1:0}"
export ENABLE_TOOL_SEARCH="${ENABLE_TOOL_SEARCH:-false}"

echo "③ Claude Code 격리 세션 시작 (Bedrock, web-search 만 로드)"
echo "   세션에서:  /mcp  로 web-search 확인 후 웹검색 질문."
echo "   예) Amazon Bedrock AgentCore 최신 뉴스를 웹에서 검색하고 출처 URL과 함께 한국어로 요약해줘."
echo "──────────────────────────────────────────────"
claude --mcp-config "$CFG" --strict-mcp-config || true

rm -f "$CFG"
echo "✅ 종료 — 임시 config 삭제 완료 (기존 MCP 설정 그대로)"
