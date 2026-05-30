# Web Search Gateway — Simple Test 설계 (AgentCore Gateway + Tavily Lambda)

> 작성일: 2026-05-30
> 관련: [`prd.md`](./prd.md) · [`research-comparison.md`](./research-comparison.md) · [`cowork-feature-mapping.md`](./cowork-feature-mapping.md)
> 레퍼런스 패턴: `gonsoomoon-ml/aiops-multi-agent-workshop` → `infra/cognito-gateway/` (CLAUDE.md 참고자료)

## 1. 목표 & 범위
"Claude Code on Bedrock → **AgentCore Gateway**(관리형 MCP) → Lambda → Tavily → 결과 반환"이 end-to-end로 동작하는지 검증하는 **simple test**. 도구는 `web_search` 1개. 추상화·폴백·캐시·fetch_url·보안 강화·Secrets Manager는 전부 다음 단계로 미룸(YAGNI).

워크숍 `infra/cognito-gateway/` 코드를 **최대한 그대로 재사용**하되, 타깃 2개(history-mock/cloudwatch) → **타깃 1개(web-search)**, prefix `aiops-demo-` → `web-search-` 로만 치환.

## 2. 아키텍처
```
Claude Code (Bedrock)   ──또는──   smoke_test.py (직접 MCP client)
   │  ① Cognito M2M (client_credentials, scope=web-search-${DEMO_USER}-resource-server/invoke) → JWT
   │  ② MCP over streamable-HTTP,  Authorization: Bearer <JWT>
   ▼
[AgentCore Gateway]  protocolType=MCP, authorizer=CUSTOM_JWT
   │  ③ tool "web-search___web_search" → Lambda invoke (bedrockAgentCoreToolName)
   ▼
[Lambda: web_search]  event={query, max_results}
   │  ④ POST https://api.tavily.com/search  (Authorization: Bearer TAVILY_API_KEY)
   ▼
   {query, results:[{title,url,snippet,score}]} 반환
```

## 3. 파일 구조
```
server/                             # [목적 1] MCP 서버 = AgentCore Gateway 구축·배포
├── cognito.yaml                    # Cognito + 1 Lambda + 2 IAM Role (CFN). Gateway/Target 은 boto3.
├── lambda/web_search/handler.py    # Tavily /search 호출
├── setup_gateway.py                # boto3: create_gateway + web-search target (idempotent)
├── cleanup_gateway.py              # boto3: target + gateway 삭제
├── deploy.sh                       # CFN package+deploy → outputs → setup_gateway → .env 기록
├── teardown.sh                     # cleanup_gateway → CFN 삭제 → log group → .env 정리
└── README.md
clients/                            # [목적 2] 클라이언트 설치 = 배포된 게이트웨이에 연결
├── README.md · TESTING.md          # 개요 · 레이어별 직접 테스트 가이드
├── smoke_test.py                   # raw MCP 클라이언트 대화형 테스터
├── claude-code/{README.md, local_test.sh}      # Claude Code on Bedrock
└── cowork/{README.md, cowork-token-helper.py}  # Cowork on Bedrock 3P
.env.example / .env                 # 공유 (server가 쓰고 clients가 읽음, TAVILY_API_KEY 수동)
pyproject.toml                      # boto3 + mcp + python-dotenv (uv)
```

## 4. 도구 스키마 (`setup_gateway.py` 인라인)
```python
WEB_SEARCH_TOOL_SCHEMA = [{
    "name": "web_search",
    "description": "웹을 검색해 관련 결과(제목·URL·스니펫)를 반환. 최신 정보·뉴스·문서 조회용. 본문 전문이 아닌 스니펫만.",
    "inputSchema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query":       {"type": "string",  "description": "검색어"},
            "max_results": {"type": "integer", "description": "최대 결과 수 (기본 5, 최대 20)"},
        },
    },
}]
```

## 5. Cognito scope & 인증
- Resource server identifier: `web-search-${DEMO_USER}-resource-server`, scope `invoke`
- 전체 scope 문자열: **`web-search-${DEMO_USER}-resource-server/invoke`** (`COGNITO_GATEWAY_SCOPE`)
- Gateway `CUSTOM_JWT`: `allowedClients=[ClientId]`, `allowedScopes=[scope]`, `discoveryUrl=<UserPool OIDC>`
- 토큰: M2M `client_credentials` (워크숍 `auth_local._fetch_token_direct` 흐름 그대로)

## 6. 보안 메모
web_search 단일 도구 → Lambda가 임의 URL을 받지 않고 **고정 Tavily 엔드포인트만 호출** → SSRF/§9(URL 출처 제약) 방어 불필요. 인바운드는 Cognito CUSTOM_JWT 3중 검증(서명·audience·scope), Lambda 호출 권한은 Gateway IAM Role로 한정. `TAVILY_API_KEY`는 simple test 단계에서 Lambda 환경변수(CFN `NoEcho` 파라미터). 다음 단계에서 Secrets Manager로 승격.

## 7. 검증
1. **`smoke_test.py`** (가장 빠름): Cognito 토큰 → `streamablehttp_client(GATEWAY_URL)` → `list_tools()`에 `web-search___web_search` 확인 → `web_search(query="latest AWS news today")` 호출 후 결과 출력.
2. **Claude Code on Bedrock**: `claude mcp add --transport http web-search "<GATEWAY_URL>" --header "Authorization: Bearer <token>"` → 검색 유도 프롬프트. (M2M 토큰 ~1h 만료.)

## 8. 가정
- 언어 Python(워크숍·boto3·Lambda 일치), 런타임 `python3.13`, `uv` 사용.
- Lambda는 비-VPC(기본 인터넷 egress)로 Tavily 호출.
- 신규 standalone 스택(`web-search-${DEMO_USER}-gateway`) — 워크숍 게이트웨이에 얹지 않음.
- 배포 전제: AWS 자격증명 + 무료 Tavily 키(https://app.tavily.com, 1,000 크레딧/월).
