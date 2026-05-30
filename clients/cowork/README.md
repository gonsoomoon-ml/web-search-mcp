# Cowork on Bedrock(3P)에 web_search 게이트웨이 붙이기

우리 AgentCore Gateway(streamable-HTTP MCP + Cognito CUSTOM_JWT, **~1h 만료**)를
**Claude Cowork on Bedrock(3P 모드)**의 MCP 도구로 노출하는 설정 가이드.

> 검증: 아래 키·동작은 **공식 문서를 직접 fetch해 확인**(2026-05-30). MCP 설정은 [/cowork/3p/configuration](https://claude.com/docs/cowork/3p/configuration)("Configuration reference")와 [/cowork/3p/extensions](https://claude.com/docs/cowork/3p/extensions)("MCP, plugins, skills, and hooks")에 있고, [/cowork/3p/bedrock](https://claude.com/docs/cowork/3p/bedrock)("Deploy Cowork on 3P with Amazon Bedrock")은 **추론 설정만**(MCP 없음). 즉 **"Cowork on Bedrock의 MCP 설치 = bedrock 페이지(추론) + configuration/extensions 페이지(MCP) 조합."** AWS [COWORK_3P.md](https://github.com/aws-solutions-library-samples/guidance-for-claude-code-with-amazon-bedrock/blob/main/assets/docs/COWORK_3P.md)도 추론 위주. 잔여 실측 항목은 §6.
> 관련: [`../claude-code/README.md`](../claude-code/README.md)(Claude Code on Bedrock), [`cowork-vs-bedrock-realusecase.md`](../../design/cowork-vs-bedrock-realusecase.md)

---

## 0. 핵심 (먼저 읽기)

| 항목 | 결론 |
|---|---|
| Cowork 3P가 MCP 지원? | **예.** 3P에서 비활성되는 건 Chat 탭·Computer Use·Skills Marketplace(Anthropic 호스팅 추론 필요)뿐. MCP는 지원. |
| 등록 방식 | **`managedMcpServers`(관리자 프로비저닝)만.** 사용자가 in-app/`claude mcp add`로 추가 **불가**. |
| ~1h Cognito JWT 대응 | **`headersHelper`**(토큰 생성 실행파일) + `headersHelperTtlSec`로 자동 갱신. 정적 `headers`는 만료되므로 비권장. |
| Claude Code와 차이 | Code=`claude mcp add`(static 헤더, 만료 시 재등록). Cowork=managed + headersHelper(1급 갱신). |

**✅ 공식 확인(직접 fetch):** *"Any MCP server reachable from the user's device over HTTPS works with Cowork on 3P"* → 우리 게이트웨이(remote HTTP)는 **공식 지원**. `isLocalDevMcpEnabled` 기본값 = **true**(공식). 원격 MCP는 admin-provisioned(`managedMcpServers`)만, 사용자 in-app 추가는 불가.

> **사전 조건:** Cowork이 이미 Bedrock 3P 추론으로 구성됨(`inferenceProvider=bedrock` 등 — 본 문서 범위 밖). 게이트웨이는 `deploy.sh`로 배포되어 `.env`에 `GATEWAY_URL`·`COGNITO_*`가 채워진 상태.

---

## 1. headersHelper 스크립트 — `cowork-token-helper.py` (이미 제공)

`clients/cowork/cowork-token-helper.py`. `.env`의 `COGNITO_*`를 읽어 Cognito
client_credentials 토큰을 발급하고 **`{"Authorization":"Bearer <jwt>"}` 한 줄만 stdout**으로 출력한다
(Cowork headersHelper 계약). CWD 무관(`__file__` 기준 `.env` 탐색).

단독 검증:
```bash
chmod +x clients/cowork/cowork-token-helper.py
python3 clients/cowork/cowork-token-helper.py
# → {"Authorization": "Bearer eyJ..."}  (exit 0)
```

> ⚠️ helper 의 stdout 은 **헤더 JSON만** — 로그/진단은 stderr 로. 비-zero exit 는 실패 처리됨.

---

## 2. `managedMcpServers` 엔트리

`<GATEWAY_URL>`=`.env`의 값, `headersHelper`=스크립트 **절대경로**:

```json
[
  {
    "name": "web-search",
    "url": "https://web-search-<id>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
    "transport": "http",
    "headersHelper": "/ABS/PATH/web-search-mcp/clients/cowork/cowork-token-helper.py",
    "headersHelperTtlSec": 3000,
    "toolPolicy": { "web_search": "allow" }
  }
]
```

| 필드 | 의미 |
|---|---|
| `url` | `https://` 필수. 게이트웨이 MCP 엔드포인트(끝에 `/mcp`) |
| `transport` | `http`(기본) / `sse` / `stdio`. 우리는 `http` |
| `headersHelper` | 헤더 JSON을 stdout으로 출력하는 실행파일 절대경로 |
| `headersHelperTtlSec` | 헬퍼 출력 캐시 초. 토큰 만료(~3600)보다 짧게 **3000** 권장 |
| `toolPolicy` | 도구별 `allow`/`ask`/`blocked` |

> `headers`(정적)·`headersHelper`·`oauth`는 **상호배타**. 우리는 `headersHelper`만 사용.

---

## 3. 배포 → 재시작 → 확인

관리설정 store(plist/registry)에서 **배열/객체 값은 JSON 문자열로 인코딩**해야 함.

### 경로 A — 단일 머신(데모/검증)
로컬 configLibrary에 추가:
- macOS: `~/Library/Application Support/Claude-3p/configLibrary/` (활성 설정 = `_meta.json`이 가리키는 `<id>.json`)
- Windows: `%LOCALAPPDATA%\Claude-3p\configLibrary\`

### 경로 B — 조직 배포
Claude Desktop → Help → Troubleshooting → **Enable Developer mode** → Developer →
"Configure third-party inference"에서 검증 후 **`.mobileconfig`(macOS)/`.reg`(Windows)** export →
Jamf/Kandji/Intune·Group Policy로 배포:
- macOS 도메인: `com.anthropic.claudefordesktop` → `/Library/Managed Preferences/`
- Windows: `HKLM\SOFTWARE\Policies\Claude`(machine) 또는 `HKCU\SOFTWARE\Policies\Claude`(user)

> **우선순위:** 관리(MDM) 소스가 있으면 그것이 이기고 로컬값은 무시됨(병합 없음). in-app 설정창은 read-only가 됨.

### 확인
```bash
# macOS — managedMcpServers 키 확인
defaults read "/Library/Managed Preferences/com.anthropic.claudefordesktop"
```
- **Cowork 완전 종료 후 재시작**(설정은 launch 시 1회만 읽음)
- Cowork에서 `web_search` 도구 노출 확인 → 검색 프롬프트로 호출
- **1시간 경과 후에도** 끊김 없는지(headersHelper 재호출로 갱신) 확인

---

## 4. 검증 프롬프트(예)
```
"Amazon Bedrock AgentCore" 최신 뉴스를 web_search 도구로 검색해 출처 URL과 함께 한국어로 요약해줘.
```
기대: Cowork이 우리 `web_search`(게이트웨이) 호출 → 실제 Tavily 결과 → 한국어 합성.

---

## 5. 하지 말 것 (안티패턴)
- **`oauth: true`(동적 등록)** — Cognito **M2M(client_credentials)**는 브라우저 authorization_code+PKCE와 비호환(유저/브라우저/refresh 없음). (참고: configuration 문서엔 사전등록 OAuth 옵션 `clientId`/`clientSecret`/`scope`/`clientSecretHelper`도 있음 — Cognito와 client_credentials OAuth 직결 가능성은 추가 검토 여지이나, M2M엔 `headersHelper`가 더 단순.)
- **정적 `headers` Bearer (운영)** — 1h 후 만료, launch 시 1회만 읽어 자동 갱신 없음. 데모 한정.
- **claude.ai Connectors UI** — static Bearer 미지원 + 게이트웨이가 DCR(RFC 7591) 미노출 → 자동 OAuth 등록 실패. 게다가 egress가 Anthropic 클라우드에서 나감(로컬 아님).
- **`claude mcp add`** — Claude Code(CLI) 전용. Cowork 3P엔 적용 안 됨.

---

## 6. 실측 필요 (문서로 확정 못 함)
1. **macOS 관리설정 도메인** — `com.anthropic.claudefordesktop`으로 확인되나 일부 페이지가 `com.anthropic.claudecode` 표기. 대상 머신에서 `defaults read`로 실측.
2. **단일 머신 configLibrary 활성 config JSON에 `managedMcpServers`를 끼우는 정확한 위치** — 경로는 확인, 끼우는 지점은 실측 권장.
3. **headersHelper 호출 타임아웃** 정확값 미문서화 → 헬퍼를 가볍게 유지(우리 건 단순 토큰 발급뿐).
4. **`COGNITO_CLIENT_SECRET`가 `.env` 평문** — 단일 머신 테스트 OK, 운영은 Secrets Manager/OS 키체인에서 런타임 로딩 권장.
5. **`transport:"stdio"`(mcp-remote 브리지)** — extensions 문서가 "local stdio command servers" 지원을 명시(✅ stdio 자체는 OK). 단 mcp-remote를 원격 게이트웨이 브리지로 쓰는 패턴은 실측 권장. 우리는 `http`+headersHelper가 1급이라 불필요.

> **§6 갱신 메모(2026-05-30 직접 fetch):** 이전 "실측 필요"였던 `isLocalDevMcpEnabled` 기본값(=true)과 "원격 HTTP MCP 동작 여부"는 **공식 문서로 해소됨**(§0 참고). 남은 1~5는 여전히 대상 환경 실측 권장.

---

## 7. 한 줄 요약
> Cowork 3P에선 `claude mcp add`가 안 되고, **관리자가 `managedMcpServers`로 프로비저닝**한다.
> 우리 게이트웨이는 `transport:"http"` + **`headersHelper`(=`cowork-token-helper.py`)**로 등록하면
> ~1h Cognito JWT가 자동 갱신되어 장기 세션도 끊기지 않는다.
