#!/usr/bin/env python3
"""install-managed-mcp.py — Cowork on Bedrock(3P) 활성 설정에 web-search MCP 추가.

Claude-3p configLibrary 의 활성 <id>.json(=_meta.json 의 appliedId)을 찾아,
GATEWAY_URL(.env)과 이 스크립트 옆 cowork-token-helper.py 절대경로로
`managedMcpServers` 엔트리를 추가/갱신한다.
- 기존 키(추론 자격증명 등) 전부 보존, managedMcpServers 만 set.
- 최초 1회 `.bak` 백업.
- 멱등(다시 돌리면 web-search 엔트리만 갱신).

실행 (Mac, repo 어디서든):  python3 clients/cowork/install-managed-mcp.py
이후 **Cowork 완전 종료 후 재시작**.

테스트용: 환경변수 CLAUDE_3P_CONFIG_DIR 로 configLibrary 경로 override 가능.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def gateway_url():
    if os.environ.get("GATEWAY_URL"):
        return os.environ["GATEWAY_URL"]
    d = HERE
    for _ in range(6):
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            for line in open(p):
                if line.strip().startswith("GATEWAY_URL="):
                    return line.split("=", 1)[1].strip()
        d = os.path.dirname(d)
    return None


def config_dir():
    override = os.environ.get("CLAUDE_3P_CONFIG_DIR")
    if override:
        return override if os.path.isdir(override) else None
    mac = os.path.expanduser("~/Library/Application Support/Claude-3p/configLibrary")
    if os.path.isdir(mac):
        return mac
    la = os.environ.get("LOCALAPPDATA")
    if la:
        win = os.path.join(la, "Claude-3p", "configLibrary")
        if os.path.isdir(win):
            return win
    return None


def main():
    cdir = config_dir()
    if not cdir:
        sys.exit("❌ Claude-3p configLibrary 없음 — 먼저 Cowork 3P 구성(Configure third-party inference → Apply locally)")

    meta_path = os.path.join(cdir, "_meta.json")
    if not os.path.isfile(meta_path):
        sys.exit(f"❌ _meta.json 없음: {meta_path}")
    active = json.load(open(meta_path)).get("appliedId")
    if not active:
        sys.exit("❌ _meta.json 에 appliedId 없음 (활성 설정 미지정)")

    cfg_path = os.path.join(cdir, active + ".json")
    if not os.path.isfile(cfg_path):
        sys.exit(f"❌ 활성 설정 파일 없음: {cfg_path}")

    gw = gateway_url()
    if not gw:
        sys.exit("❌ GATEWAY_URL 못 찾음 (.env 또는 환경변수) — server/deploy.sh 후 .env 확인")
    helper = os.path.join(HERE, "cowork-token-helper.py")
    if not os.path.isfile(helper):
        sys.exit(f"❌ helper 없음: {helper}")
    os.chmod(helper, 0o755)  # Cowork 가 직접 실행하므로 +x 보장

    cfg = json.load(open(cfg_path))
    bak = cfg_path + ".bak"
    if not os.path.exists(bak):
        shutil.copy(cfg_path, bak)  # 최초 원본만 보존

    # TTL: 평상시 3000(만료 경계 회피). 진단 시 HEADERS_HELPER_TTL=60 으로 helper 호출 강제.
    ttl = int(os.environ.get("HEADERS_HELPER_TTL", "3000"))

    cfg["managedMcpServers"] = [{
        "name": "web-search",
        "url": gw,
        "transport": "http",
        "headersHelper": helper,
        "headersHelperTtlSec": ttl,
        "toolPolicy": {"web_search": "allow"},
    }]
    json.dump(cfg, open(cfg_path, "w"), indent=2)

    print(f"✅ managedMcpServers 추가 → {cfg_path}")
    print(f"   backup     : {bak}")
    print(f"   gateway    : {gw}")
    print(f"   headersHelper: {helper}")
    print(f"   ttlSec     : {ttl}")
    print(f"   keys now   : {list(cfg.keys())}")
    print("   다음 → Cowork 완전 종료 후 재시작 → /mcp 또는 web_search 도구 확인")


if __name__ == "__main__":
    main()
