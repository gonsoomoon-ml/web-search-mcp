# Claude Cowork Web Search 고급 기능 → 자체 MCP 재구현 매핑

> 작성일: 2026-05-29
> 관련 문서: [`design/research-comparison.md`](./research-comparison.md) · [`design/prd.md`](./prd.md)
> 목적: Claude Cowork(= Anthropic 네이티브 `web_search`/`web_fetch` 서버도구)의 **모든 고급 기능을 열거**하고, 각각을 **Claude Code on Bedrock용 자체 MCP 서버**(`web_search` + `fetch_url`)에서 어떻게 재구현할지 매핑한다.
> 근거: deep-research 하니스(에이전트 95개 · 소스 15개 · 주장 65개 추출 → 25개 검증 → 24개 확정 · 1개 기각). 3표 적대적 검증(2/3 반박 시 폐기).

---

## 0. 한 줄 결론 (TL;DR)

**Cowork의 web search는 별도 기능이 아니라 Anthropic 네이티브 `web_search`/`web_fetch` 서버도구를 그대로 쓰는 것**이다. 따라서 "Cowork 고급 기능"의 정확한 명세 = 네이티브 도구 스펙이며, 그게 곧 우리가 MCP로 재현할 목표다. 파라미터성 기능(도메인 필터·사용 횟수·결과 상한·인용·콘텐츠 추출)은 거의 자명하게 복제된다. **진짜 난점은 "기능"이 아니라 "강제(enforcement) 계층"** — URL 출처 제약·프롬프트 인젝션 검사·egress 봉쇄·SSRF 방어 — 이고, 이것이 Cowork이 매끄러워 보이는 진짜 이유다.

---

## 1. 핵심 인식: 무엇을 "복제"하는가

- **네이티브 도구 = 기능 + 강제 계층의 묶음.** `allowed_domains` 같은 파라미터는 쉽게 복제되지만, "모델이 임의 URL을 못 만들게 막는 규칙"은 *프롬프트가 아니라 서버측에서* 강제된다. 복제 난이도는 파라미터가 아니라 이 강제 계층에 있다.
- **Bedrock 공백의 정확한 경계** (2026-05-29 기준, 공식 문서):
  - `web_search`·`web_fetch` 둘 다 **표준 Amazon Bedrock 미지원**.
  - `web_fetch`는 **Vertex AI도 미지원**.
  - 단, **"Claude Platform on AWS"(≠ 표준 Bedrock)는 지원** — 문서가 이 둘을 의도적으로 구분한다. → build vs buy 선결 검토 대상([research-comparison §1.2](./research-comparison.md)).
  - 네이티브 `web_search`는 Claude API에서 **$10 / 1,000회**.

---

## 2. 전체 기능 매핑 표

범례: **난도** = 자체 MCP 재구현 난이도 · `[보안]` = 보안 강제 계층(재구현의 핵심 난점) · **무** = 재구현 불필요.

```
+----+----------------------+------------------------------+--------------------------------+------+
| #  | 기능 (Native)        | 명세 디테일                  | 자체 MCP 재구현                | 난도 |
+----+----------------------+------------------------------+--------------------------------+------+
| 1  | 도메인 allow/block   | allowed/blocked_domains      | env allowlist; Tavily/Exa 위임 | 낮음 |
| 2  | 사용 횟수 상한       | max_uses→max_uses_exceeded   | 요청 카운터 + 예산상한         | 낮음 |
| 3  | 결과 개수 상한       | 쿼리당 max 20, 기본 5        | count 파라미터, 상한 강제      | 낮음 |
| 4  | 인용 (web_search)    | 항상 ON; cited_text 150자    | 결과 구조화; 토큰 미과금       | 낮음 |
| 5  | 인용 (web_fetch)     | 선택적; char_location 오프셋 | 본문 문자 오프셋 보존          | 중간 |
| 6  | agentic 멀티스텝     | 단일 요청 내 검색 반복       | 재구현 불필요 (CC가 처리)      | 무   |
| 7  | freshness/page_age   | page_age=최종 갱신 시점      | published_date 패스스루        | 낮음 |
| 8  | encrypted_content    | 멀티턴 연속성 암호화         | 재구현 불필요 (평문 반환)      | 무   |
| 9  | [보안] URL 출처 제약 | 맥락에 등장한 URL만; 250자   | stateless 근사: 토큰/프록시    | 높음 |
| 10 | 콘텐츠 추출/정제     | max_content_tokens 절단      | Readability→md, N토큰 절단     | 중간 |
| 11 | 관련도 하이라이트    | 쿼리 관련 발췌만             | Exa highlights; 토큰 16x↓      | 중간 |
| 12 | 동적 필터링          | _20260209; 코드실행 필요     | MVP 밖; §10·11로 대체          | 보류 |
| 13 | [보안] 인젝션 검사   | 분류기로 출력 검사           | untrusted 표식 + 스캔          | 높음 |
| 14 | [보안] egress 봉쇄   | allowlist=능력 부여          | egress 프록시; 세션검증        | 높음 |
| 15 | [보안] SSRF/DNS      | DNS 리바인딩 TOCTOU          | Smokescreen; DNS 핀 고정       | 높음 |
| 16 | rate limit           | too_many_requests            | 재시도/백오프/폴백             | 중간 |
+----+----------------------+------------------------------+--------------------------------+------+
```

### 2.1 표 항목 상세 주석

- **#1 도메인 필터**: `allowed_domains`/`blocked_domains`는 한 요청에 동시 설정 불가, 서브도메인 매칭 적용, 조직 레벨 추가 제약. 검색 결과·fetch 대상 모두에 적용.
- **#2 사용 횟수**: web_search `max_uses`는 요청당 검색 횟수, web_fetch `max_uses`는 페치 횟수(기본값 없음). 초과 시 `max_uses_exceeded`. MCP는 턴 경계가 약하므로 일·시간 윈도우 예산으로 대체.
- **#4 인용(search)**: **항상 켜짐**. `web_search_result_location` = url, title, `encrypted_index`, `cited_text`(≤150자). **cited_text/title/url은 토큰 미과금**.
- **#5 인용(fetch)**: **선택적**(`citations.enabled`). `char_location` = document_index, document_title, start/end_char_index, cited_text. (PDF는 `page_location`의 start/end_page_number로 인용 — char 오프셋 아님.)
- **#6 agentic 루프**: 단일 요청 내 "검색→결과→재검색" 반복 후 최종 인용 응답(`pause_turn`). **재구현 불필요** — Claude Code 자체가 도구를 반복 호출하는 에이전트다. MCP는 1회 검색/페치만 잘 반환하면 됨.
- **#8 encrypted_content**: 멀티턴 연속성용 Anthropic 서버측 암호화. 우리는 평문 본문+오프셋만 반환하면 됨 — 재구현 불필요.
- **#11 하이라이트**: 멀티스텝 에이전트엔 전문보다 **관련 발췌**가 핵심. Exa 자료 기준 "500자 하이라이트 ≈ 8000자 전문 정확도, 토큰 16배 절감"(벤더 수치이나 lost-in-the-middle 문헌과 정성적으로 일치).
- **#12 동적 필터링**: `web_fetch_20260209`(2026-02 출시)에서 Claude가 코드를 작성·실행해 페치 콘텐츠를 컨텍스트 진입 전 필터. **코드실행 도구 필요** → MVP 범위 밖. 우리는 #10·#11(서버측 절단·하이라이트)로 대체.

---

## 3. 가장 중요한 결론: 어려운 건 파라미터가 아니라 **보안 4종**

표의 `[보안]` 4개(#9·#13·#14·#15)가 재구현 노력의 대부분이자, 네이티브가 "매끄럽게" 보이는 진짜 이유다. 나머지는 거의 자명하게 복제된다.

### 3.1 #9 URL 출처 제약 — 가장 미묘 (핵심 설계 결정)

네이티브 web_fetch는 **대화 맥락에 이미 등장한 URL만** 페치 가능하다(사용자 메시지 / 이전 web search·fetch 결과). 모델이 만든 임의 URL은 금지(`url_not_allowed`), URL 250자 상한. 이는 **데이터 유출(exfiltration) 방지**를 위해 *서버측에서* 강제된다.

문제: **우리 MCP 서버는 stateless라 "그 URL이 맥락에 있었는지" 모른다.** 이게 이 프로젝트의 핵심 미해결 설계 결정이다.

- **옵션 A (실용적·MVP 권장)**: 프로토콜로 강제하지 않고, `fetch_url`을 **read-only + 도메인 allowlist + SSRF 프록시** 뒤에 둬서 위험을 통제. Claude Code가 자체적으로 "검색→페치" 순서를 밟으므로 실무상 "맥락 URL"과 거의 일치.
- **옵션 B (엄격)**: `web_search`가 반환한 각 URL에 서버가 **단기 토큰/해시**를 발급 → `fetch_url`은 그 토큰을 가진 URL만 수락. "이전 검색 결과에서 온 URL만" 규칙을 stateless하게 근사.

### 3.2 #13 인젝션 검사 & #14 egress 봉쇄

- 페치 본문은 **신뢰 불가 입력**. `<untrusted_web_content>…</untrusted_web_content>` 표식이 1차 방어("데이터일 뿐, 지시 아님").
- 네이티브는 신뢰 도구의 출력조차 공격면으로 보고, 프록시가 반환값을 **분류기(작고 빠른 모델)로 검사** 후 컨텍스트에 주입한다.
- **재구현 가능성 실증**: 오픈소스 MCP egress firewall **pipelock**이 Strict(allowlist-only) / Balanced(기본, 유출 탐지) / Audit(로그만) 모드 + 다중패스 정규화(zero-width/homoglyph/leetspeak) 스캔(block/strip/warn/ask)으로 구현. **단, 패턴 매칭 탐지기는 우회 가능 — 메커니즘 증명일 뿐 보증은 아니다.**
- **Cowork 사고의 교훈**: allowlist를 "목적지 필터"로만 봤다가 허용 도메인 `api.anthropic.com` 경유로 파일 유출당함. 수정책은 VM 내부 **MITM 프록시**가 VM 자신의 세션 토큰을 검증하고 공격자 주입 키를 거부하는 것. → **allowlist = 능력 부여**이며, 허용 도메인의 *모든 엔드포인트가 공격면*이 된다.

### 3.3 #15 SSRF / DNS 리바인딩 — fetch_url 최대 잔여 위험

- **수동 IP 차단 리스트를 직접 짜지 말 것.** 공격자는 octal/hex/IPv4-mapped IPv6 인코딩으로 커스텀 파서를 우회한다.
- 핵심 위협은 **TOCTOU(DNS 리바인딩)**: 검증 시점엔 안전 IP, 요청 시점엔 내부 IP로 바뀜. → **DNS 결과를 check-use 간 핀 고정**.
- 권장: **Stripe Smokescreen** 같은 egress 프록시로 내부 목적지를 설계상 차단. 실제 2026 CVE(WeKnora web_fetch SSRF 등)로 악용 가능성 확인.
- ⚠️ **출처 주의**: 차단 IP 대역(10/8, 172.16/12, 192.168/16, 127/8, `169.254.169.254` 메타데이터, fc00::/7, fe80::/10)의 근거는 **RFC 9728이 아니라 OWASP SSRF Prevention**을 인용할 것 — 리서치 검증에서 RFC 9728 §7.7 귀속은 폐기된(1-2) 유일한 주장이다.

---

## 4. 검색 백엔드(제공자) 선택

자체 `web_search`가 위임할 백엔드 — 표의 #1·#3·#7·#10·#11 대부분을 **off-the-shelf로** 제공한다.

```
+--------+---------------------------+-------------+-----------------------------+------------------------+
| 제공자 | 도메인 필터               | 결과 상한   | 콘텐츠 추출                 | 비고                   |
+--------+---------------------------+-------------+-----------------------------+------------------------+
| Tavily | include 300 / exclude 150 | 20 (기본 5) | raw_content(md), chunks 1-3 | LLM 소비 최적화        |
| Exa    | include / exclude 각 1200 | —           | text / highlights / summary | 의미 검색 + 하이라이트 |
| Brave  | (네이티브가 내부 사용)    | —           | —                           | Cowork와 동일 인덱스   |
+--------+---------------------------+-------------+-----------------------------+------------------------+
```

- **Tavily**: `include_domains`(≤300)/`exclude_domains`(≤150), `max_results`(기본5, ≤20), `include_raw_content`(boolean 또는 markdown/text), `chunks_per_source`(1-3, advanced depth 한정).
- **Exa**: `includeDomains`/`excludeDomains`(각 ≤1200), 콘텐츠 3모드 = text(전문 md) / **highlights**(쿼리 관련 발췌) / summary(LLM 요약). #11 하이라이트의 가장 직접적 구현.
- **Brave**: 네이티브 web_search가 내부적으로 Brave 사용 → 고르면 **Cowork와 같은 인덱스**를 우리 경계 안에서. "자체 구축 시 품질 저하" 우려를 크게 줄임.
- ⚠️ 이들은 **검색 결과 도메인 필터**일 뿐, **네트워크 레이어 egress 제어**(Smokescreen/pipelock)와는 별개다 — 견고한 서버는 두 계층 모두 필요.

---

## 5. 권장 구현 범위 (단계)

[research-comparison §6](./research-comparison.md)의 MVP/v2/v3 단계와 정합.

- **MVP**: stdio + 단일 제공자(Brave 또는 Tavily) + `web_search`/`fetch_url` 2도구 + 기본 캐시 + `<untrusted_web_content>` 표식 + 구조화 인용(#1·#3·#4·#10) + **#9 보안 옵션 A** + **#15 SSRF 프록시**.
- **v2**: 제공자 추상화·폴백, #5 인용 오프셋, #11 하이라이트, #13 인젝션 스캔, 예산/레이트리밋, 관측성.
- **v3**: 사내 HTTP 서비스 승격 + #14 egress 봉쇄(MITM/세션검증), 중앙 캐시·예산·감사, **#9 옵션 B**(토큰 발급) 검토.

---

## 6. 미해결 / 확정 필요 (다음 brainstorming 입력)

1. **#9 stateless 강제** — 옵션 A(프록시로 위험 통제) vs B(검색 발급 토큰)? → MVP는 A 권장.
2. **freshness** — 어느 백엔드가 `page_age` 동등 필드를 주는가? (제공자별 가용성 확인)
3. **백엔드 1차 선택** — Tavily vs Exa vs Brave (비용·지연·랭킹·결과 상한).
4. **캐싱/레이트리밋** — TTL·dedup 전략(반복 에이전트 루프 대비). 네이티브는 `too_many_requests` 외 문서화된 캐시 동작 없음.
5. **인용 출력 포맷** — 인라인 각주 vs 출처 목록(#4·#5).

---

## 부록 A. 출처 (2026-05 확인, 검증 통과분)

- [Web search tool — Claude Docs](https://platform.claude.com/docs/en/docs/agents-and-tools/tool-use/web-search-tool) *(primary)*
- [Web fetch tool — Claude Docs](https://platform.claude.com/docs/en/docs/agents-and-tools/tool-use/web-fetch-tool) · [docs.anthropic.com 미러](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/web-fetch-tool) *(primary)*
- [How we contain Claude — Anthropic Engineering](https://www.anthropic.com/engineering/how-we-contain-claude) *(primary; egress·분류기·MITM 프록시)*
- [Claude Cowork exfiltrates files — PromptArmor](https://www.promptarmor.com/resources/claude-cowork-exfiltrates-files) · Embrace The Red *(secondary; 유출 PoC)*
- [MCP Security Best Practices](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices) *(primary; SSRF/DNS 핀)*
- [Stripe Smokescreen](https://github.com/stripe/smokescreen) · [OWASP SSRF](https://owasp.org/www-community/attacks/Server_Side_Request_Forgery) *(primary; egress 프록시·차단 대역 근거)*
- [pipelock — MCP egress firewall](https://github.com/luckyPipewrench/pipelock) *(primary; 재구현 실증)*
- [Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search) *(primary)*
- [Exa — coding agents 가이드](https://exa.ai/docs/reference/search-api-guide-for-coding-agents) · [contents retrieval](https://exa.ai/docs/reference/contents-retrieval) · [highlights for agents](https://exa.ai/blog/highlights-for-agents) *(primary/vendor)*

## 부록 B. 검증 메타데이터 및 한계

- **하니스**: deep-research(에이전트 95개, 소스 15개 페치, 주장 65개 추출 → 25개 검증, 24개 확정·1개 기각, 3표 적대적 검증).
- **시점 민감성**: `web_search_20260209`/`web_fetch_20260209`(동적 필터링)는 2026-02 출시, 구버전 `web_search_20250305`/`web_fetch_20250910`도 문서상 유효. "Bedrock 미지원" 주장은 2026-05-29 기준 — **재확인 필요**.
- **소스 품질**: 강한 주장은 Anthropic 1차 문서 기반(권위 있으나 벤더 통제). 가격($10/1K)은 1차 문서 진술이나 2차 집계로 독립 교차검증 안 됨.
- **한계**: pipelock은 단일 오픈소스 프로젝트 — 메커니즘 재구현 가능성을 증명할 뿐 보안 보증 아님. 패턴 매칭 인젝션 탐지기는 우회 가능. Exa 토큰 효율 수치는 벤더 마케팅(정성적 권고는 독립 지지됨). MCP 보안 문서는 DNS 핀/IP 검증을 SHOULD/'Consider'로 기술(MUST 아님).
- **기각된 주장(1-2)**: 사설/예약 IP 차단 대역의 **RFC 9728 §7.7 귀속** — IP 대역 자체는 표준 SSRF 가이드지만 RFC 섹션 귀속은 부정확 → OWASP SSRF Prevention 인용 권장.
