# web-search-mcp

Claude Code / Cowork **on Amazon Bedrock**에 web search를 추가하는 MCP 서버 + 클라이언트.
Bedrock은 Anthropic 네이티브 `web_search`(server-side)를 미지원 → **AgentCore Gateway(관리형 MCP)**에
client-side `web_search` 도구를 호스팅해 그 공백을 메운다.

## 구조 (두 목적 분리)
- **[`server/`](./server/)** — [목적 1] **MCP 서버**: AgentCore Gateway + Tavily Lambda 구축·배포 (CFN + boto3). *조직당 1회 배포.*
- **[`clients/`](./clients/)** — [목적 2] **클라이언트 연결**: 배포된 게이트웨이에 Claude Code / Cowork / raw 테스터 붙이기. *사용자·머신마다 설치.*
- **[`design/`](./design/)** — 리서치·설계 문서 (왜 MCP인가 → 무엇을 재구현 → 실사용 비교).
- `.env` / `.env.example` / `pyproject.toml` — **공유** (server가 `.env`를 채우고 clients가 읽음).

## 빠른 시작
```bash
uv sync && cp .env.example .env                              # .env 에 TAVILY_API_KEY 입력
./server/deploy.sh                                           # 게이트웨이 배포 (~3-5분)
uv run python clients/smoke_test.py "latest AWS news today"  # 검증
./server/teardown.sh                                         # 정리 (과금 중단)
```

## 클라이언트 연결
- Claude Code on Bedrock → [`clients/claude-code/`](./clients/claude-code/)
- Cowork on Bedrock 3P → [`clients/cowork/`](./clients/cowork/)
- 빠른 raw MCP 테스터 → [`clients/smoke_test.py`](./clients/smoke_test.py)
- 레이어별 테스트 가이드 → [`clients/TESTING.md`](./clients/TESTING.md)

레퍼런스 패턴: `gonsoomoon-ml/aiops-multi-agent-workshop` (`infra/cognito-gateway`).
