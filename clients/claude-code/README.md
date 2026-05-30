# 로컬 Claude Code on Bedrock — web-search 게이트웨이 테스트

로컬 Mac/Linux의 Claude Code(Bedrock 인증)가 우리 AgentCore Gateway를 MCP 서버로 써서
실제로 웹 검색하는지 검증하는 가이드. **긴 명령 붙여넣기 없이** 스크립트 한 번으로 끝납니다.

> 사전: 이 머신에서 `deploy.sh` 완료 → `.env`에 `GATEWAY_URL`·`COGNITO_*` 채워짐.
> (`.env`는 git 제외라 clone엔 없음 — 배포한 머신에서 하거나 `.env`를 복사하세요.)

---

## 방법 A — 헬퍼 스크립트 (권장, 명령 1개)

다른 8~9개 MCP 서버를 전혀 안 건드리고, **web-search만 격리**해서 Claude Code를 띄웁니다.

```
./clients/claude-code/local_test.sh
```

스크립트가 하는 일: ① Cognito 토큰 발급 → ② web-search만 담은 임시 config 작성
→ ③ `claude --strict-mcp-config`로 격리 세션 실행 → 종료 시 임시 config 삭제.

세션이 뜨면:
1. `/mcp` 입력 → `web-search` 도구 하나만 보이는지 확인
2. 질문:
   ```
   Amazon Bedrock AgentCore 최신 뉴스를 웹에서 검색하고 출처 URL과 함께 한국어로 요약해줘.
   ```
3. 도구 사용 권한 프롬프트 뜨면 **허용**
4. 끝나면 평소대로 종료(`/exit` 또는 Ctrl-D) → 기존 MCP 설정 그대로

### 성공 판정
- Claude가 `web-search___web_search` 도구를 호출
- 실제 최신 URL(aboutamazon / aws.amazon.com 등)이 든 한국어 요약 반환
- ✅ → 로컬 Claude Code on Bedrock ↔ 게이트웨이 통합 완결

---

## 방법 B — 격리 대신 "경쟁 서버만 잠깐 제거" (수동, 짧은 명령들)

스크립트가 안 맞거나, 이미 `claude mcp add`로 등록해둔 web-search를 그대로 쓰고 싶을 때.
각 명령이 짧아 붙여넣기 안전합니다.

```
cp ~/.claude.json ~/.claude.json.bak
```
```
claude mcp remove builder-mcp
```
```
claude mcp remove aws-knowledge-mcp-server-mcp
```
```
claude mcp list
```
→ `web-search ✓ Connected` 남고 위 둘이 사라졌는지 확인. 그 다음:
```
export CLAUDE_CODE_USE_BEDROCK=1
```
```
export AWS_REGION=us-east-1
```
```
export ENABLE_TOOL_SEARCH=false
```
```
claude
```
세션에서 위 방법 A의 1~3번과 동일하게 테스트.

### 복원 (테스트 끝나면)
```
cp ~/.claude.json.bak ~/.claude.json
```
```
claude mcp list
```
→ 제거했던 서버들이 모두 돌아왔는지 확인.

---

## 트러블슈팅

| 증상 | 해결 |
|---|---|
| `400 Tool reference not found` | `ENABLE_TOOL_SEARCH=false` 확인 (방법 A는 자동 설정) |
| `/mcp`에서 web-search **failed** | 토큰 만료(~1h). 방법 A는 재실행하면 새 토큰. 방법 B는 `claude mcp remove web-search` 후 재등록 |
| Claude가 다른 검색 도구 사용 | 방법 A(격리)를 쓰거나, 프롬프트에 "web-search 서버의 web_search 도구로" 명시 |
| 토큰 발급 시 도메인 not found | `COGNITO_DOMAIN` 확인 / 도메인 프로비저닝 1분 대기 |
| 도구는 부르는데 빈 결과 | `.env`의 `TAVILY_API_KEY` 유효성 / 크레딧 확인 |
| `.env` 값이 비어있음 | 이 머신에서 `deploy.sh` 미실행 (`.env`는 clone에 없음) |

## 보안 메모
- Cognito 토큰은 ~1시간 만료 + "내 게이트웨이 호출"만 가능한 저위험 토큰. 채팅/로그에 붙여넣지 말 것.
- 방법 B에서 `claude mcp add` 헤더 토큰은 `~/.claude.json`에 평문 저장됨 → 테스트 후 `claude mcp remove web-search` 권장.
