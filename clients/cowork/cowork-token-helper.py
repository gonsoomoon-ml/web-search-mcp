#!/usr/bin/env python3
"""cowork-token-helper — Cowork on Bedrock(3P) managedMcpServers 의 headersHelper.

Cognito M2M(client_credentials) access token 을 발급해
    {"Authorization": "Bearer <jwt>"}
한 줄만 stdout 으로 출력한다 (Cowork headersHelper 계약). 로그·에러는 stderr/파일.

COGNITO_* 값: (1) 이미 환경변수에 있으면 사용, 없으면 (2) 스크립트 인근의 .env 에서 로드.
managedMcpServers 등록 예:
    {"name":"web-search","url":"<GATEWAY_URL>","transport":"http",
     "headersHelper":"<이 파일의 절대경로>","headersHelperTtlSec":3000,
     "toolPolicy":{"web_search":"allow"}}
TTL 은 토큰 만료(~3600s)보다 짧게(3000s 권장) — 만료 경계 401 회피.

진단 로그(diagnostics):
    Cowork 가 단일-사용자 3P 에서 이 helper 를 실제로 호출하는지/어디서 실패하는지
    관측하기 위해 매 호출을 파일에 append 한다. 기본 경로 /tmp/web-search-mcp-token-helper.log.
    - stdout 은 헤더 JSON 한 줄만(계약) — 로그는 절대 stdout 으로 보내지 않는다.
    - 토큰·시크릿 원문은 기록하지 않는다(토큰은 길이만).
    - 끄려면:  환경변수 TOKEN_HELPER_LOG=/dev/null
    - 조사 후:  tail -f /tmp/web-search-mcp-token-helper.log  로 호출 여부 확인
"""
import base64
import datetime
import json
import os
import sys
import traceback
import urllib.parse
import urllib.request

NEEDED = ("COGNITO_DOMAIN", "COGNITO_CLIENT_ID", "COGNITO_CLIENT_SECRET", "COGNITO_GATEWAY_SCOPE")

# 진단 로그 경로. Cowork 가 helper 를 호출하는지 관측용 — 파일로만(절대 stdout 오염 금지).
LOG_PATH = os.environ.get("TOKEN_HELPER_LOG", "/tmp/web-search-mcp-token-helper.log")


def _log(msg):
    """파일에 한 줄 append. 실패해도 helper 본 기능을 죽이지 않는다(.sh 의 `|| true` 대응)."""
    try:
        ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        with open(LOG_PATH, "a") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:  # noqa: BLE001 - 로깅 실패는 무시
        pass


def _load_env_if_missing():
    """COGNITO_* 확보. 반환값 = env 출처(진단용): 'env'(이미 주입됨) | <.env 경로> | None."""
    if all(os.environ.get(k) for k in NEEDED):
        return "env"  # Cowork/부모 프로세스가 이미 주입
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(6):
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            for line in open(p):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
            return p
        d = os.path.dirname(d)
    return None


def main():
    # Cowork 의 슬림한 env 에서 호출되는지 진단: 호출 흔적 + 환경 스냅샷.
    _log(
        f"invoked pid={os.getpid()} ppid={os.getppid()} argv={sys.argv} "
        f"cwd={os.getcwd()} user={os.environ.get('USER')} "
        f"HOME={os.environ.get('HOME')} PATH={os.environ.get('PATH')}"
    )

    src = _load_env_if_missing()
    _log(f"env source: {src}")

    missing = [k for k in NEEDED if not os.environ.get(k)]
    if missing:
        _log(f"FAIL missing env: {missing}")
        print(f"missing env: {missing} (.env 또는 환경변수)", file=sys.stderr)
        sys.exit(1)

    region = os.environ.get("AWS_REGION", "us-east-1")
    url = f"https://{os.environ['COGNITO_DOMAIN']}.auth.{region}.amazoncognito.com/oauth2/token"
    scope = os.environ["COGNITO_GATEWAY_SCOPE"]
    _log(f"minting token: url={url} scope={scope} region={region}")  # 시크릿/토큰은 기록 안 함
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": scope,
    }).encode("utf-8")
    creds = base64.b64encode(
        f"{os.environ['COGNITO_CLIENT_ID']}:{os.environ['COGNITO_CLIENT_SECRET']}".encode()
    ).decode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {creds}",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            token = json.load(r)["access_token"]
    except Exception as e:  # noqa: BLE001 - helper 는 단순히 실패를 알리고 종료
        _log(f"FAIL token mint: {e!r}\n{traceback.format_exc().rstrip()}")
        print(f"token mint failed: {e}", file=sys.stderr)
        sys.exit(2)

    _log(f"OK emitting Authorization header (token len={len(token)})")
    # 계약: stdout 에는 헤더 JSON 한 줄만
    sys.stdout.write(json.dumps({"Authorization": f"Bearer {token}"}))


if __name__ == "__main__":
    main()
