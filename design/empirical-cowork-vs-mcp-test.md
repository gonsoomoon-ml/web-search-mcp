# 경험적 비교 테스트: Claude Cowork(내장) vs Claude Code on Bedrock + 우리 MCP

> 작성일: 2026-05-30 · 관련: [`cowork-vs-bedrock-realusecase.md`](./cowork-vs-bedrock-realusecase.md)
> 목적: 분석 문서의 결론(격차는 *도구가 운반하는 데이터의 풍부함*, P0=fetch_url+인용)을
> **같은 과제를 양쪽에 실제로 돌려** 경험적으로 검증/반증.

---

## ⚠️ 해석 전제 (먼저 읽을 것)

이 테스트를 잘못 읽으면 틀린 결론에 도달합니다. 세 가지를 항상 기억:

1. **Cowork ≠ Bedrock.** Cowork는 Anthropic 인프라에서 돌고 **native web search를 이미 가짐**. 즉 비교는 "**관리형 native(Cowork)** vs **Bedrock + 자체 게이트웨이(우리)**"다. Cowork는 애초에 Bedrock 공백의 대상이 아니다 — 그래서 검색이 *된다*.
2. **이 테스트는 데이터 경계(거버넌스)를 보여주지 못한다.** 둘 다 결과를 출력하지만, 우리 쪽은 데이터가 **AWS 경계 내**, Cowork는 **Anthropic 인프라 통과**다. 출력만 보고 "Cowork이 낫다"를 결론내면 안 됨 — 우리 접근의 *진짜 이유*(거버넌스)는 화면에 안 보인다.
3. **현재 비대칭은 의도된 것.** 우리는 `web_search`-only(아직 `fetch_url` 미구현)라, Cowork가 **본문 정독·verbatim 인용**에서 앞설 것으로 *예상*된다. 즉 이 테스트는 사실상 **P0 격차(fetch_url + 구조화 인용)를 경험적으로 측정**하는 것이다 — Cowork 우위가 그 두 축에 집중되면 우리 우선순위가 옳다는 증거.

---

## 실행 (공정성: 동일 프롬프트 · 같은 시각)

### A) Claude Code on Bedrock + 우리 게이트웨이
```
./clients/claude-code/local_test.sh
```
(격리 세션 — web-search만, `CLAUDE_CODE_USE_BEDROCK=1` 자동. 모델: `global.anthropic.claude-sonnet-4-6`)

### B) Claude Cowork
Claude Desktop 앱 → **Cowork**에서 **같은 프롬프트**. 내장 web search라 셋업 0.
(모델 메모: Cowork가 쓰는 모델을 기록 — 가급적 비슷한 티어로 비교)

### 추천 프롬프트 2종
- **빠른 점검(sanity):**
  `"Amazon Bedrock AgentCore" 최신 뉴스를 검색해 출처 URL과 함께 한국어로 3문장 요약.`
- **깊이 측정(격차가 드러남):**
  `토스(Toss)의 최근 6개월 결제·규제 대응 동향을 여러 출처로 조사하고, 핵심 주장마다 원문 인용과 URL을 달아 한국어 보고서로 만들어줘.`

---

## 비교 루브릭 (실행 후 채우기)

| 항목 | Cowork (A) | 우리 Bedrock+MCP (B) | 메모 |
|---|---|---|---|
| 검색 반복(멀티스텝) 깊이 | | | 몇 번 검색? 각도 전환? |
| 페이지 **본문 정독** 여부 | | | 스니펫만? 전문 읽음? |
| **인용 충실도** | | | 원문 구절(verbatim) vs URL만 |
| 신선도(최신 날짜) | | | 결과의 최신성 |
| 한국어 품질 | | | 유창성·정확성 |
| 지연 / 체감 UX | | | 응답 속도·매끄러움 |
| 셋업 부담 | 0 (켜면 됨) | 배포+토큰 | |
| (출력에 안 보임) **데이터 경계** | Anthropic 통과 | AWS 경계 내 | 테스트로 측정 불가 |

---

## 해석 가이드
- **Cowork 우위가 "본문 정독·인용"에 집중** → realusecase의 P0(fetch_url+인용)이 핵심 레버라는 경험적 확증. 다음 구현 정당화.
- **한국어·신선도가 비등** → 격차가 "작문(에이전트)"이 아니라 "도구가 주는 데이터"임을 재확인(분석 §2와 일치).
- **데이터 경계·거버넌스**는 이 테스트로 판단 불가 → 별도 요건으로 분리 평가(핀테크/규제 시 우리 우위).
- 결론은 "어느 제품이 낫다"가 아니라 **"우리가 무엇을 더 만들면 Cowork UX에 근접하나"**로 읽을 것.

> 참고: Cowork에 *우리 게이트웨이를 MCP로 추가*하는 것도 가능하나(Claude Desktop의 MCP/커넥터), 이 비교의 목적은 Cowork의 **내장** 검색과 우리 것을 견주는 것이므로 권장하지 않음.
