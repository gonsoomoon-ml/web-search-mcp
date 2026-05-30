#!/usr/bin/env bash
# server/teardown.sh — Gateway/Target → CFN stack → DEPLOY_BUCKET → .env 정리
# Reference: gonsoomoon-ml/aiops-multi-agent-workshop infra/cognito-gateway/teardown.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
log()  { echo -e "${GREEN}[teardown]${NC} $1"; }
warn() { echo -e "${YELLOW}[teardown]${NC} $1"; }
fail() { echo -e "${RED}[teardown]${NC} $1"; exit 1; }

[[ -f "$PROJECT_ROOT/.env" ]] && { set -a; source "$PROJECT_ROOT/.env"; set +a; }

REGION="${AWS_REGION:-us-east-1}"
DEMO_USER="${DEMO_USER:-${USER:-ubuntu}}"
[[ "$DEMO_USER" =~ ^[a-z0-9-]{1,16}$ ]] \
    || fail "DEMO_USER='$DEMO_USER' 잘못된 형식 (소문자/숫자/하이픈만 ≤16자 — Cognito Domain 제약)"
ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo '')"
[[ -n "$ACCOUNT_ID" ]] || fail "AWS 자격증명 미설정"

STACK="web-search-${DEMO_USER}-gateway"
DEPLOY_BUCKET="web-search-${DEMO_USER}-deploy-${ACCOUNT_ID}-${REGION}"

log "region=$REGION demo_user=$DEMO_USER stack=$STACK"

# delete + wait + verify (idempotent)
delete_stack() {
    local stack="$1"
    if ! aws cloudformation describe-stacks --region "$REGION" --stack-name "$stack" >/dev/null 2>&1; then
        warn "  (stack '$stack' 없음 — skip)"
        return 0
    fi
    aws cloudformation delete-stack --region "$REGION" --stack-name "$stack"
    aws cloudformation wait stack-delete-complete --region "$REGION" --stack-name "$stack" 2>/dev/null || true
    if aws cloudformation describe-stacks --region "$REGION" --stack-name "$stack" --query 'Stacks[0].StackStatus' --output text 2>/dev/null | grep -qv "DELETE_COMPLETE"; then
        fail "  ❌ stack '$stack' 삭제 실패. 'aws cloudformation describe-stack-events --stack-name $stack' 로 원인 확인"
    fi
    log "  ✓ stack '$stack' 삭제 완료"
}

# ── 1. boto3 자원 먼저 삭제 (Gateway + Target) ──
# CFN stack 의 Lambda invoke 권한이 살아있는 동안 호출 필요
log "Gateway + Target 정리 (boto3, idempotent)"
DEMO_USER="$DEMO_USER" AWS_REGION="$REGION" \
    uv run python "$PROJECT_ROOT/server/cleanup_gateway.py" || warn "cleanup_gateway.py 실패 (무시 후 진행)"

# ── 2. CFN stack 삭제 (post-verify) ─────────────
log "CFN stack 삭제: $STACK"
delete_stack "$STACK"

# ── Lambda Log Group 삭제 (CFN cascade 안 함 — first-invoke 시 auto-create) ──
LAMBDA_LG="/aws/lambda/web-search-${DEMO_USER}-web-search"
if aws logs delete-log-group --region "$REGION" --log-group-name "$LAMBDA_LG" 2>/dev/null; then
    log "  ✓ Lambda log group ${LAMBDA_LG} 삭제"
fi

# ── 3. DEPLOY_BUCKET 비우기 + 삭제 ──────────────
if aws s3api head-bucket --bucket "$DEPLOY_BUCKET" --region "$REGION" 2>/dev/null; then
    log "DEPLOY_BUCKET 정리: s3://$DEPLOY_BUCKET"
    aws s3 rm "s3://$DEPLOY_BUCKET" --recursive --region "$REGION" >/dev/null
    aws s3 rb "s3://$DEPLOY_BUCKET" --region "$REGION"
fi

# ── 4. packaged.yaml 정리 ───────────────────────
rm -f "$PROJECT_ROOT/server/cognito.packaged.yaml"

# ── 5. .env 변수 비우기 ─────────────────────────
log ".env 변수 비우기 (TAVILY_API_KEY 는 유지)"
for key in COGNITO_USER_POOL_ID COGNITO_DOMAIN COGNITO_CLIENT_ID COGNITO_CLIENT_SECRET \
           COGNITO_GATEWAY_SCOPE GATEWAY_ID GATEWAY_URL LAMBDA_WEB_SEARCH_ARN; do
    sed -i "s|^${key}=.*|${key}=|" "$PROJECT_ROOT/.env" 2>/dev/null || true
done

log "teardown 완료"
