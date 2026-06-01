#!/usr/bin/env python3
"""install-mobileconfig.py — Cowork on Bedrock(3P) 의 managedMcpServers+headersHelper 를
**관리형 preferences 레이어**(macOS configuration profile)로 주입한다.

배경(실측 2026-06-01): configLibrary 에 넣은 headersHelper 는 Cowork 가 *호출은 하지만*
요청 헤더에 적용하지 않는다("Missing Bearer token"). 반면 정적 Headers 는 configLibrary
에서도 적용됨 → headersHelper 는 **관리형 prefs 레이어**에서 와야 honor 되는 것으로 보임.
레퍼런스: hi-space/websearch-agentcore-gateway cowork/templates/cowork-3p.mobileconfig.tmpl
(managedMcpServers 를 com.anthropic.claudefordesktop 관리형 prefs 에 넣음).

이 스크립트는:
  1) 활성 configLibrary <id>.json 에서 사용자의 inference 설정을 읽어 그대로 보존하고,
     (관리형 prefs 가 도메인 authoritative 여도 inference 가 안 깨지게)
  2) 우리 게이트웨이용 managedMcpServers(headersHelper=옆 cowork-token-helper.py 절대경로)를 더해
  3) com.anthropic.claudefordesktop configuration profile(.mobileconfig)을 plistlib 로 렌더링,
  4) configLibrary 의 managedMcpServers 는 제거(프로파일이 단일 소스가 되도록, inference 는 유지).

설치는 사용자가 직접: open <생성된 .mobileconfig> → System Settings 에서 승인 → Cowork 재시작.
제거(원복): System Settings → Privacy & Security → Profiles 에서 삭제.

실행 (Mac, repo 어디서든):  python3 clients/cowork/install-mobileconfig.py
override(테스트): CLAUDE_3P_CONFIG_DIR, GATEWAY_URL, HEADERS_HELPER_TTL, MOBILECONFIG_OUT
"""
import json
import os
import plistlib
import shutil
import sys
import uuid

HERE = os.path.dirname(os.path.abspath(__file__))

# configLibrary 에서 프로파일로 복사해 보존할 키(사용자의 기존 추론 설정).
INFERENCE_KEYS = (
    "inferenceProvider", "inferenceCredentialKind", "inferenceBedrockRegion",
    "inferenceBedrockProfile", "inferenceModels",
)


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
    return mac if os.path.isdir(mac) else None


def active_config_path(cdir):
    meta_path = os.path.join(cdir, "_meta.json")
    if not os.path.isfile(meta_path):
        sys.exit(f"❌ _meta.json 없음: {meta_path}")
    active = json.load(open(meta_path)).get("appliedId")
    if not active:
        sys.exit("❌ _meta.json 에 appliedId 없음")
    p = os.path.join(cdir, active + ".json")
    if not os.path.isfile(p):
        sys.exit(f"❌ 활성 설정 파일 없음: {p}")
    return p


def stable_uuid(name):
    """재실행 시 동일 UUID → 프로파일 중복 대신 갱신."""
    ns = uuid.uuid5(uuid.NAMESPACE_DNS, "web-search-mcp.cowork")
    return str(uuid.uuid5(ns, name)).upper()


def main():
    gw = gateway_url()
    if not gw:
        sys.exit("❌ GATEWAY_URL 못 찾음 (.env 또는 환경변수) — server/deploy.sh 후 .env 확인")

    helper = os.path.join(HERE, "cowork-token-helper.py")
    if not os.path.isfile(helper):
        sys.exit(f"❌ helper 없음: {helper}")
    os.chmod(helper, 0o755)  # Cowork 가 직접 실행하므로 +x 보장

    ttl = int(os.environ.get("HEADERS_HELPER_TTL", "900"))

    # --- configLibrary 에서 inference 보존값 읽기 ---
    cdir = config_dir()
    cfg_path = None
    inference = {}
    if cdir:
        cfg_path = active_config_path(cdir)
        inference = {k: v for k, v in json.load(open(cfg_path)).items() if k in INFERENCE_KEYS}

    # --- 프로파일 렌더링 (plistlib) ---
    inner = {
        "PayloadType": "com.anthropic.claudefordesktop",
        "PayloadUUID": stable_uuid("payload"),
        "PayloadIdentifier": "com.anthropic.claudefordesktop.websearchmcp",
        "PayloadDisplayName": "Claude Cowork — web-search MCP",
        "PayloadVersion": 1,
    }
    inner.update(inference)  # 사용자의 기존 inference 그대로 보존
    inner["managedMcpServers"] = [{
        "url": gw,
        "transport": "http",
        "name": "web-search",
        "headersHelper": helper,
        "headersHelperTtlSec": ttl,
    }]

    profile = {
        "PayloadContent": [inner],
        "PayloadDisplayName": "Claude Cowork with web-search MCP (Bedrock)",
        "PayloadIdentifier": "com.web-search-mcp.cowork",
        "PayloadType": "Configuration",
        "PayloadUUID": stable_uuid("profile"),
        "PayloadVersion": 1,
        "PayloadScope": "User",
    }

    out = os.environ.get("MOBILECONFIG_OUT") or os.path.join(
        os.path.expanduser("~"), ".cache", "web-search-mcp", "web-search-mcp.mobileconfig"
    )
    os.makedirs(os.path.dirname(out), mode=0o700, exist_ok=True)
    with open(out, "wb") as f:
        plistlib.dump(profile, f)
    os.chmod(out, 0o600)

    # --- configLibrary 의 managedMcpServers 제거(프로파일이 단일 소스, inference 는 유지) ---
    removed = False
    if cfg_path:
        cfg = json.load(open(cfg_path))
        if "managedMcpServers" in cfg:
            bak = cfg_path + ".bak"
            if not os.path.exists(bak):
                shutil.copy(cfg_path, bak)  # 최초 원본(정적 헤더 동작본) 보존
            del cfg["managedMcpServers"]
            json.dump(cfg, open(cfg_path, "w"), indent=2)
            removed = True

    print(f"✅ mobileconfig 생성 → {out}")
    print(f"   gateway       : {gw}")
    print(f"   headersHelper : {helper}")
    print(f"   ttlSec        : {ttl}")
    print(f"   inference 보존 : {list(inference) or '(configLibrary 없음 — inference 미포함, 주의)'}")
    print(f"   configLibrary managedMcpServers 제거 : {removed}")
    print()
    print("다음 (사용자 수동):")
    print(f"   1) 설치 :  open \"{out}\"   → System Settings 에서 프로파일 승인")
    print("   2) 확인 :  System Settings → Privacy & Security → Profiles 에 'Claude Cowork ...' 표시")
    print("   3) 재시작:  Cowork Cmd+Q 후 재실행 → web_search 트리거")
    print("   4) 검증 :  tail -3 ~/.cache/web-search-mcp/token-helper.log  (cache hit / OK wrote header)")
    print()
    print("제거(원복) : System Settings → Profiles 에서 프로파일 삭제.")
    if cfg_path:
        print(f"            정적 헤더로 복귀하려면  cp '{cfg_path}.bak' '{cfg_path}'  후 Cowork 재시작")


if __name__ == "__main__":
    main()
