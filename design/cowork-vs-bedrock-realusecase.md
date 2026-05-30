# 실사용 심층 비교: Claude Cowork 내장 web search vs Claude Code on Bedrock + 우리 MCP 게이트웨이

> 작성일: 2026-05-30
> 관련: [`prd.md`](./prd.md) · [`research-comparison.md`](./research-comparison.md) · [`cowork-feature-mapping.md`](./cowork-feature-mapping.md) · [`web-search-gateway-simpletest.md`](./web-search-gateway-simpletest.md)
> 방법: 6축 병렬 심층 분석 → 종합 → 적대적 비평(과대주장·모순·누락 색출). 본 문서는 **비평을 반영해 정정한 버전**이다.

---

## 0. 앵커 시나리오

추상 비교표가 아니라 하나의 구체적 과제로 고정한다:

> "AWS 데이터 거버넌스(데이터가 AWS 경계 밖으로 못 나감)를 따르는 **한국 핀테크** 개발자가 Claude에게 — *'경쟁사 Toss의 최근 6개월 결제·규제 대응 동향을 조사해, 출처 URL 달린 한국어 요약 보고서로'* — 요청. 이 과제는 ① 다중 검색·반복 탐색 ② 일부 페이지 본문 정독 ③ 출처 인용 ④ 한국어 합성 을 모두 요구한다."

두 경로로 추적한다: **경로A** = Cowork 내장 web search(관리형·server-side) · **경로B** = Claude Code on Bedrock + 우리 MCP 게이트웨이.

---

## 1. 한 줄 결론

**격차는 "누가 답을 쓰나"가 아니다 — 양쪽 다 Claude(동급 모델)가 쓰고 한국어 유창성도 동급이다. 진짜 격차는 *검색 도구가 모델 손에 쥐여주는 데이터의 풍부함*에서 발생한다.** 따라서 통제 가능한 핵심 레버는 **`fetch_url`(본문 정독) + 구조화 인용**이며, 답변 합성·한국어 같은 곳이 아니다. 그리고 6축 중 유일하게 맥락에 의존하지 않는 우위는 **데이터 거버넌스**다 — 단, 현재 simple-test는 그 우위를 아직 *실현*하지 못했다(아래 §5).

---

## 2. 결정적 차이가 발생하는 레이어

흔한 오해와 달리 차이는 "답을 누가 쓰나"가 아니라 **세 하위 레이어**에서만 갈린다:

- **(A) 루프 레이어 — 깊이가 어디서 도는가.** 경로A는 추론 제공자 내부의 server-side 검색 반복 + 그 위 Cowork outer 루프 = 2단. 경로B는 Claude Code outer 루프 한 겹(우리 도구는 stateless 1샷 — "agentic 멀티스텝은 CC가 처리"라는 의도된 설계). "단일 요청 내 무한 연장"은 *재현 대상이 아니라 설계 차이*다.
- **(B) 그라운딩 레이어 — 합성기가 무엇을 쥐고 쓰나.** 경로A: 본문 fetch + 모델이 직접 본문 reasoning. 경로B: **Tavily basic 스니펫(패러프레이즈)만, `fetch_url` 미구현으로 본문 미독**. ← 진짜 격차.
- **(C) 인용 레이어 — "이 문장 = 이 URL의 이 구절"을 누가 보증하나.** 경로A: 모델이 본문에서 고른 verbatim 구절을 typed 필드로 운반(프로토콜 보장). 경로B: 모델이 스니펫·URL로 **free-text 인용 자가조립** → 구조·verbatim 보증 없음 → fabricated-quote 위험.

> **요지**: 도구(게이트웨이)는 양쪽 다 답을 쓰지 않는다. 네이티브 web_search 도구가 우월한 건 "답을 써서"가 아니라 **본문을 fetch해 verbatim 인용을 typed로 운반**하기 때문이다. → **fetch_url + 구조화 인용을 도구 레이어에 넣으면 동급 합성기가 동급에 근접**한다는 설계 함의(※ 검증된 사실 아님, 미구현 추론).

---

## 3. 축별 비교 (verdict)

| 축 | Cowork (경로A) | Bedrock+MCP (경로B, 현재 코드) | Verdict |
|---|---|---|---|
| 멀티스텝 리서치 깊이 | server-side 루프 + outer 루프 2단 | outer 루프 한 겹, basic 스니펫 1샷, fetch_url 미구현 | 맥락의존 |
| 답변·인용·한국어 | 본문 reasoning + verbatim typed 인용 | 한국어 유창성 동급, 본문 미독·인용 자가조립 | 맥락의존 |
| 지연·UX·셋업 | 호스팅 경로면 0-셋업·1-hop | 선배포 ~3–5분 + 4-hop 직렬 | 맥락의존 |
| 비용 (과제 1건) | 검색 $10/1k + 토큰 | Tavily 무료티어 + 인프라 <$0.02 + 토큰 | 맥락의존 (토큰이 ~95%, 양쪽 유사) |
| **거버넌스·데이터 경계** | 쿼리·결과가 Anthropic 인프라 통과 | 데이터 AWS 경계 내 (단 §5 한계) | **bedrock-mcp-우위** |
| 운영·신뢰성·이식성 | Anthropic이 흡수(블랙박스) | 우리가 전부 책임, 표준 MCP라 이식성↑ | 맥락의존 |

> "맥락의존"의 context는 일관되게 **"AWS 데이터 경계를 강제하는가"**다. 이 제약이 없으면 대부분 축이 Cowork 쪽으로 기운다.

---

## 4. 통제 가능한 격차 우선순위

| 우선순위 | 격차 | 무엇을 | 근거 |
|---|---|---|---|
| **P0** | **fetch_url 구현** | 본문 추출(Readability→md, N토큰 절단)을 handler.py `TOOLS`에 추가 | research-comparison §5.0, mapping #10 |
| **P0** | **verbatim 인용 보존** | fetch 본문의 문자 오프셋 반환 → cited_text 수준 인용 | mapping #5, cowork §5.2 |
| **P0 (동반 필수)** | **SSRF/egress 방어 + 키 보안** | fetch는 공격면을 "Tavily 1곳→임의 URL"로 넓힘 → Smokescreen류 프록시·DNS 핀·도메인 allowlist + `TAVILY_API_KEY` Secrets Manager 이전·Lambda VPC egress 통제 | mapping #9·#14·#15 |
| P1 | 검색 깊이·신선도 | `search_depth: advanced`, published_date 패스스루 | tavily docs |
| P1 | 폴백·재시도 | 지수백오프 + 폴백 제공자(432 시 Brave/Serper) | design §5.7 |
| P1 | 토큰 캐시 | M2M 토큰 ~1h 재사용(hop0 제거) | — |
| P2 | 비용 가드레일·관측성·인젝션 표식 | 예산캡·TTL 캐시·구조화 로깅·`<untrusted_web_content>` | design §5.5·5.8, mapping #13 |

> 순서 논리: P0(fetch_url + 인용)이 앵커의 핵심 공백(본문 정독·verbatim 인용)을 닫는 단일 최대 레버. 넣는 즉시 SSRF 방어가 동시 필수가 된다.

---

## 5. 정직한 정정·한계 (적대적 비평 반영)

종합 보고서가 설득력을 위해 과장했던 부분을 바로잡는다 — 이 문서의 주장은 아래 한계 안에서만 유효하다.

1. **"Cowork은 Bedrock에서 아예 못 쓴다"는 과장.** Cowork/Claude Code는 Bedrock에서 *구동 가능*하고 **server-side `web_search`만 공백**이다(research-comparison §2.1).
2. **"Cowork 검색 비용 통제 불가"는 사실 아님.** 네이티브 `web_search`는 `max_uses`로 요청당 검색 횟수를 하드캡한다(mapping #2).
3. **누락된 진짜 대안 — Claude Platform on AWS.** AWS 계정 경계로 네이티브 web search/fetch를 *직접 구축 없이* 제공(research-comparison §1.2). "Cowork vs 우리 MCP" 이분법은 이 build-vs-buy 분기를 회피했다 — **선결 평가 필요**.
4. **누락 — 권한 비대칭.** 핀테크 거버넌스에선 Cowork(데스크톱/claude.ai 계정)를 **켤 권한 자체가 막힐** 수 있다(기능 비교 이전 문제).
5. **누락 — 한국어 검색 품질.** 앵커가 한국 핀테크인데 **Tavily가 한국 금융 도메인에서 Brave(Cowork 백엔드) 동급인지 미검증**. 결정적 변수.
6. **우리 구현 보안 과대포장.** "데이터 경계 구조적 우위"는 *방향*이지 현재 수준이 아니다: `TAVILY_API_KEY`가 **Secrets Manager 아닌 Lambda 평문 env**, Lambda는 **비-VPC 기본 인터넷 egress**.
7. **Cowork 유출 PoC·내부 프로토콜은 확정 아님.** egress 우회/PromptArmor PoC는 *secondary/PoC* 근거, "Brave 백엔드·pause_turn·encrypted_index"는 *벤더 통제 1차문서*(교차검증 안 됨).
8. **비평도 틀린 한 건.** "882자 JWT는 코드에 없는 날조"라는 지적은 오판 — 882는 **우리 실제 smoke_test 실행 로그**(`token 획득 (len=882)`)의 실측치다. 단 이는 *대화형 테스터* 값이고 실제 Claude Code 런타임 토큰 수명은 미측정(이 점은 비평이 맞음).
9. **"fetch_url 넣으면 Cowork에 근접"은 설계 추론**(동급 합성기 가정, 미구현) — 검증된 사실 아님.
10. **시점 민감성.** "Bedrock 미지원"은 2026-05-29~30 기준 — 재확인 필요(cowork-feature-mapping 부록B).

---

## 6. 그럼에도 Bedrock+MCP인 이유 (거버넌스)

깊이·인용·UX 격차는 P0~P1으로 *좁힐 수 있는* 엔지니어링 부채다. 반면 **데이터가 AWS 밖으로 못 나가는** 핀테크 제약은 Cowork server-side search에선 구조적으로 해소 불가다(Bedrock 미지원). 데이터 경계·IAM 최소권한·통제권·이식성(표준 MCP)이 경로B의 비-맥락의존 우위다. **단 그 우위는 §5-6의 보안 부채(평문 키·비-VPC)를 갚아야 *실현*된다.**

> **결론**: 따라잡을 수 있는 것(깊이·인용)을 P0로 따라잡고, 따라잡을 수 없는 것(거버넌스)을 이미 쥐고 있되 *실제로 단단히 쥐도록* 보안 부채를 갚는다 — 그리고 **Claude Platform on AWS를 build-vs-buy 선결로 평가**한다.

---

## 부록. 신뢰도·근거
- 6축 분석은 우리 design 문서(검증됨)·실배포 코드·실행 로그에 그라운딩, 일부 Cowork 사실은 웹 검증. Anthropic 내부 프로토콜 디테일은 *벤더 통제 1차문서*로 신뢰도 한정.
- 비용·지연 수치는 앵커 워크로드 *가정치* — 실제 에이전트 자율검색 횟수에 따라 변동, 정량 latency 미측정.
- verdict "bedrock-mcp-우위"(거버넌스)만 비-맥락의존; 나머지 5축은 "AWS 경계 강제 여부"에 의존.
