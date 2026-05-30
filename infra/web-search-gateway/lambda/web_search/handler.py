"""web-search Lambda — Tavily-backed MCP 도구 (AgentCore Gateway target).

게이트웨이 호출 계약 (워크숍 infra/cognito-gateway/lambda/*/handler.py 와 동형):
- tool 식별자: ``context.client_context.custom["bedrockAgentCoreToolName"]``
  (event 가 아닌 Lambda invoke metadata, 형식 ``<target>___<tool>``)
- input: ``event`` 자체가 inputSchema.properties 의 값 dict (wrapper 없음)

도구 확장 방법 (2 스텝):
  1. 새 함수 ``def my_tool(params) -> dict`` 추가
  2. 아래 ``TOOLS`` 에 ``"my_tool": my_tool`` 등록
  + setup_gateway.py 의 tool schema 에도 같은 이름으로 inputSchema 추가.
한 Lambda 가 여러 도구를 호스팅 — 도구 이름으로 디스패치.
"""
import json
import os
import urllib.error
import urllib.request

TAVILY_API_KEY = os.environ["TAVILY_API_KEY"]
TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _tavily_post(url: str, payload: dict) -> dict:
    """Tavily API POST — Bearer 인증 (공식 tavily-mcp 서버와 동일)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TAVILY_API_KEY}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return json.load(resp)


# ── 도구 구현 ────────────────────────────────────────────────
def web_search(params: dict) -> dict:
    """웹 검색 → {query, results:[{title,url,snippet,score}]}."""
    query = params.get("query")
    if not query:
        return {"error": "query is required"}

    # max_results: 기본 5, Tavily 상한 20 으로 clamp (비용·토큰 가드레일)
    try:
        max_results = int(params.get("max_results", 5))
    except (TypeError, ValueError):
        max_results = 5
    max_results = max(1, min(max_results, 20))

    data = _tavily_post(TAVILY_SEARCH_URL, {
        "query": query,
        "max_results": max_results,
        "search_depth": "basic",
    })
    results = [
        {
            "title": r.get("title"),
            "url": r.get("url"),
            "snippet": r.get("content"),
            "score": r.get("score"),
        }
        for r in data.get("results", [])
    ]
    return {"query": query, "results": results}


# ── 도구 레지스트리 — 확장 지점 ──────────────────────────────
TOOLS = {
    "web_search": web_search,
    # "fetch_url": fetch_url,   # 예: 다음 단계에서 추가
}


def _tool_name(context) -> str:
    cc = getattr(context, "client_context", None)
    custom = getattr(cc, "custom", None) if cc else None
    return (custom or {}).get("bedrockAgentCoreToolName", "")


def lambda_handler(event, context):
    # "<target>___<tool>" 의 마지막 세그먼트가 도구 이름
    tool_id = _tool_name(context)
    name = tool_id.split("___")[-1]
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {tool_id!r}"}

    try:
        return fn(event or {})
    except urllib.error.HTTPError as e:
        return {"error": f"tavily HTTPError {e.code}", "detail": e.read().decode("utf-8", "replace")[:500]}
    except urllib.error.URLError as e:
        return {"error": f"tavily URLError: {e.reason}"}
