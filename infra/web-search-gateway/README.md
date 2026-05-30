# web-search-gateway — Simple Test

AgentCore Gateway(관리형 MCP) + Tavily Lambda 로 `web_search` 도구 하나를 노출하고,
end-to-end 동작을 검증하는 최소 테스트. 설계: [`design/web-search-gateway-simpletest.md`](../../design/web-search-gateway-simpletest.md).

레퍼런스 패턴: `gonsoomoon-ml/aiops-multi-agent-workshop` → `infra/cognito-gateway/`.

## 구성
```
cognito.yaml              Cognito + web_search Lambda + 2 IAM Role (CFN)
lambda/web_search/handler.py   Tavily /search 호출
setup_gateway.py          boto3: Gateway + web-search Target 생성 (idempotent)
cleanup_gateway.py        boto3: Target + Gateway 삭제
deploy.sh                 CFN package+deploy → outputs → setup_gateway → .env 기록
teardown.sh               cleanup_gateway → CFN 삭제 → log group → .env 정리
```
> 대화형 검증 스크립트 `smoke_test.py` 는 **프로젝트 루트**에 있음 (Cognito 토큰 → MCP → web_search 반복 호출).

## 사전 요구
- AWS 자격증명 (`aws sts get-caller-identity` 성공)
- `uv` (https://astral.sh/uv)
- 무료 Tavily 키 (https://app.tavily.com — 1,000 크레딧/월)
- 리전: AgentCore Gateway 지원 리전 (예: `us-east-1`)

## 실행
```bash
# 1. 의존성 + .env
uv sync
cp .env.example .env
#  → .env 에서 TAVILY_API_KEY 입력 (필요 시 DEMO_USER, AWS_REGION 조정)

# 2. 배포 (Cognito + Lambda + Gateway + Target)
./infra/web-search-gateway/deploy.sh

# 3. 검증
uv run python smoke_test.py "latest AWS news today"   # 프로젝트 루트에서
```

기대 출력: `list_tools` 에 `web-search___web_search` 가 보이고, 호출 결과로
`{query, results:[{title,url,snippet,score}, …]}` JSON 이 출력됨.

## Claude Code on Bedrock 에서 직접 쓰기 (선택)
```bash
# .env 에서 GATEWAY_URL 확인. 토큰은 client_credentials 로 발급(~1h 만료).
claude mcp add --transport http web-search "<GATEWAY_URL>" \
  --header "Authorization: Bearer <token>"
```
> Bedrock 환경에서는 MCP tool-search 가 400 을 유발할 수 있으니
> `export ENABLE_TOOL_SEARCH=auto:30` (또는 `false`) 설정.

## 정리
```bash
./infra/web-search-gateway/teardown.sh
```

## 범위 밖 (다음 단계)
제공자 추상화·폴백, 캐시·예산, `fetch_url`, Secrets Manager(키), 토큰 자동 갱신,
관측성. 본 디렉토리는 "게이트웨이 경유 web_search 가 되는가"만 증명한다.
