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

## STEP 3 — Cowork에 등록 (단일 머신)

### 3a. in-app UI — 가장 쉬움 ✅ (스크린샷 확인, 권장)
**Developer → Configure third-party inference → 왼쪽 "Connectors & extensions" → MCP SERVERS의 "Managed MCP servers" → "+ Add server"** → 폼에 아래 값 입력:

| 폼 필드 | 값 (일반 형식 — 본인 값으로) | 현재 값 (예시) |
|---|---|---|
| **Name** | `web-search` | `web-search` |
| **Transport** | **Streamable HTTP** (= 우리 http) | `Streamable HTTP` |
| **URL** | `.env`의 `GATEWAY_URL` | `https://web-search-gsmoon-gateway-ot0el1g06p.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp` |
| **OAuth** | **None** | `None` |
| **Headers** *(현재 동작 ✅)* | **+ Add** → Key `Authorization`, Value `Bearer <token>` | `Authorization` : `Bearer eyJ...`(발급 토큰) |
| **Headers helper script** *(자동갱신 목표 — 현재 미작동)* | (비워둠) | (비워둠) |
| **Tool policy** | **+ Add** → tool `web_search` → `allow` | `web_search` → `allow` |

> **"값(일반 형식)"** = 다른 환경/사람용 placeholder, **"현재 값"** = 이 배포의 예시. URL은 `.env`의 `GATEWAY_URL`, helper 경로는 repo `pwd` 기준.

→ **"Test this connection"**(Apply 전 helper+게이트웨이 왕복 검증) → **Save Changes → Apply Changes** → **Cowork 완전 종료 후 재시작**.

> **인증 — 현재 동작 확인된 방법 = 정적 `Headers`(Authorization: Bearer)** (2026-05-31 실측).
> `Headers helper script`(headersHelper)는 필드는 있으나 **단일-사용자 3P에서 Cowork이 호출/사용하지 않아 미작동** → helper 필드는 **비우고** 정적 헤더 사용.
> 토큰을 발급해 클립보드로 복사 → Headers의 `Authorization` Value에 붙여넣기(Cmd+V):
> ```bash
> clients/cowork/cowork-token-helper.py | python3 -c 'import json,sys;print(json.load(sys.stdin)["Authorization"])' | tr -d '\n' | pbcopy
> ```
> ⚠️ 정적 토큰은 **~1h 만료** → 만료 시 위 명령으로 재발급·재입력 후 **Cowork 재시작**(launch 시 1회만 읽음). 자동 갱신(headersHelper)은 [조사 중](#확인-메모-스크린샷-실측-2026-05-31).

### 3b. 자동 스크립트 (UI 대신, 파일에 직접)
```bash
python3 clients/cowork/install-managed-mcp.py
```
활성 `configLibrary/<id>.json`(=`_meta.json`의 `appliedId`)을 찾아 `managedMcpServers`를 추가한다. **기존 키(자격증명 포함) 보존 + `.bak` 백업 + 멱등.** → Cowork 재시작.

### 3c. 설정 파일 손편집
활성 `<id>.json`을 열면 `inferenceProvider`·`inferenceModels` 등 **최상위 키**가 있다. 그 **형제로 `managedMcpServers`를 추가**(STEP 2의 JSON):
```json
{
  "inferenceProvider": "bedrock",
  "inferenceModels": [ ... ],
  "managedMcpServers": [
    { "name": "web-search", "url": "<GATEWAY_URL>", "transport": "http",
      "headersHelper": "<repo 절대경로>/clients/cowork/cowork-token-helper.py",
      "headersHelperTtlSec": 3000, "toolPolicy": { "web_search": "allow" } }
  ]
}
```
> 로컬 파일은 JSON **객체**로 직접(MDM store만 "JSON 문자열"). 저장 → 재시작.

<details><summary><b>조직 배포(MDM, 다수 머신) — .mobileconfig 프로파일</b></summary>

Export 버튼으로 **`.mobileconfig`(macOS)/`.reg`(Windows)** 받아 Jamf/Kandji/Intune·GPO로 배포.
- 프로파일에선 값을 **JSON 문자열**로(`inferenceModels`처럼). 즉:
  `<key>managedMcpServers</key><string>[{"name":"web-search","url":"<GATEWAY_URL>","transport":"http","headersHelper":"<abs>/clients/cowork/cowork-token-helper.py","headersHelperTtlSec":3000,"toolPolicy":{"web_search":"allow"}}]</string>`
- macOS 도메인 `com.anthropic.claudefordesktop`. Windows `HKLM\SOFTWARE\Policies\Claude`.
- 우선순위: 관리(MDM) 소스가 있으면 그것이 이기고 로컬값 무시(in-app 창 read-only).
</details>

---

## 인증 방법 비교 (Cowork ↔ 게이트웨이)

| 항목 | ① 정적 Headers (Bearer) | ② Headers helper script | ③ OAuth (Bring your own client) |
|---|---|---|---|
| **Cowork이 토큰 얻는 법** | 사용자가 발급한 토큰을 헤더에 직접 붙여넣음 | Cowork이 지정 실행파일을 돌려 stdout 헤더 JSON 사용 | Cowork이 IdP와 OAuth 토큰 교환을 직접 수행 |
| **맞는 인증 모델** | 아무 Bearer 토큰 | 아무 Bearer (프로그램이 발급) | 사용자 sign-in (authorization_code) |
| **우리 M2M 게이트웨이 적합성** | ✅ 맞음 (우리 M2M 토큰 그대로) | ✅ 설계상 딱 맞음 (`cowork-token-helper.py`=M2M 발급) | ⚠️ 불일치 (우리는 client_credentials, 사용자·브라우저 없음) |
| **~1h 만료 처리** | ❌ 자동 갱신 없음 → 재발급+재입력+재시작 | ✅ TTL마다 자동 재발급 *(되면)* | ✅ Cowork이 자동 *(되면)* |
| **현재 상태** | ✅ **동작 확인** (2026-05-31) | ❌ **미작동** (단일-사용자 3P에서 Cowork이 호출 안 함) | ❓ **미검증** (sign-in 모델이라 안 될 공산 큼) |
| **입력 필드** | Headers: `Authorization` = `Bearer <token>` | Headers helper script: helper 절대경로 | Client ID / secret / Authorization server / Tenant ID |
| **우리 케이스 판정** | **현재 유일한 동작 경로** | 되면 최선, 지금은 안 됨(원인 조사) | 사실상 부적합 (Cognito를 authorization_code로 재구성해야) |

> AgentCore Gateway는 **무인증 미지원** — `create-gateway`의 `authorizer-type`이 필수이며 enum은 `CUSTOM_JWT`(Bearer)·`AWS_IAM`(SigV4)뿐, `NONE` 없음(CLI 확인 2026-05-31). Cowork(Bearer 클라이언트)엔 `CUSTOM_JWT`(Cognito)가 매칭 → ①~③ 중 **①만 현재 동작**.

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

## 확인 메모 (스크린샷 실측, 2026-05-31)
1. ✅ **E2E 검증됨 (2026-05-31) — 정적 `Headers`(Authorization: Bearer)로**. 단일-사용자 in-app "+ Add server"에 Name/Transport/URL/OAuth/Headers/Headers helper script/Tool policy + "Test this connection" 필드가 있고, **정적 헤더로 등록 시 Cowork이 `web_search`를 자율 호출(멀티스텝)해 정확한 결과+인용 반환** 확인(질의 "삼성전자 주가" → 317,000원, 출처 매일경제/Daum). → **게이트웨이/Cognito/Lambda/Tavily 전 경로 정상**.
   - ❌ **`Headers helper script`(headersHelper) 미작동** — helper 단독 실행은 되나 Cowork(단일-사용자 3P)이 호출/사용하지 않음. 원인 후보(조사 중): Cowork이 helper를 실행하는 환경의 PATH/`env python3` 해석, 샌드박스, 호출 타임아웃, 또는 in-app/configLibrary 경로에서 headersHelper 미지원(MDM 프로파일 전용일 가능성). → 현재는 **정적 헤더 + ~1h 재입력**이 동작 경로.
2. macOS 관리설정 도메인 `com.anthropic.claudefordesktop`(일부 페이지 `com.anthropic.claudecode` 표기) — `defaults read`로 실측.
3. `headersHelper` 호출 타임아웃 정확값 미문서화 → helper를 가볍게 유지(우리 건 단순 토큰 발급).
4. `COGNITO_CLIENT_SECRET`가 `.env` 평문 — 단일 머신 테스트 OK, 운영은 Secrets Manager/키체인.

## 한 줄 요약
> Cowork 3P는 `claude mcp add` 불가 → **in-app "Connectors & extensions → Managed MCP servers → + Add server"**에서 등록(STEP 3a).
> Transport=**Streamable HTTP**, OAuth=**None**, **Headers helper script**=`cowork-token-helper.py` 절대경로 → ~1h Cognito JWT 자동 갱신, 장기 세션도 안 끊긴다.
