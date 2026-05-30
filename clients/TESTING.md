# 직접 테스트 가이드 — web-search-gateway

AgentCore Gateway + Tavily Lambda(`web_search`)를 직접 검증하는 단계별 가이드.
레이어가 올라갈수록 더 많은 부품을 검증합니다 — 막히면 한 레이어 내려가서 원인을 좁히세요.

```
레이어 0  정적 검사            (AWS·키 불필요)
레이어 1  핸들러 로직 (mock)    (AWS·키 불필요)
레이어 2  Lambda 직접 호출      (AWS + Tavily 키)   ← 게이트웨이/인증 제외하고 Lambda+Tavily만
레이어 3  게이트웨이 E2E        (AWS + Tavily 키)   ← Cognito→Gateway→Lambda 전체 배선
레이어 4  Claude Code 통합     (위 + Bedrock 세션)
```

---

## 0. 사전 요구

```bash
# (1) AWS 자격증명 — 성공해야 함
aws sts get-caller-identity --query Account --output text

# (2) uv 설치 확인 (없으면: curl -LsSf https://astral.sh/uv/install.sh | sh)
uv --version

# (3) 리전 — AgentCore Gateway 지원 리전 사용 (us-east-1 권장)
#     .env 의 AWS_REGION 으로 제어
```
- **Tavily 무료 키**: https://app.tavily.com (카드 불필요, 1,000 크레딧/월)

---

## 레이어 0 — 정적 검사 (AWS·키 불필요)

```bash
# 파이썬 컴파일
python3 -m py_compile server/*.py server/lambda/web_search/handler.py clients/smoke_test.py clients/cowork/cowork-token-helper.py
# bash 문법
bash -n server/deploy.sh && bash -n server/teardown.sh
```
기대: 에러 없이 종료(코드 0).

---

## 레이어 1 — 핸들러 로직 단위 테스트 (mock, AWS·키 불필요)

네트워크/AWS 없이 도구 디스패치·검증·응답 매핑·max_results 클램프를 검증.

```bash
python3 - <<'PY'
import os, sys, json
from unittest import mock
os.environ["TAVILY_API_KEY"] = "dummy"
sys.path.insert(0, "server/lambda/web_search")
import handler
def ctx(t):
    cc = type("CC", (), {"custom": {"bedrockAgentCoreToolName": t}})()
    return type("Ctx", (), {"client_context": cc})()

assert handler.lambda_handler({"query":"x"}, ctx("x___foo")) == {"error": "unknown tool: 'x___foo'"}
assert handler.lambda_handler({}, ctx("web-search___web_search")) == {"error": "query is required"}

fake = {"results":[{"title":"T","url":"https://a","content":"snip","score":0.9}]}
class R:
    def __enter__(s): return s
    def __exit__(s,*a): return False
    def read(s): return json.dumps(fake).encode()
cap = {}
def fake_open(req, timeout=None):
    cap["body"] = json.loads(req.data.decode()); return R()
with mock.patch("handler.urllib.request.urlopen", side_effect=fake_open):
    r = handler.lambda_handler({"query":"aws","max_results":99}, ctx("web-search___web_search"))
assert r["results"][0] == {"title":"T","url":"https://a","snippet":"snip","score":0.9}
assert cap["body"]["max_results"] == 20   # 99 → 20 클램프
print("✅ 레이어 1 통과")
PY
```

---

## 준비 — 의존성 + .env (레이어 2~ 공통)

```bash
uv sync                          # mcp, boto3, python-dotenv 설치
cp .env.example .env             # 이미 있으면 skip
# .env 편집: TAVILY_API_KEY=tvly-xxxx 입력
#   (선택) DEMO_USER=<소문자> , AWS_REGION=<리전>
```

---

## 레이어 2 — Lambda 직접 호출 (게이트웨이/인증 제외)

먼저 배포한 뒤(레이어 3의 deploy 실행) Lambda만 단독 호출 — "Lambda+Tavily가 되는가"를 게이트웨이 배선과 분리해 검증.

```bash
set -a; source .env; set +a
DEMO_USER="${DEMO_USER:-$USER}"

# 게이트웨이가 넘기는 도구 이름을 client-context 로 흉내
CTX=$(printf '{"custom":{"bedrockAgentCoreToolName":"web-search___web_search"}}' | base64)

aws lambda invoke --region "$AWS_REGION" \
  --function-name "web-search-${DEMO_USER}-web-search" \
  --client-context "$CTX" \
  --cli-binary-format raw-in-base64-out \
  --payload '{"query":"latest AWS news today","max_results":3}' \
  /dev/stdout
```
기대: `{"query":"...","results":[{"title":...,"url":...,"snippet":...,"score":...}, ...]}`
- `{"error":"query is required"}` → payload 문제
- `{"error":"tavily HTTPError 401"}` → 키 잘못/미주입 (재배포 필요)

---

## 레이어 3 — 게이트웨이 E2E (전체 배선)

### 3-1. 배포
```bash
./server/deploy.sh
```
- 소요: 약 3~5분 (Cognito+Lambda+IAM CFN ~2-3분, Gateway 생성 ~30-60초)
- 완료 후 `.env` 에 `GATEWAY_URL`, `COGNITO_*`, `LAMBDA_WEB_SEARCH_ARN` 이 채워짐

### 3-2. 배포 검증
```bash
set -a; source .env; set +a
echo "GATEWAY_URL=$GATEWAY_URL"                       # 비어있지 않아야 함
aws cloudformation describe-stacks --region "$AWS_REGION" \
  --stack-name "web-search-${DEMO_USER:-$USER}-gateway" \
  --query 'Stacks[0].StackStatus' --output text       # CREATE_COMPLETE / UPDATE_COMPLETE
aws bedrock-agentcore-control list-gateways --region "$AWS_REGION" \
  --query "items[?name=='web-search-${DEMO_USER:-$USER}-gateway'].[name,status]" --output text
```

### 3-3. 스모크 테스트 (Cognito 토큰 → MCP → web_search)
```bash
uv run python clients/smoke_test.py "latest AWS news today"
```
기대 출력:
```
① Cognito 토큰 발급 … ✅ token 획득
② Gateway MCP 연결: https://...gateway...
③ list_tools …  도구: ['web-search___web_search']
④ web-search___web_search(query=...) 호출 …
   {"query": "...", "results": [{"title": ..., "url": ..., "snippet": ..., "score": ...}]}
✅ smoke test 완료
```

---

## 레이어 4 — Claude Code on Bedrock 통합 (선택)

```bash
set -a; source .env; set +a
# Cognito M2M 토큰 발급 (~1h 만료)
TOKEN=$(curl -s -X POST \
  "https://${COGNITO_DOMAIN}.auth.${AWS_REGION}.amazoncognito.com/oauth2/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -u "${COGNITO_CLIENT_ID}:${COGNITO_CLIENT_SECRET}" \
  -d "grant_type=client_credentials&scope=${COGNITO_GATEWAY_SCOPE}" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

export CLAUDE_CODE_USE_BEDROCK=1
export ENABLE_TOOL_SEARCH=auto:30      # Bedrock tool-search 400 회피
claude mcp add --transport http web-search "$GATEWAY_URL" --header "Authorization: Bearer $TOKEN"
claude mcp list                        # web-search ✓ Connected
# 세션에서: "Use web_search to find the latest AWS news today and cite URLs."
```

---

## 정리 (과금 방지 — 테스트 후 필수)

```bash
./server/teardown.sh
```
Gateway/Target 삭제 → CFN 스택 삭제 → Lambda 로그그룹 삭제 → S3 배포버킷 삭제 → `.env` 변수 비움(키는 유지).

---

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `TAVILY_API_KEY 미설정` (deploy) | `.env` 에 키 입력 |
| `DEMO_USER ... 잘못된 형식` | 소문자/숫자/하이픈만, ≤16자 |
| `ModuleNotFoundError: mcp...` (smoke_test) | `uv sync` 후 `uv run python ...` 로 실행 |
| 토큰 발급 시 도메인 not found | Cognito 도메인 프로비저닝 지연 — 1분 후 재시도 |
| 토큰 `invalid_scope`/`invalid_client` | deploy 미완료로 `COGNITO_*` 빈 값 — `.env` 확인 |
| `tavily HTTPError 401` | 키 오류; `432`/usage → 크레딧 소진 |
| Gateway 생성 `ValidationException` | READY 전 Target 추가 — setup_gateway 가 대기하므로 재실행 |
| Claude Code `400 Tool reference not found` | `export ENABLE_TOOL_SEARCH=auto:30` (또는 `false`) |
| AgentCore Gateway 미지원 리전 에러 | `AWS_REGION` 을 `us-east-1`/`us-west-2` 로 |

---

## 한 줄 빠른 경로
```bash
uv sync && cp -n .env.example .env   # → .env 에 TAVILY_API_KEY 입력
./server/deploy.sh
uv run python clients/smoke_test.py "latest AWS news today"
./server/teardown.sh
```
