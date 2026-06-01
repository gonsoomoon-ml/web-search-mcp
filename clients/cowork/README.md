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
| **Headers** *(데모용 — 1h 재입력)* | **+ Add** → Key `Authorization`, Value `Bearer <token>` | `Authorization` : `Bearer eyJ...`(발급 토큰) |
| **Headers helper script** *(in-app/configLibrary 경로는 미적용 — 자동갱신은 STEP 3d mobileconfig)* | (비움) | (비움 — STEP 3d 사용) |
| **Tool policy** | **+ Add** → tool `web_search` → `allow` | `web_search` → `allow` |

> **"값(일반 형식)"** = 다른 환경/사람용 placeholder, **"현재 값"** = 이 배포의 예시. URL은 `.env`의 `GATEWAY_URL`, helper 경로는 repo `pwd` 기준.

→ **"Test this connection"**(Apply 전 helper+게이트웨이 왕복 검증) → **Save Changes → Apply Changes** → **Cowork 완전 종료 후 재시작**.

> **인증 방법 두 가지:** ① 정적 `Headers`(Authorization: Bearer) = 빠르지만 ~1h 재입력(데모, 2026-05-31 실측). ② **headersHelper = 자동갱신** — 단 in-app/configLibrary 가 아니라 **mobileconfig(관리형 prefs)로 등록해야 동작** → **STEP 3d 권장**(2026-06-01 실측).
> in-app UI 의 `Headers helper script` 필드는 configLibrary 에 기록되는데, 그 경로의 helper 는 Cowork 이 *호출은 하나 요청에 미적용*이다. **자동갱신을 원하면 이 필드는 비우고 STEP 3d(mobileconfig)** 를 쓴다.
> (데모로 정적 헤더를 쓸 경우) 토큰을 발급해 클립보드로 복사 → Headers의 `Authorization` Value에 붙여넣기(Cmd+V):
> ```bash
> clients/cowork/cowork-token-helper.py | python3 -c 'import json,sys;print(json.load(sys.stdin)["Authorization"])' | tr -d '\n' | pbcopy
> ```
> ⚠️ 정적 토큰은 **~1h 만료** → 만료 시 위 명령으로 재발급·재입력 후 **Cowork 재시작**(launch 시 1회만 읽음). **재입력이 싫으면 STEP 3d(mobileconfig headersHelper) = 자동 갱신.**

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

### 3d. mobileconfig 프로파일 — **자동갱신 동작 ✅ (권장, 2026-06-01 실측)**
`headersHelper`는 **configLibrary 가 아니라 관리형 prefs 레이어**에 등록해야 Cowork 가 요청에 적용한다(위 핵심 발견). `install-mobileconfig.py`가 그 프로파일을 만들어 준다 — 사용자의 기존 inference 설정은 보존하고, 우리 게이트웨이용 `managedMcpServers`(headersHelper)만 관리형 prefs 로 주입.
```bash
git pull                                                  # newline+캐싱 helper 포함
python3 clients/cowork/install-mobileconfig.py            # .mobileconfig 생성 (+ configLibrary 의 managedMcpServers 정리)
open ~/.cache/web-search-mcp/web-search-mcp.mobileconfig  # → System Settings 에서 프로파일 승인(서명 없음 경고는 정상)
```
- 설치 직후(재시작 전) 관리형 prefs 진입 확인: `defaults read "/Library/Managed Preferences/$(whoami)/com.anthropic.claudefordesktop" managedMcpServers`
- **Cowork Cmd+Q → 재시작 → web_search 트리거.** 이제 helper 가 TTL마다 자동 호출되어 **~1h 만료 재입력이 불필요**(장기 세션 유지).
- 검증 로그: `tail -4 ~/.cache/web-search-mcp/token-helper.log` → `cache hit` / `OK wrote header`.
- **원복:** System Settings → Privacy & Security → Profiles 에서 프로파일 삭제. (정적 헤더로 돌아가려면 `cp <id>.json.bak <id>.json` 후 재시작.)

> 동작 메커니즘(실측): Cowork 가 cold mint 1.67s 를 끝까지 기다려 헤더를 받음(타임아웃 무관), 이후 캐시 적중 3ms. configLibrary 에 같은 helper 를 넣었을 땐 호출돼도 미적용 → 레이어가 결정적.

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
| **~1h 만료 처리** | ❌ 자동 갱신 없음 → 재발급+재입력+재시작 | ✅ TTL마다 자동 재발급 (**동작**) | ✅ Cowork이 자동 *(되면)* |
| **현재 상태** | ✅ **동작 확인** (2026-05-31) | ✅ **동작 확인** (2026-06-01, **관리형 prefs 프로파일 경유**) | ❓ **미검증** (sign-in 모델이라 안 될 공산 큼) |
| **입력 필드** | Headers: `Authorization` = `Bearer <token>` | Headers helper script: helper 절대경로 (**configLibrary 아닌 mobileconfig 에 등록**) | Client ID / secret / Authorization server / Tenant ID |
| **우리 케이스 판정** | 빠른 데모용(1h 재입력) | **권장 — 자동갱신 동작** (STEP 3d = `install-mobileconfig.py`) | 사실상 부적합 (Cognito를 authorization_code로 재구성해야) |

> AgentCore Gateway는 **무인증 미지원** — `create-gateway`의 `authorizer-type`이 필수이며 enum은 `CUSTOM_JWT`(Bearer)·`AWS_IAM`(SigV4)뿐, `NONE` 없음(CLI 확인 2026-05-31). Cowork(Bearer 클라이언트)엔 `CUSTOM_JWT`(Cognito)가 매칭 → ①~③ 중 **① 정적 헤더(데모)와 ② headersHelper(자동갱신) 둘 다 동작**.
>
> **핵심 발견(2026-06-01):** ② headersHelper 는 **어느 레이어에 등록하느냐**가 결정적. **configLibrary** 에 넣으면 Cowork 가 helper 를 *호출은 하지만 그 출력을 요청 헤더에 적용하지 않음*("Missing Bearer token"). **관리형 prefs 레이어(macOS configuration profile = `.mobileconfig`)** 에 넣어야 honor 됨. (+ helper 출력은 **trailing newline 필수** — 미종료 라인은 폐기됨.) → STEP 3d.

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
   - ✅ **`headersHelper` 자동갱신 동작 (2026-06-01 실측, STEP 3d)** — 이전의 "미작동"은 **두 버그 중첩**이었음: ① 출력 **trailing newline 부재**(Cowork reader 가 미종료 라인 폐기 → "Missing Bearer token"), ② **잘못된 레이어** — headersHelper 를 **configLibrary** 에 넣으면 *호출은 되나 요청 미적용*, **관리형 prefs(mobileconfig)** 에 넣어야 honor. 진단 결정타 = helper 에 `~/.cache/web-search-mcp/token-helper.log` 호출-추적 로깅을 넣어 "Cowork 가 helper 를 *호출은 함*"을 입증(가설 역전). 로그 실측: cold mint 1671ms 를 Cowork 가 끝까지 대기(타임아웃 무관, BrokenPipe 없음), 이후 캐시 적중 3ms. → **정적 헤더는 데모용, 자동갱신 운영은 `install-mobileconfig.py`.**
2. macOS 관리설정 도메인 `com.anthropic.claudefordesktop`(일부 페이지 `com.anthropic.claudecode` 표기) — `defaults read`로 실측.
3. `headersHelper` 호출 타임아웃 정확값 미문서화 → helper를 가볍게 유지(우리 건 단순 토큰 발급).
4. `COGNITO_CLIENT_SECRET`가 `.env` 평문 — 단일 머신 테스트 OK, 운영은 Secrets Manager/키체인.

## 한 줄 요약
> Cowork 3P는 `claude mcp add` 불가 → `managedMcpServers`로 등록. **빠른 데모 = 정적 Headers**(STEP 3a, ~1h 재입력), **운영(자동갱신) = headersHelper 를 mobileconfig(관리형 prefs)로 등록**(STEP 3d = `install-mobileconfig.py`).
> 핵심(2026-06-01 실측): in-app/configLibrary 의 headersHelper 는 *호출돼도 요청에 미적용* — **관리형 prefs 레이어 + 출력 newline 종료**라야 동작. Transport=Streamable HTTP, OAuth=None.


## Reference

- https://github.com/hi-space/websearch-agentcore-gateway/blob/main/cowork/setup-mac.sh
