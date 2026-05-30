# Web Search 비교 리서치: Claude Cowork vs. Claude Code on Bedrock + 자체 MCP 서버

> 작성일: 2026-05-29
> 대상 PRD: [`design/prd.md`](./prd.md)
> 목적: (1) Claude Cowork의 내장 Web Search와 Claude Code on Bedrock + 자체 MCP 서버 방식의 장단점 비교, (2) MCP 방식의 단점에 대한 기술적 개선 방안 제시

---

## 0. 한 줄 결론 (TL;DR)

Bedrock을 이미 선택한 조직이라면 **"Cowork이 더 편한가?"가 아니라 "우리 데이터·거버넌스 경계 안에서 web search를 어떻게 갖출 것인가?"가 진짜 질문**이다. Cowork의 web search는 매끄럽지만 Anthropic 관리형 경로(데이터가 Anthropic 인프라를 통과)이고, **Anthropic의 `web_search`·`web_fetch` 네이티브 서버 도구는 (표준) Bedrock에서 지원되지 않는다.** 따라서 표준 Bedrock에서 web search를 쓰는 정식 경로는 사실상 **자체 MCP 서버**다. (단, AWS 계정으로 Anthropic 네이티브를 제공하는 **Claude Platform on AWS**는 web search/fetch가 내장돼 있어 직접 구축 없이 쓸 수도 있다 — [§1.2](#12-제3의-선택지-claude-platform-on-aws-build-vs-buy에-영향) 참고.) 자체 MCP는 초기 구축·운영 부담이 있지만, 아래 [기술적 개선](#5-mcp-방식의-단점에-대한-기술적-개선-방안)을 적용하면 비용·토큰·보안·이식성 측면에서 오히려 더 우수한 자산이 된다.

---

## 1. 배경: 왜 Bedrock에는 Web Search가 없는가

이것은 "AWS가 기능을 빼먹어서"가 아니라 **아키텍처상 당연한 결과**다.

```
[Claude 앱 / Anthropic First-party API]
   모델 추론 + web_search 서버도구 + 검색 인프라  ← 전부 Anthropic이 호스팅
        │
        └── web_search 결과를 Anthropic이 직접 채워서 모델에 주입 (citation 포함)

[Amazon Bedrock]
   모델 추론만 AWS가 서빙  ← Anthropic의 검색 인프라는 경로에 없음
        │
        └── "도구"는 클라이언트(당신)가 채워야 함 → 그 표준이 MCP
```

- Anthropic의 **`web_search` 도구는 "server-side tool"**이다. 즉 모델이 검색을 요청하면 *Anthropic 서버가* 검색을 실행하고 결과·인용을 모델에 돌려준다. 이 인프라는 Anthropic First-party API와 Claude 앱(=Cowork 포함)에서만 호스팅된다.
- **Bedrock은 AWS가 모델 추론(inference)만 서빙**한다. Anthropic이 운영하는 검색 백엔드는 이 경로에 포함되지 않는다. (AWS re:Post / AWS 블로그에서 `web_search_20250305` 서버도구는 Bedrock 미지원으로 확인됨.)
- 그래서 Bedrock에서 web search를 쓰려면 **클라이언트 측 도구(client-side tool)**로 직접 채워야 하고, 그 표준 프로토콜이 **MCP(Model Context Protocol)**다.

### 1.1 추가로 확인된 Bedrock 환경의 제약 (중요)

Claude Code를 Bedrock 인증으로 돌릴 때 다음이 모두 사실이다 (공식 문서 기준):

| 항목 | Bedrock 인증 시 동작 | 함의 |
|---|---|---|
| `web_search` 서버 도구 | **미지원** | 내장 web search 불가 |
| `web_fetch` 서버 도구 (`web_fetch_20250910`/`_20260209`) | **미지원** (Bedrock·Vertex 공통) | URL 본문 가져오기 네이티브 도구도 불가. Claude API·Claude Platform on AWS·MS Foundry에서만 제공 |
| claude.ai 커넥터 자동 로드 | **로드 안 됨** (Bedrock/Vertex/`ANTHROPIC_API_KEY` 사용 시) | claude.ai에서 추가한 MCP를 Bedrock 세션이 못 가져옴 |
| MCP **Tool Search**(지연 로딩) | **기본 비활성** (non-first-party host) | MCP 도구 정의가 컨텍스트에 선(先)로딩됨 → 도구를 적게/간결하게 설계해야 함 |
| MCP 서버 등록 경로 | `.mcp.json` / `claude mcp add` / `~/.claude.json` | **직접 등록이 유일한 정식 경로** |

> 결론: 표준 Bedrock에서는 "claude.ai에서 켜면 되는" 우회로가 막혀 있다. **로컬/프로젝트 스코프로 MCP 서버를 직접 붙이는 것이 사실상 유일한 방법**이며, tool search가 꺼져 있으므로 **도구 개수를 최소화(예: `web_search`, `fetch_url` 2개)하고 설명을 간결**하게 해야 컨텍스트 낭비가 없다.

### 1.2 제3의 선택지: Claude Platform on AWS (build vs buy에 영향)

표준 **Amazon Bedrock**(모델 추론만 서빙, 네이티브 web 도구 없음)과 **별개로**, AWS에는 **Claude Platform on AWS** — "Anthropic의 네이티브 플랫폼을 *당신의 AWS 계정*으로 제공" — 이 있다. 여기엔 Messages API, Claude Managed Agents(beta), 그리고 **네이티브 web search·web fetch가 포함**된다.

| 경로 | 네이티브 web search/fetch | 데이터 경계 | 직접 구축 |
|---|---|---|---|
| **표준 Amazon Bedrock** | ❌ 없음 | AWS 내 | MCP 서버 필요(본 문서 주제) |
| **Claude Platform on AWS** | ✅ 있음 | AWS 계정 경유(Anthropic 네이티브) | 불필요(켜면 됨) |
| **Anthropic First-party API / Cowork** | ✅ 있음 | Anthropic 인프라 | 불필요 |

> 함의: "AWS 경계 유지"가 핵심 동기였다면, **Claude Platform on AWS가 직접 구축 없이 네이티브 web 도구를 주는 지름길**일 수 있다. 단, ① **Claude Code가 이 엔드포인트를 타겟할 수 있는지**, ② 가용 리전·요금·계약 조건, ③ 표준 Bedrock 대비 데이터 처리 방식 차이는 **반드시 확인**해야 한다. 만약 Claude Code가 표준 Bedrock만 지원하거나, 제공자 통제·비용 최적화·사내 검색 연동이 필요하다면 **자체 MCP가 여전히 정답**이다. → [§7](#7-미해결확인-필요-사항-구축-단계-brainstorming-입력)에 확인 항목으로 추가.

### 1.3 ⚠️ 용어 정리: "web search/fetch"의 실행 위치 (혼동의 근원)

"web fetch가 client-side냐"는 **어느 도구·어느 제품이냐에 따라 답이 다르다.** 핵심: **Claude Code와 Cowork는 동일하다**(Cowork이 Claude Code 기반) — 둘 다 **web fetch = client-side, web search = server-side**다. server-side로 *fetch*하는 건 별개 API 기능인 네이티브 서버도구뿐이다.

| 도구 (출처) | 실행 위치 | 표준 Bedrock | 메모 |
|---|---|---|---|
| **Anthropic 네이티브 서버도구** `web_search`·`web_fetch_*` (별개 API 기능) | **server-side** | ❌ | First-party API·Claude Platform on AWS·MS Foundry. 검색은 **Brave 기반** |
| **Claude Code & Cowork — web search** | **server-side** (추론 제공자에서 실행) | ❌ | Vertex/Foundry/Gateway ○, **Bedrock ✗** → **진짜 공백** |
| **Claude Code & Cowork — web fetch** | **client-side** (사용자 기기의 데스크톱/CLI 프로세스가 로컬 fetch) | ⚠️/✅ | Cowork: *"runs in the Claude Desktop main process on the user's device"*, `coworkEgressAllowedHosts` 허용목록으로 egress 통제. Claude Code: 로컬 Axios + 보조 Haiku 호출(이 호출에 Bedrock 리전 버그 `#8217`), 일부 환경 기본 비활성 `#690` |
| **우리 MCP `web_search` / `fetch_url`** | **client-side** (우리 서버) | ✅ | 직접 구현·완전 통제 |

> **요지 (← 이전 초안 정정)**: Claude Code와 **Cowork 둘 다 web fetch는 client-side**(로컬에서 직접 fetch), **web search는 server-side**(추론 제공자, **Bedrock 미지원**)다. 한때 'Cowork fetch=server-side'로 적었으나 **오류**였고, 공식 Cowork 문서가 client-side로 명시한다. server-side인 *fetch*는 오직 별개 API 기능인 **네이티브 `web_fetch` 서버도구**뿐이다.
>
> **프로젝트 범위 함의(중요)**: 표준 Bedrock에서 *진짜* 막히는 건 **"search"**(server-side). **"fetch"는 client-side라 Cowork·Claude Code 모두 Bedrock에서도 동작**하지만, Claude Code 쪽은 보조 모델 호출 버그·기본 비활성으로 불안정하다. → 우리 MCP가 **search를 확실히 메우고 fetch도 안정적 대체재로** 제공하는 게 타당. 공식/커뮤니티의 Bedrock 검색 복원책도 **검색 MCP 서버(Brave/Exa) 추가** 또는 **LiteLLM 게이트웨이 경유** — 즉 **본 프로젝트가 문서화된 권장 패턴**이다. (Axios/Turndown/Haiku 등 내부 구현은 리버스 엔지니어링 기반이라 버전에 따라 변할 수 있음.)

---

## 2. 두 방식의 작동 방식

### 2.1 Claude Cowork Web Search (관리형 / 내장형)

- **Cowork이란**: Anthropic의 *agentic* 지식노동 도구. 데스크톱에서 로컬 파일·앱에 연결해 멀티스텝 작업을 끝까지 수행한다("Claude Code의 힘을 지식노동에"). 2026년 초 프리뷰를 벗어나 모든 유료 플랜(Pro/Team/Enterprise)에서 GA.
- **Web Search 동작**: 모델이 필요하다고 판단하면 Anthropic이 검색을 실행하고, **결과 스니펫·제목·URL을 인용(citation)과 함께** 모델에 주입한다. 사용자는 설정·키·제공자 선택이 전혀 필요 없다.
- **실행 위치(정정됨)**: Cowork의 **web search는 server-side**(추론 제공자 인프라에서 실행 — Vertex/Foundry/Gateway 지원, **Bedrock 미지원**)이지만, **web fetch는 client-side**다. 공식 문서: *"Web Fetch runs in the Claude Desktop main process on the user's device."* 즉 데스크톱 앱이 로컬에서 직접 fetch하고, `coworkEgressAllowedHosts` 허용목록으로 egress를 통제한다(우리 MCP §5.4의 도메인 allowlist와 같은 발상). 이는 **Claude Code와 동일한 구조**(Cowork이 Claude Code 기반)이며, 우리 MCP `fetch_url`도 같은 client-side다. 참고로 Cowork 자체도 3P 추론 제공자(Vertex/Foundry/**Bedrock**/gateway)로 구동 가능하다. → 핵심은 **search만 server-side라 Bedrock에서 공백**이라는 점이다.
- **과금**(First-party API 기준): web search **$10 / 1,000회** + 표준 토큰 비용. citation 필드(`cited_text`, `title`, `url`)는 토큰에 포함되지 않음.
- **데이터 경로**: 쿼리·결과가 Anthropic 인프라를 통과. 멀티턴에서는 결과가 암호화되어(encrypted content) 다음 호출에 되돌려진다.

### 2.2 Claude Code on Bedrock + 자체 MCP 서버 (자가 구축형)

- **구조**: Claude Code(또는 Bedrock 기반 에이전트)가 MCP 클라이언트가 되고, 당신이 만든 MCP 서버가 외부 검색 API(Brave/Tavily/Serper/Exa 등)를 호출해 결과를 돌려준다.
- **등록 방식** (공식):
  - **transport**: `stdio`(로컬 프로세스), `http`(원격, 권장), `sse`(deprecated)
  - **scope**: `local`(`~/.claude.json`, 개인), `project`(`.mcp.json`, git 공유), `user`(전 프로젝트)
  - 예시 (`.mcp.json`, 프로젝트 공유):
    ```json
    {
      "mcpServers": {
        "web-search": {
          "type": "stdio",
          "command": "${CLAUDE_PROJECT_DIR:-.}/server/run.sh",
          "args": [],
          "env": { "SEARCH_API_KEY": "${SEARCH_API_KEY}" }
        }
      }
    }
    ```
  - 또는 CLI: `claude mcp add --transport stdio --env SEARCH_API_KEY=... web-search -- npx -y our-web-search-mcp`
- **데이터 경로**: 검색 쿼리는 *당신이 고른* 검색 제공자로, 추론은 *당신의* Bedrock으로 간다. Anthropic 검색 인프라를 거치지 않는다.
- **과금**: 검색 제공자 요금(아래 [4.1](#41-검색-제공자-옵션-비교) 참고) + Bedrock 토큰 비용. web search 자체에 대한 Anthropic의 $10/1K는 없음.

---

## 3. 장단점 비교

범례: ✅ 우위 · ⚠️ 주의 · ❌ 약점

| 차원 | Claude Cowork (내장) | Claude Code on Bedrock + 자체 MCP |
|---|---|---|
| **설정·운영 부담** | ✅ 0에 가까움 (켜면 됨) | ❌ 서버 구축·키 관리·배포·유지보수 필요 |
| **Time-to-value** | ✅ 즉시 | ⚠️ 초기 며칠 (이후 재사용 자산) |
| **검색 품질·최신성** | ✅ Anthropic 튜닝, 일관됨 | ⚠️ 고른 제공자에 좌우 (잘 고르면 동급↑) |
| **인용/근거(citation)** | ✅ 기본 제공, 토큰 무과금 | ⚠️ 직접 구현해야 함 (구현하면 동급) |
| **비용 모델** | ⚠️ 고정 $10/1K + 토큰, 통제 불가 | ✅ 제공자·캐싱으로 대폭 절감 가능 (Serper ~$0.3–1/1K) |
| **통제·커스터마이징** | ❌ 블랙박스 (제공자/필터/도메인 제어 불가) | ✅ 제공자·도메인 allowlist·랭킹·후처리 완전 통제 |
| **데이터 경로·프라이버시** | ⚠️ Anthropic 인프라 경유 | ✅ 데이터가 당신의 AWS/제공자 경계 내 |
| **거버넌스·규정준수** | ⚠️ Anthropic 계약·정책에 종속 | ✅ AWS IAM/VPC/PrivateLink/감사로그로 통합 |
| **배포 모델 적합성** | ❌ Bedrock 표준 경로와 별개(데스크톱/claude.com) | ✅ 이미 Bedrock을 쓰는 조직과 정합 |
| **이식성(portability)** | ❌ Cowork/Anthropic 종속 | ✅ MCP 호환 클라이언트 어디서나 재사용 |
| **보안 리스크(프롬프트 인젝션)** | ✅ Anthropic이 일부 완화 | ❌ 외부 콘텐츠 주입 → **직접 방어 필요** |
| **가용성·SLA** | ✅ Anthropic 운영 | ⚠️ 당신이 책임 (제공자 장애·레이트리밋 포함) |
| **관측성(로그/메트릭)** | ❌ 내부 가시성 거의 없음 | ✅ 쿼리·지연·비용·실패를 직접 계측 |
| **오프라인/사내망** | ❌ 불가 | ✅ 사내 검색엔진·인트라넷 색인도 연결 가능 |

### 3.1 요약
- **Cowork이 이기는 곳**: 설정 부담, 즉시성, 기본 인용, 보안 기본기 — *"빨리·편하게"*.
- **Bedrock+MCP가 이기는 곳**: 통제, 비용, 데이터 경계, 거버넌스, 이식성, 관측성 — *"우리 방식대로·확장 가능하게"*.
- **핵심**: 이미 Bedrock을 택한 조직(데이터 거버넌스/리전/AWS 통합이 이유)에게 Cowork은 *그 선택의 이유를 부정*한다. 그래서 PRD의 방향(자체 MCP)이 합리적이다.

---

## 4. MCP 방식의 단점 (정리)

PRD의 질문 — "MCP 방식이 단점이 많으면 어떻게 개선하나?" — 에 답하기 위해 단점을 먼저 명확히 한다.

1. **구축·운영 부담**: 서버 코드, 키 관리, 배포, 모니터링, 버전 업그레이드를 직접.
2. **검색 품질의 변동성**: 제공자 선택·랭킹·후처리에 따라 결과 품질이 들쭉날쭉.
3. **인용/근거 부재(기본값)**: 직접 구현하지 않으면 답변 신뢰성·추적성이 떨어짐.
4. **토큰 폭증 위험**: 검색 결과 원문을 통째로 모델에 넣으면 컨텍스트·비용이 폭발. (Bedrock은 tool search 비활성 → 도구 정의도 컨텍스트 차지)
5. **보안(프롬프트 인젝션)**: 웹 콘텐츠에 숨은 지시문이 모델을 조종할 수 있음. 공식 문서도 "외부 콘텐츠를 가져오는 서버는 prompt injection 위험"을 경고.
6. **비용 가시성·폭주**: 에이전트가 무분별하게 검색하면 제공자 요금이 급증.
7. **지연시간(latency)**: 검색 + (원문 fetch) + 모델 호출이 직렬화되면 느려짐.
8. **신뢰성**: 제공자 장애·레이트리밋·타임아웃에 대한 폴백 부재 시 취약.
9. **거버넌스 일관성**: 팀원마다 다른 설정/키를 쓰면 재현성·감사 어려움.

---

## 5. MCP 방식의 단점에 대한 기술적 개선 방안

각 단점을 **구체적 설계로 해소**한다. 굵게 표시한 두 가지가 가장 큰 레버다.

### 5.0 핵심 설계 원칙 두 가지

> **(A) 2-도구 분리: `web_search` + `fetch_url`**
> - `web_search(query, count)` → **스니펫·제목·URL·발행일만** 반환 (원문 X). 토큰 절약 + 모델이 "어디를 더 읽을지" 판단.
> - `fetch_url(url)` → 선택된 페이지만 본문 추출(가독성 정제·길이 제한)해 반환.
> - 효과: 토큰 폭증(단점 4)·비용(6)·지연(7)을 동시에 통제. Bedrock의 tool search 비활성 환경에서도 **도구 2개·설명 간결**이라 컨텍스트 부담 최소.
> - ⚠️ **이름 주의**: 이 `web_search`/`fetch_url`은 *우리가 구현하는 클라이언트측 MCP 도구*다. Anthropic의 동명 **네이티브 서버도구**(`web_search`/`web_fetch_*`, **Bedrock 미지원**)와 무관하다. fetch 도구를 굳이 `web_fetch`로 부르면 네이티브와 혼동되므로 `fetch_url`/`read_url`을 권장한다 — 모델은 이름이 아니라 *도구 설명*으로 인식하므로 명명은 자유다.
>
> **(B) 제공자 추상화 계층(Provider Interface)**
> - `SearchProvider` 인터페이스 뒤에 Brave/Tavily/Serper/Exa 구현을 두고 **환경변수로 스왑**.
> - 효과: 품질 변동(2)·비용(6)·벤더 종속을 해소. A/B 테스트·폴백·멀티-제공자 병합이 쉬워짐.

### 5.1 검색 제공자 옵션 비교 (단점 2·6)

> ⚠️ 가격은 2026년 시점의 공개 정보 기준, **반드시 최신 요금 재확인**. 단위 환산 주의(쿼리당 vs 1K당).

| 제공자 | 대략 가격 | 강점 | 적합 케이스 |
|---|---|---|---|
| **Serper** | ~$0.30–1.00 / 1K (무료 2,500/월) | 가장 저렴, 구글 SERP 원형 | 자체 LLM으로 후처리, 비용 최우선·대량 |
| **Brave Search (Data for AI)** | 무료~$5/월 저볼륨, Pro $5/월 2K | 독립 색인, 인포박스/뉴스/포럼 등 풍부, LLM 그라운딩 설계 | 균형형, 독립 인덱스 선호 |
| **Tavily** | ~$0.008/쿼리(= $8/1K) | LLM 소비 최적화(랭킹 스니펫·관련도·인용 포맷) | 빠른 고품질, 적은 후처리 |
| **Exa** | 검색 ~$0.001/result (+추출 별도) | 신경망/의미 기반 검색 | 의미적 탐색·유사문서 발견 |

> 💡 **품질 우려를 줄이는 사실**: Anthropic의 네이티브 `web_search`(= Cowork가 쓰는 것)도 **내부 검색 제공자로 Brave Search를 사용**한다. 따라서 자체 MCP에서 **Brave를 고르면 Cowork/네이티브와 동일한 검색 인덱스**를 우리 경계 안에서 쓰는 셈이라, "자체 구축 시 품질 저하" 우려가 크게 줄어든다.
>
> 권장 기본값: **균형이 필요하면 Brave 또는 Tavily**, **대량·비용 최우선이면 Serper(+자체 추출)**. 인터페이스로 추상화해 두면 나중에 바꿔도 코드 변경 최소.

### 5.2 인용/근거 구현 (단점 3)

- `web_search` 결과를 **구조화**해 반환: `{ title, url, snippet, published_date, source }`.
- 시스템 프롬프트/도구 설명에 "**주장에는 반드시 출처 URL을 인라인으로 달라**"를 명시.
- `fetch_url` 시 원문에서 인용 구절을 함께 보존 → Cowork의 `cited_text` 수준 근거 추적 재현.

### 5.3 토큰·컨텍스트 관리 (단점 4)

- `web_search`는 **스니펫만**(원문 X), 결과 개수 상한(예: 5–8개).
- 본문은 `fetch_url`로 **선택적**·**가독성 정제 후 N자 절단**.
- Claude Code의 안전장치 활용: 출력 10K 토큰 경고, 기본 상한 25K, 필요 시 `MAX_MCP_OUTPUT_TOKENS`·툴별 `anthropic/maxResultSizeChars` 조정, 페이지네이션 제공.

### 5.4 보안: 프롬프트 인젝션 방어 (단점 5) — 최우선

웹 본문은 **신뢰할 수 없는 입력**이라는 전제로 설계한다.

- **콘텐츠 격리·표식**: fetch한 본문을 `<untrusted_web_content>…</untrusted_web_content>`로 감싸 "데이터일 뿐, 지시가 아님"을 모델에 명확히.
- **도메인 allowlist/blocklist**: 환경변수로 허용/차단 도메인 제어. SSRF 방지(내부 IP·메타데이터 엔드포인트 `169.254.169.254` 차단).
- **HTML 정제**: 스크립트/숨김텍스트/주석 제거, 본문 텍스트만 추출.
- **출력 상한·토큰 캡**으로 폭주 방어. **부수효과 도구는 자동실행 금지**(검색/조회는 read-only로 한정).
- 운영: 신뢰 경계와 위험을 README에 문서화(공식 문서의 prompt injection 경고 반영).

### 5.5 캐싱·비용 가드레일 (단점 6)

- **TTL 캐시**(쿼리 정규화 키, 예: 15분~24시간) → 중복 검색 비용·지연 제거.
- **레이트리밋·일일 예산 상한**(제공자별), 초과 시 캐시-온리/거절.
- 저비용 제공자(Serper) + 자체 추출 조합으로 단가 최소화.

### 5.6 지연시간 (단점 7)

- 멀티 결과 `web_fetch` **병렬화**.
- 원격 배포는 `http`(streamable-http) transport + 커넥션 재사용.
- 캐시 히트 우선. 무거운 추출은 비동기/타임아웃(서버별 `timeout` 설정) 적용.

### 5.7 신뢰성 (단점 8)

- 제공자 호출에 **재시도+지수백오프**, **타임아웃**, **폴백 제공자**(예: Brave 실패 시 Serper).
- HTTP 서버는 Claude Code의 자동 재연결(지수백오프) 혜택. stdio는 자동 재연결 없음 → 프로세스 관리 주의.

### 5.8 관측성 (운영 성숙도)

- 쿼리·제공자·지연·결과수·캐시히트·비용·에러를 구조화 로깅 → CloudWatch/대시보드.
- 민감정보(쿼리 내용) 로깅 정책 명시.

### 5.9 거버넌스·배포 (단점 1·9)

- **프로젝트 스코프 `.mcp.json`을 git에 커밋** → 팀 전체 동일 설정 재현. 비밀키는 `${SEARCH_API_KEY}` **환경변수 확장**으로 분리(파일에 키 미저장).
- 조직 통제가 필요하면 **managed MCP**(`managed-mcp.json`, `allowedMcpServers`)로 서버 셋 고정.
- **배포 형태 선택**:

| 형태 | transport | 적합 | 비고 |
|---|---|---|---|
| 로컬 stdio | `stdio` | 개인 개발·빠른 시작 | 키는 `--env`/환경변수 |
| 사내 공유 HTTP | `http` | 팀·CI·여러 클라이언트 | AWS Lambda/ECS/App Runner, IAM·PrivateLink·OAuth로 보호, 캐시·예산 중앙화 |

> 성숙 단계 권장: **개발은 stdio로 시작 → 안정화되면 사내 HTTP 서비스로 승격**(중앙 캐시·예산·감사·보안 일원화). 이러면 단점 1·6·8·9가 한 번에 개선된다.

---

## 6. 권장 아키텍처 (결정)

```
Claude Code (Bedrock 인증)
   │  MCP (stdio→차후 http)
   ▼
[web-search MCP 서버]   ← 우리 코드 / 우리 경계
   ├─ tool: web_search(query,count)  → 스니펫·URL·날짜만
   ├─ tool: fetch_url(url)           → 정제 본문(+인용 보존)
   ├─ SearchProvider 인터페이스       → Brave | Tavily | Serper | Exa (env 스왑)
   ├─ 보안: untrusted 표식 · 도메인 allowlist · SSRF 차단 · HTML 정제
   ├─ 비용: TTL 캐시 · 레이트리밋 · 일일 예산
   ├─ 신뢰성: 재시도/백오프/타임아웃/폴백 제공자
   └─ 관측성: 구조화 로깅(쿼리/지연/비용/에러)
        │
        ▼
   외부 검색 API (선택한 제공자)
```

- **MVP**: stdio + 단일 제공자(Brave 또는 Tavily) + `web_search`/`fetch_url` 2도구 + 기본 캐시 + untrusted 표식.
- **v2**: 제공자 추상화·폴백, 도메인 allowlist, 예산/레이트리밋, 관측성.
- **v3**: 사내 HTTP 서비스로 승격(IAM/PrivateLink/OAuth, 중앙 캐시·예산·감사).

---

## 7. 미해결/확인 필요 사항 (구축 단계 brainstorming 입력)

- **(선결) Claude Platform on AWS 검토**: Claude Code가 이 엔드포인트를 타겟할 수 있는가? 가용 리전·요금·계약·데이터 처리 방식은? → 가능하다면 직접 구축 없이 네이티브 web search/fetch 확보 가능하므로 **build vs buy를 먼저 재평가**. (불가/부적합 시 아래 자체 MCP 진행)
- 검색 **제공자 1차 선택**(Brave vs Tavily vs Serper)과 예산 상한?
- **fetch 범위 결정**: 내장 `WebFetch`(client-side)를 그대로 쓸지 vs 자체 `fetch_url` 제공할지? (내장은 Bedrock 보조모델 버그·기본 비활성 리스크 → 안정성·통제 위해 자체 제공 권장. search는 어차피 자체 필수.)
- 서버 **구현 언어**(TypeScript/Python)와 배포 타깃(로컬 only vs 사내 공유)?
- **데이터 거버넌스 요건**(검색 쿼리 외부 전송 허용 범위, 리전, 로깅 정책)?
- 인용 **출력 포맷** 요건(인라인 각주 vs 출처 목록)?
- 사내망/인트라넷 **내부 검색 소스** 연동 필요 여부?

> 다음 단계로 "MCP 서버 구축"을 진행할 때는 위 질문들을 brainstorming에서 먼저 확정한 뒤 구현에 들어가는 것을 권장한다.

---

## 부록 A. 출처 (2026-05 확인)

- [Web Search for Anthropic Models in Bedrock — AWS re:Post](https://repost.aws/questions/QUSd3wAByQTtyzUPzgqss3TQ/web-search-for-anthropic-models-in-bedrock)
- [Integrate dynamic web content using a web search API and Amazon Bedrock Agents — AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/integrate-dynamic-web-content-in-your-generative-ai-application-using-a-web-search-api-and-amazon-bedrock-agents/)
- [Tool use — Amazon Bedrock Docs](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-anthropic-claude-messages-tool-use.html)
- [Claude Cowork — Anthropic](https://www.anthropic.com/product/claude-cowork) · [Cowork — claude.com](https://claude.com/product/cowork)
- [Connect Claude Code to tools via MCP — Claude Code Docs](https://code.claude.com/docs/en/mcp)
- [Web search tool — Claude API Docs](https://docs.claude.com/en/docs/agents-and-tools/tool-use/web-search-tool) · [Introducing web search on the Anthropic API](https://www.anthropic.com/news/web-search-api)
- [Search API Pricing Compared 2026 — Awesome Agents](https://awesomeagents.ai/pricing/search-api-pricing/) · [Best Web Search APIs for AI — Firecrawl](https://www.firecrawl.dev/blog/best-web-search-apis) · [AI Search API Pricing — buildmvpfast](https://www.buildmvpfast.com/api-costs/ai-search)
