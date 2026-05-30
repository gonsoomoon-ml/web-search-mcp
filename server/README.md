# web-search-gateway — Simple Test

AgentCore Gateway(관리형 MCP) + Tavily Lambda 로 `web_search` 도구 하나를 노출하고,
end-to-end 동작을 검증하는 최소 테스트. 설계: [`design/web-search-gateway-simpletest.md`](../design/web-search-gateway-simpletest.md).
이 폴더는 **[목적 1] MCP 서버 구축·배포**. 배포된 게이트웨이에 *연결*하는 클라이언트는 [`../clients/`](../clients/).

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
> 대화형 검증 스크립트는 [`clients/smoke_test.py`](../clients/smoke_test.py) (Cognito 토큰 → MCP → web_search 반복 호출).

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
./server/deploy.sh

# 3. 검증
uv run python clients/smoke_test.py "latest AWS news today"   # 프로젝트 루트에서
```

기대 출력: `list_tools` 에 `web-search___web_search` 가 보이고, 호출 결과로
`{query, results:[{title,url,snippet,score}, …]}` JSON 이 출력됨.

## 클라이언트 연결 (배포 후)
게이트웨이에 붙는 방법은 [`../clients/`](../clients/):
- Claude Code on Bedrock → [`../clients/claude-code/`](../clients/claude-code/)
- Cowork on Bedrock 3P → [`../clients/cowork/`](../clients/cowork/)
- 빠른 raw 테스터 → [`../clients/smoke_test.py`](../clients/smoke_test.py)
- 레이어별 테스트 가이드 → [`../clients/TESTING.md`](../clients/TESTING.md)

## 정리
```bash
./server/teardown.sh
```

## 범위 밖 (다음 단계)
제공자 추상화·폴백, 캐시·예산, `fetch_url`, Secrets Manager(키), 토큰 자동 갱신,
관측성. 본 디렉토리는 "게이트웨이 경유 web_search 가 되는가"만 증명한다.
