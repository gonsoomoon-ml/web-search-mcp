#!/usr/bin/env bash
# infra/web-search-gateway/deploy.sh
#   Cognito + Lambda + IAM (CFN) + AgentCore Gateway + web-search Target (boto3)
# Reference: gonsoomoon-ml/aiops-multi-agent-workshop infra/cognito-gateway/deploy.sh
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT/infra/web-search-gateway"

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'
log()  { echo -e "${GREEN}[deploy]${NC} $1"; }
fail() { echo -e "${RED}[deploy]${NC} $1"; exit 1; }

# ── 사전 검증 ────────────────────────────────────
aws sts get-caller-identity --query Account --output text >/dev/null 2>&1 \
    || fail "AWS 자격증명 미설정"

[[ -f "$PROJECT_ROOT/.env" ]] || fail ".env 미존재. cp .env.example .env 후 재실행"

set -a
source "$PROJECT_ROOT/.env"
set +a

REGION="${AWS_REGION:-us-east-1}"
DEMO_USER="${DEMO_USER:-${USER:-ubuntu}}"
[[ "$DEMO_USER" =~ ^[a-z0-9-]{1,16}$ ]] \
    || fail "DEMO_USER='$DEMO_USER' 잘못된 형식 (소문자/숫자/하이픈만 ≤16자 — Cognito Domain 제약)"
[[ -n "${TAVILY_API_KEY:-}" ]] \
    || fail "TAVILY_API_KEY 미설정 — .env 에 입력 (https://app.tavily.com)"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
STACK="web-search-${DEMO_USER}-gateway"
DEPLOY_BUCKET="web-search-${DEMO_USER}-deploy-${ACCOUNT_ID}-${REGION}"

log "region=$REGION demo_user=$DEMO_USER account=$ACCOUNT_ID"
log "stack=$STACK / deploy bucket=$DEPLOY_BUCKET"

# ── 0. DEPLOY_BUCKET 보장 (idempotent) ───────────
if ! aws s3api head-bucket --bucket "$DEPLOY_BUCKET" --region "$REGION" 2>/dev/null; then
    log "DEPLOY_BUCKET 생성: s3://$DEPLOY_BUCKET"
    aws s3 mb "s3://$DEPLOY_BUCKET" --region "$REGION"
    aws s3api put-public-access-block --bucket "$DEPLOY_BUCKET" \
        --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
else
    log "DEPLOY_BUCKET 이미 존재 (재사용)"
fi

# ── 1. cfn package (Lambda Code 디렉토리 zip + S3 업로드) ─
log "cfn package — Lambda Code 디렉토리 zip + S3 업로드"
aws cloudformation package \
    --template-file "$PROJECT_ROOT/infra/web-search-gateway/cognito.yaml" \
    --s3-bucket "$DEPLOY_BUCKET" \
    --s3-prefix "web-search-gateway" \
    --region "$REGION" \
    --output-template-file "$PROJECT_ROOT/infra/web-search-gateway/cognito.packaged.yaml" >/dev/null

# ── 2. CFN deploy (Cognito + Lambda + IAM) ──────
log "CFN deploy: $STACK"
aws cloudformation deploy \
    --region "$REGION" \
    --template-file "$PROJECT_ROOT/infra/web-search-gateway/cognito.packaged.yaml" \
    --stack-name "$STACK" \
    --capabilities CAPABILITY_NAMED_IAM \
    --parameter-overrides "DemoUser=${DEMO_USER}" "TavilyApiKey=${TAVILY_API_KEY}"

# ── 3. CFN outputs 환경변수 export ──────────────
log "CFN outputs 캡처"
get_output() {
    aws cloudformation describe-stacks --region "$REGION" --stack-name "$STACK" \
        --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text
}
export COGNITO_USER_POOL_ID="$(get_output UserPoolId)"
export COGNITO_DOMAIN="$(get_output Domain)"
export COGNITO_CLIENT_ID="$(get_output ClientId)"
export COGNITO_GATEWAY_SCOPE="$(get_output ResourceServerScope)"
export GATEWAY_IAM_ROLE_ARN="$(get_output GatewayIamRoleArn)"
export LAMBDA_WEB_SEARCH_ARN="$(get_output LambdaWebSearchArn)"

# Cognito Client Secret 별도 조회 (CFN output 미노출)
export COGNITO_CLIENT_SECRET="$(aws cognito-idp describe-user-pool-client \
    --region "$REGION" \
    --user-pool-id "$COGNITO_USER_POOL_ID" \
    --client-id "$COGNITO_CLIENT_ID" \
    --query 'UserPoolClient.ClientSecret' --output text)"

# ── 4. boto3 setup — Gateway + web-search Target ─
log "boto3: Gateway + web-search Target 생성"
TMP_OUT="$(mktemp)"
trap 'rm -f "$TMP_OUT"' EXIT
DEMO_USER="$DEMO_USER" AWS_REGION="$REGION" \
    uv run python "$PROJECT_ROOT/infra/web-search-gateway/setup_gateway.py" \
    | tee "$TMP_OUT"

GATEWAY_ID="$(grep '^GATEWAY_ID=' "$TMP_OUT" | cut -d= -f2-)"
GATEWAY_URL="$(grep '^GATEWAY_URL=' "$TMP_OUT" | cut -d= -f2-)"
[[ -n "$GATEWAY_ID" && -n "$GATEWAY_URL" ]] \
    || fail "setup_gateway.py 출력에서 GATEWAY_ID/URL 캡처 실패"

# ── 5. .env 갱신 ─────────────────────────────────
log ".env 갱신"
update_env() {
    local key="$1" val="$2"
    if grep -qE "^${key}=" "$PROJECT_ROOT/.env"; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$PROJECT_ROOT/.env"
    else
        echo "${key}=${val}" >> "$PROJECT_ROOT/.env"
    fi
}
update_env COGNITO_USER_POOL_ID   "$COGNITO_USER_POOL_ID"
update_env COGNITO_DOMAIN         "$COGNITO_DOMAIN"
update_env COGNITO_CLIENT_ID      "$COGNITO_CLIENT_ID"
update_env COGNITO_CLIENT_SECRET  "$COGNITO_CLIENT_SECRET"
update_env COGNITO_GATEWAY_SCOPE  "$COGNITO_GATEWAY_SCOPE"
update_env GATEWAY_ID             "$GATEWAY_ID"
update_env GATEWAY_URL            "$GATEWAY_URL"
update_env LAMBDA_WEB_SEARCH_ARN  "$LAMBDA_WEB_SEARCH_ARN"

log "deploy 완료"
log "  Gateway URL: $GATEWAY_URL"
log "  Lambda (web_search): $LAMBDA_WEB_SEARCH_ARN"
log "  검증: uv run python smoke_test.py \"latest AWS news today\""
