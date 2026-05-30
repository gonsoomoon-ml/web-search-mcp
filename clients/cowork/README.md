# Cowork on Bedrock(3P)에 web_search 붙이기 — 시작 가이드

우리 AgentCore Gateway(streamable-HTTP MCP + Cognito CUSTOM_JWT, **~1h 만료**)를
**Claude Cowork on Bedrock(3P 모드)**의 MCP 도구로 노출한다. clone부터 순서대로 따라가면 된다.

> 관련: [`../claude-code/README.md`](../claude-code/README.md)(Claude Code on Bedrock 연결) · [`../../design/cowork-vs-bedrock-realusecase.md`](../../design/cowork-vs-bedrock-realusecase.md)
> 공식 근거: [/cowork/3p/installation](https://claude.com/docs/cowork/3p/installation) · [/cowork/3p/configuration](https://claude.com/docs/cowork/3p/configuration) · [/cowork/3p/extensions](https://claude.com/docs/cowork/3p/extensions) · [/cowork/3p/bedrock](https://claude.com/docs/cowork/3p/bedrock)(추론만). 일부 단계는 **실측 필요**(맨 아래 참고).

---

## 사전 조건
- 게이트웨이가 **배포되어 있고**(`server/deploy.sh` 완료) 루트 `.env`에 `GATEWAY_URL`·`COGNITO_*`가 채워짐. (안 됐으면 [`../../server/`](../../server/) 먼저.)
- **macOS/Windows 데스크톱** + `python3` (headersHelper 실행용).
- Cowork 3P가 Bedrock 추론으로 구성됨 — 안 됐으면 **STEP 0**.

---

## STEP 0 (한 번만) — Cowork 3P 설치 + Bedrock 추론 구성
이미 Cowork on Bedrock을 쓰고 있으면 건너뛴다.
1. [claude.com/download](https://claude.com/download)에서 Claude 데스크톱 설치(Claude.app → Applications).
2. 메뉴 **Help → Troubleshooting → Enable Developer Mode**.
3. **Developer → Configure third-party inference** 창 열기 → provider=**Bedrock**, region, 자격증명(Bearer token/AWS profile/SSO) 입력 → **Apply locally**.
   - *3P는 Anthropic 로그인 불필요.* 추론 설정 상세는 [/cowork/3p/bedrock](https://claude.com/docs/cowork/3p/bedrock).

---

## STEP 1 — repo 받고 headersHelper 준비
```bash
git clone https://github.com/gonsoomoon-ml/web-search-mcp   # 또는 기존 repo면 git pull
cd web-search-mcp
# .env 가 없으면: server/deploy.sh 를 돌린 머신의 .env 를 복사 (GATEWAY_URL·COGNITO_* 필요)
chmod +x clients/cowork/cowork-token-helper.py
python3 clients/cowork/cowork-token-helper.py        # → {"Authorization":"Bearer eyJ..."} (exit 0) 면 OK
pwd                                                  # 절대경로 메모 (STEP 2에서 사용)
```
> `cowork-token-helper.py`는 `.env`의 `COGNITO_*`로 토큰을 발급해 **헤더 JSON 한 줄**을 출력한다(Cowork `headersHelper` 계약). 위치 무관(`.env`를 위로 탐색).

---

## STEP 2 — `managedMcpServers` 항목 만들기
> **`managedMcpServers`는 설정의 "최상위 키"** 이름이다(화면에 그대로 보이는 라벨이 아님). 그 **값**이 MCP 서버 배열이다.

`<GATEWAY_URL>`은 `.env`의 값, `headersHelper`는 STEP 1 helper의 **절대경로**(`<pwd>/clients/cowork/cowork-token-helper.py`):
```json
"managedMcpServers": [
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
이 `"managedMcpServers": [...]` 한 덩어리를 **설정 파일/프로파일의 최상위에** 넣는다(STEP 3).

---

## STEP 3 — `managedMcpServers`를 설정에 넣기 (단일 머신)
`managedMcpServers` 키는 **3P 설정 파일**(`configLibrary/<id>.json`)의 최상위에 들어간다.

### 3a. 자동 스크립트 — 가장 쉬움 ✅ (권장)
```bash
python3 clients/cowork/install-managed-mcp.py
```
활성 `<id>.json`(=`_meta.json`의 `appliedId`)을 찾아 `GATEWAY_URL`(.env)·helper 절대경로로
`managedMcpServers`를 추가한다. **기존 키(추론 자격증명 포함) 보존 + `.bak` 백업 + 멱등.**
→ 이후 **Cowork 완전 종료 후 재시작**.

### 3b. 설정 파일 직접 편집 (수동)
```bash
# 1) 설정 디렉토리 확인
ls ~/Library/Application\ Support/Claude-3p/configLibrary/        # _meta.json + <id>.json 들
# 2) 활성 설정 파일이 무엇인지 (_meta.json 이 가리킴)
cat ~/Library/Application\ Support/Claude-3p/configLibrary/_meta.json
```
활성 `<id>.json`을 열면 이미 `inferenceProvider`·`inferenceBedrockRegion`·`inferenceModels` 같은 **최상위 키들**이 있다. 그 **형제로 `managedMcpServers` 키를 추가**한다:
```json
{
  "inferenceProvider": "bedrock",
  "inferenceBedrockRegion": "us-east-1",
  "inferenceModels": [ ... ],
  "managedMcpServers": [
    {
      "name": "web-search",
      "url": "https://web-search-<id>.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp",
      "transport": "http",
      "headersHelper": "/ABS/PATH/web-search-mcp/clients/cowork/cowork-token-helper.py",
      "headersHelperTtlSec": 3000,
      "toolPolicy": { "web_search": "allow" }
    }
  ]
}
```
> 로컬 파일은 JSON **객체**로 직접 넣는다(`.mobileconfig`/registry 같은 MDM store만 값을 "JSON 문자열"로 인코딩). 저장 → **Cowork 완전 종료 후 재시작**(설정은 launch 시 1회만 읽음).

### 3c. in-app 창 (대안)
Developer → Configure third-party inference → 왼쪽 **"Connectors & extensions"** 섹션 → MCP 서버 추가 → **"Apply locally"**(같은 `configLibrary/`에 기록) → 재시작.
> ⚠️ 화면엔 `managedMcpServers`라는 글자가 아니라 "MCP servers"/"Connectors" 같은 **라벨**로 보인다. single-user 창이 이 편집을 노출하는지 문서 미확정 → **안 보이면 3a**.

<details><summary><b>조직 배포(MDM, 다수 머신)</b></summary>

같은 창에서 **`.mobileconfig`(macOS)/`.reg`(Windows)** export → Jamf/Kandji/Intune·Group Policy로 배포.
- macOS 도메인 `com.anthropic.claudefordesktop` → `/Library/Managed Preferences/` (이때는 값을 **JSON 문자열**로).
- Windows `HKLM\SOFTWARE\Policies\Claude`(machine) / `HKCU\...`(user).
- 우선순위: 관리(MDM) 소스가 있으면 그것이 이기고 로컬값은 무시(in-app 창 read-only).
</details>

---

## STEP 4 — 확인
Cowork에서:
1. `web_search`(또는 `web-search`) 도구가 노출되는지 확인.
2. 프롬프트:
   ```
   "Amazon Bedrock AgentCore" 최신 뉴스를 web_search 도구로 검색해 출처 URL과 함께 한국어로 요약해줘.
   ```
   기대: Cowork이 게이트웨이 `web_search` 호출 → 실제 Tavily 결과 → 한국어 합성.
3. **1시간 경과 후에도** 끊김 없는지 확인(headersHelper가 TTL마다 토큰 재발급).

문제 시: `defaults read "/Library/Managed Preferences/com.anthropic.claudefordesktop"`로 키 확인(MDM 경로). 401이면 helper 토큰의 audience/scope가 게이트웨이 요구와 일치하는지 점검.

---

## 참고 — managedMcpServers 필드
| 필드 | 의미 |
|---|---|
| `url` | `https://` 필수. 게이트웨이 MCP 엔드포인트(끝에 `/mcp`) |
| `transport` | `http`(기본) / `sse` / `stdio`. 우리는 `http` |
| `headersHelper` | 헤더 JSON을 stdout으로 출력하는 실행파일 **절대경로** |
| `headersHelperTtlSec` | helper 출력 캐시 초. 토큰 만료(~3600)보다 짧게 **3000** 권장 |
| `toolPolicy` | 도구별 `allow`/`ask`/`blocked` |

> `headers`(정적)·`headersHelper`·`oauth`는 **상호배타**. 우리는 `headersHelper`만 사용.
> ✅ 공식: *"Any MCP server reachable over HTTPS works with Cowork on 3P"*(우리 게이트웨이 지원), `isLocalDevMcpEnabled` 기본 `true`, 원격 MCP는 `managedMcpServers`(admin)만.

## 하지 말 것 (안티패턴)
- **`oauth: true`(동적 등록)** — Cognito **M2M(client_credentials)**는 브라우저 authorization_code+PKCE와 비호환. (configuration 문서에 사전등록 OAuth `clientId`/`clientSecret`/`scope`도 있으나 M2M엔 `headersHelper`가 단순.)
- **정적 `headers` Bearer (운영)** — 1h 후 만료, launch 시 1회만 읽어 갱신 없음. 데모 한정.
- **claude.ai Connectors UI** — static Bearer 미지원 + DCR 미노출 + egress가 Anthropic 클라우드.
- **`claude mcp add`** — Claude Code(CLI) 전용. Cowork 3P엔 안 됨.

## 실측 필요 (문서로 확정 못 함)
1. 단일-사용자 in-app 창의 `managedMcpServers` 편집 노출 여부 → STEP 3 fallback 준비.
2. macOS 관리설정 도메인 `com.anthropic.claudefordesktop`(일부 페이지 `com.anthropic.claudecode` 표기) — `defaults read`로 실측.
3. `headersHelper` 호출 타임아웃 정확값 미문서화 → helper를 가볍게 유지(우리 건 단순 토큰 발급).
4. `COGNITO_CLIENT_SECRET`가 `.env` 평문 — 단일 머신 테스트 OK, 운영은 Secrets Manager/키체인.

## 한 줄 요약
> Cowork 3P는 `claude mcp add` 불가 → **`managedMcpServers`로 프로비저닝**(단일 머신은 in-app "Configure third-party inference" → Connectors & extensions → Apply locally).
> `transport:"http"` + **`headersHelper`(=`cowork-token-helper.py`)**면 ~1h Cognito JWT가 자동 갱신되어 장기 세션도 안 끊긴다.
