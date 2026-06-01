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
    관측하기 위해 매 호출을 파일에 append 한다.
    기본 경로 ~/.cache/web-search-mcp/token-helper.log (사용자 소유 디렉터리, 0700).
    - 보안: 로그는 0600(소유자만 read) + O_NOFOLLOW(심링크 추종 거부)로 연다.
      → 공유 /tmp 심링크 스쿼팅·world-readable 노출 회피.
    - stdout 은 헤더 JSON 한 줄만(계약) — 로그는 절대 stdout 으로 보내지 않는다.
    - 토큰·시크릿 원문은 기록하지 않는다(토큰은 길이만, client_secret/Basic 헤더 미기록).
    - PATH/argv/cwd/HOME/env 출처는 진단 목적상 기록한다(슬림 env·샌드박스·.env 탐색 실패 판별).
      민감하면 조사 후 파일 삭제. 끄려면 TOKEN_HELPER_LOG=/dev/null.
    - 조사 후:  tail -f ~/.cache/web-search-mcp/token-helper.log
"""
import base64
import datetime
import json
import os
import sys
import time
import traceback
import urllib.parse
import urllib.request

NEEDED = ("COGNITO_DOMAIN", "COGNITO_CLIENT_ID", "COGNITO_CLIENT_SECRET", "COGNITO_GATEWAY_SCOPE")

# 진단 로그 경로. Cowork 가 helper 를 호출하는지 관측용 — 파일로만(절대 stdout 오염 금지).
# 기본은 사용자 소유 ~/.cache 하위(공유 /tmp 회피). TOKEN_HELPER_LOG 로 override/비활성.
LOG_PATH = os.environ.get("TOKEN_HELPER_LOG") or os.path.join(
    os.path.expanduser("~"), ".cache", "web-search-mcp", "token-helper.log"
)

# 토큰 캐시: 매 호출 mint(네트워크 ~1-2s)를 피해 캐시 적중 시 즉시 출력 — Cowork 의
# headersHelper 타임아웃이 짧을 경우 대비(레퍼런스 token-helper.sh 의 tokens.json 패턴).
CACHE_PATH = os.path.join(os.path.expanduser("~"), ".cache", "web-search-mcp", "token-cache.json")
CACHE_SKEW = 300  # 만료 5분 전부터는 새로 발급(경계 401 회피)


def _log(msg):
    """파일에 한 줄 append. 보안: 사용자 소유 디렉터리(0700)에 0600·O_NOFOLLOW 로 연다
    (심링크 추종 거부 → /tmp 스쿼팅 회피). 실패해도 helper 본 기능을 죽이지 않는다."""
    try:
        d = os.path.dirname(LOG_PATH)
        if d:
            os.makedirs(d, mode=0o700, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(LOG_PATH, flags, 0o600)
        try:
            os.write(fd, f"[{ts}] {msg}\n".encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001 - 로깅 실패(심링크 거부 포함)는 무시
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


def _read_cached_token():
    """유효한 캐시 토큰 반환. 없거나 만료 임박(CACHE_SKEW 이내)이면 (None, None)."""
    try:
        with open(CACHE_PATH) as f:
            c = json.load(f)
        left = c.get("expires_at", 0) - time.time()
        if c.get("access_token") and left > CACHE_SKEW:
            return c["access_token"], int(left)
    except Exception:  # noqa: BLE001 - 캐시 없음/손상은 그냥 mint 로 폴백
        pass
    return None, None


def _write_cached_token(token, expires_in):
    """캐시 저장(사용자 소유 0700 디렉터리에 0600·O_NOFOLLOW). 실패해도 무시."""
    try:
        d = os.path.dirname(CACHE_PATH)
        if d:
            os.makedirs(d, mode=0o700, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(CACHE_PATH, flags, 0o600)
        try:
            os.write(fd, json.dumps({
                "access_token": token,
                "expires_at": time.time() + int(expires_in),
            }).encode("utf-8"))
        finally:
            os.close(fd)
    except Exception:  # noqa: BLE001
        pass


def _mint_token():
    """Cognito M2M client_credentials → access_token, expires_in 반환."""
    region = os.environ.get("AWS_REGION", "us-east-1")
    url = f"https://{os.environ['COGNITO_DOMAIN']}.auth.{region}.amazoncognito.com/oauth2/token"
    scope = os.environ["COGNITO_GATEWAY_SCOPE"]
    _log(f"cache miss → minting: url={url} scope={scope} region={region}")  # 시크릿/토큰 미기록
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
    with urllib.request.urlopen(req, timeout=8) as r:
        resp = json.load(r)
    return resp["access_token"], int(resp.get("expires_in", 3600))


def main():
    t0 = time.time()
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

    # 캐시 우선 — 적중 시 네트워크 없이 즉시(타임아웃 가설 차단).
    token, ttl_left = _read_cached_token()
    if token:
        _log(f"cache hit (ttl_left={ttl_left}s, {int((time.time() - t0) * 1000)}ms)")
    else:
        try:
            token, expires_in = _mint_token()
        except Exception as e:  # noqa: BLE001 - helper 는 단순히 실패를 알리고 종료
            _log(f"FAIL token mint: {e!r}\n{traceback.format_exc().rstrip()}")
            print(f"token mint failed: {e}", file=sys.stderr)
            sys.exit(2)
        _write_cached_token(token, expires_in)
        _log(f"minted (len={len(token)}, {int((time.time() - t0) * 1000)}ms)")

    # 계약: stdout 에 헤더 JSON 한 줄 + trailing newline. flush 로 즉시 파이프에 씀 →
    # Cowork 가 reader 를 일찍 닫았으면 BrokenPipeError 로 잡혀 timeout 을 직접 진단.
    payload = json.dumps({"Authorization": f"Bearer {token}"}) + "\n"
    try:
        sys.stdout.write(payload)
        sys.stdout.flush()
        _log(f"OK wrote header (newline-terminated, total {int((time.time() - t0) * 1000)}ms)")
    except BrokenPipeError:
        _log(f"BROKEN PIPE — Cowork 가 reader 를 일찍 닫음(타임아웃 의심), "
             f"total {int((time.time() - t0) * 1000)}ms")
        try:
            sys.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        sys.exit(3)


if __name__ == "__main__":
    main()
