#!/usr/bin/env python3
"""cowork-token-helper — Cowork on Bedrock(3P) managedMcpServers 의 headersHelper.

Cognito M2M(client_credentials) access token 을 발급해
    {"Authorization": "Bearer <jwt>"}
한 줄만 stdout 으로 출력한다 (Cowork headersHelper 계약). 로그·에러는 stderr.

COGNITO_* 값: (1) 이미 환경변수에 있으면 사용, 없으면 (2) 스크립트 인근의 .env 에서 로드.
managedMcpServers 등록 예:
    {"name":"web-search","url":"<GATEWAY_URL>","transport":"http",
     "headersHelper":"<이 파일의 절대경로>","headersHelperTtlSec":3000,
     "toolPolicy":{"web_search":"allow"}}
TTL 은 토큰 만료(~3600s)보다 짧게(3000s 권장) — 만료 경계 401 회피.
"""
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

NEEDED = ("COGNITO_DOMAIN", "COGNITO_CLIENT_ID", "COGNITO_CLIENT_SECRET", "COGNITO_GATEWAY_SCOPE")


def _load_env_if_missing():
    if all(os.environ.get(k) for k in NEEDED):
        return
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
            return
        d = os.path.dirname(d)


def main():
    _load_env_if_missing()
    missing = [k for k in NEEDED if not os.environ.get(k)]
    if missing:
        print(f"missing env: {missing} (.env 또는 환경변수)", file=sys.stderr)
        sys.exit(1)

    region = os.environ.get("AWS_REGION", "us-east-1")
    url = f"https://{os.environ['COGNITO_DOMAIN']}.auth.{region}.amazoncognito.com/oauth2/token"
    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "scope": os.environ["COGNITO_GATEWAY_SCOPE"],
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
        print(f"token mint failed: {e}", file=sys.stderr)
        sys.exit(2)

    # 계약: stdout 에는 헤더 JSON 한 줄만
    sys.stdout.write(json.dumps({"Authorization": f"Bearer {token}"}))


if __name__ == "__main__":
    main()
