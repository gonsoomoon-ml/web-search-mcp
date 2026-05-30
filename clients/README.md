# clients — 배포된 게이트웨이에 연결

[목적 2] 클라이언트 설치/연결. [`../server/`](../server/)로 배포한 AgentCore Gateway(`web_search` MCP)에
각 클라이언트를 붙인다.

> **공통 전제:** `server/deploy.sh` 완료 → 루트 `.env`에 `GATEWAY_URL`·`COGNITO_*`가 채워진 상태.
> (`.env`는 git 제외. `cowork-token-helper.py`·`local_test.sh`는 위치 무관하게 루트 `.env`를 탐색한다.)

## 구성
| 경로 | 무엇 |
|---|---|
| [`smoke_test.py`](./smoke_test.py) | raw MCP 클라이언트 — 가장 빠른 E2E 검증(대화형). `uv run python clients/smoke_test.py "질문"` |
| [`TESTING.md`](./TESTING.md) | 레이어별 직접 테스트 가이드 (정적 → 핸들러 → Lambda → 게이트웨이 → Claude Code) |
| [`claude-code/`](./claude-code/) | **Claude Code on Bedrock** 연결 (`local_test.sh` = 격리 세션 자동) |
| [`cowork/`](./cowork/) | **Cowork on Bedrock 3P** 연결 (`managedMcpServers` + `headersHelper`) |

## 공통: Cognito 토큰
모든 클라이언트는 **Cognito M2M(client_credentials) JWT(~1h)**로 게이트웨이에 인증한다.
- 발급 로직: `smoke_test.py`의 `get_cognito_token()` / `cowork/cowork-token-helper.py`
- `.env`의 `COGNITO_*`로 발급 → `Authorization: Bearer <jwt>`
- 만료 처리: Claude Code는 재등록, Cowork는 `headersHelper`가 자동 갱신

## 어느 것부터?
1. **빠른 확인** → `smoke_test.py`
2. **실제 에이전트(Claude Code on Bedrock)** → [`claude-code/`](./claude-code/)
3. **Cowork(데스크톱, 3P)** → [`cowork/`](./cowork/)
