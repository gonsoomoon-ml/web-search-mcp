"""smoke_test — AgentCore Gateway 경유 web_search 대화형 테스터.

흐름: Cognito M2M 토큰 → streamable-http MCP 연결 → web_search 호출 → 결과 출력.
사전: server/deploy.sh 완료 후 .env 가 채워진 상태.

실행:
  uv run python clients/smoke_test.py                 # 대화형 — 검색어를 반복 입력 (빈 줄/Ctrl-D 종료)
  uv run python clients/smoke_test.py 검색어 ...        # 한 번 실행 (인자를 검색어로)
"""
import asyncio
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

load_dotenv()

REGION = os.environ.get("AWS_REGION", "us-east-1")


def _require(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        print(f"환경변수 누락: {key} — deploy.sh 를 먼저 실행했는지 확인", file=sys.stderr)
        sys.exit(1)
    return val


def get_cognito_token() -> str:
    """Cognito token endpoint 직접 호출 (client_credentials, Basic auth)."""
    domain = _require("COGNITO_DOMAIN")
    client_id = _require("COGNITO_CLIENT_ID")
    client_secret = _require("COGNITO_CLIENT_SECRET")
    scope = _require("COGNITO_GATEWAY_SCOPE")

    url = f"https://{domain}.auth.{REGION}.amazoncognito.com/oauth2/token"
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": scope,
    }).encode("utf-8")
    creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {creds}",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)["access_token"]


def _print_results(raw: str) -> None:
    """Lambda 가 돌려준 JSON text 블록을 보기 좋게 출력."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        print(raw)
        return
    if isinstance(data, dict) and data.get("error"):
        print(f"   ⚠️ {data['error']}")
        return
    results = (data or {}).get("results", [])
    if not results:
        print("   (결과 없음)")
        return
    for i, r in enumerate(results, 1):
        snippet = (r.get("snippet") or "").strip().replace("\n", " ")
        print(f"   {i}. {r.get('title')}  [score={r.get('score')}]")
        print(f"      {r.get('url')}")
        print(f"      {snippet[:160]}")


async def run_query(query: str) -> None:
    """검색어 1건: 토큰 발급 → 게이트웨이 연결 → web_search 호출 → 출력.

    쿼리마다 새 연결/토큰 — 대화형에서 idle 타임아웃을 피하고 흐름이 단순.
    """
    gateway_url = _require("GATEWAY_URL")
    token = get_cognito_token()
    async with streamablehttp_client(
        url=gateway_url,
        headers={"Authorization": f"Bearer {token}"},
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            target = next((t.name for t in tools if t.name.endswith("web_search")), None)
            if not target:
                print("❌ web_search 도구를 찾을 수 없음", file=sys.stderr)
                sys.exit(2)
            result = await session.call_tool(target, {"query": query, "max_results": 5})
            for block in result.content:
                _print_results(getattr(block, "text", None) or str(block))


def main() -> None:
    # 인자가 있으면 한 번 실행
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(f"🔍 {query}")
        asyncio.run(run_query(query))
        return

    # 대화형 루프
    print("Gateway web_search 대화형 테스터 — 검색어를 입력하세요 (빈 줄 또는 Ctrl-D 종료).")
    while True:
        try:
            query = input("\n🔍 검색어> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not query:
            break
        asyncio.run(run_query(query))
    print("종료.")


if __name__ == "__main__":
    main()
