"""AgentCore Gateway 생성 + web-search Target 등록 (boto3, idempotent).

표준 AWS 자원 (Cognito, Lambda, IAM Role) 은 cognito.yaml CFN 이 담당.
이 스크립트는 AgentCore 자원 (Gateway + Target) 만.
Reference: gonsoomoon-ml/aiops-multi-agent-workshop infra/cognito-gateway/setup_gateway.py

deploy.sh 가 CFN outputs 를 환경변수로 export 한 뒤 호출:
    GATEWAY_IAM_ROLE_ARN
    COGNITO_USER_POOL_ID
    COGNITO_CLIENT_ID
    COGNITO_GATEWAY_SCOPE
    LAMBDA_WEB_SEARCH_ARN

CUSTOM_JWT authorizer 3중 검증:
    들어오는 JWT → ① 서명(discoveryUrl) ② audience(allowedClients) ③ scope(allowedScopes)

출력: GATEWAY_ID + GATEWAY_URL (deploy.sh 가 stdout 에서 캡처해 .env 기록).
"""
import os
import sys
import time

import boto3

REGION = os.environ.get("AWS_REGION", "us-east-1")
DEMO_USER = os.environ.get("DEMO_USER", "")  # main() 의 required 검증에서 빈 값 거부

GATEWAY_NAME = f"web-search-{DEMO_USER}-gateway"
TARGET_WEB_SEARCH = "web-search"

WEB_SEARCH_TOOL_SCHEMA = [
    {
        "name": "web_search",
        "description": (
            "웹을 검색해 관련 결과(제목·URL·스니펫)를 반환한다. "
            "최신 정보·뉴스·문서 조회에 사용. 본문 전문이 아니라 스니펫만 반환."
        ),
        "inputSchema": {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "description": "검색어"},
                "max_results": {
                    "type": "integer",
                    "description": "최대 결과 수 (기본 5, 최대 20)",
                },
            },
        },
    },
]


def _client():
    return boto3.client("bedrock-agentcore-control", region_name=REGION)


def wait_for_gateway_ready(gw, gateway_id: str, max_wait: int = 90, poll: int = 3) -> None:
    """Gateway 가 READY 상태 될 때까지 대기 (Target 추가 전 필수).

    create_gateway 직후엔 CREATING — Target 추가 시 ValidationException. 이미 READY 면 즉시 반환.
    """
    print(f"  ⏳ Gateway READY 대기 (max {max_wait}s)")
    deadline = time.monotonic() + max_wait
    status = "UNKNOWN"
    while time.monotonic() < deadline:
        detail = gw.get_gateway(gatewayIdentifier=gateway_id)
        status = detail.get("status", "UNKNOWN")
        if status == "READY":
            print("  ✅ Gateway READY")
            return
        if status in ("FAILED", "DELETING", "DELETED"):
            raise RuntimeError(f"Gateway 비정상 상태: {status}")
        time.sleep(poll)
    raise RuntimeError(f"Gateway READY 타임아웃 ({max_wait}s, 현재={status})")


def create_gateway(gw, role_arn, pool_id, client_id, scope):
    print("\n=== Step 1: AgentCore Gateway 생성 ===")
    existing = next(
        (g for g in gw.list_gateways().get("items", []) if g.get("name") == GATEWAY_NAME),
        None,
    )
    if existing:
        print(f"  이미 존재: gatewayId={existing['gatewayId']} (재사용)")
        return gw.get_gateway(gatewayIdentifier=existing["gatewayId"])

    discovery_url = (
        f"https://cognito-idp.{REGION}.amazonaws.com/{pool_id}/.well-known/openid-configuration"
    )
    resp = gw.create_gateway(
        name=GATEWAY_NAME,
        roleArn=role_arn,
        protocolType="MCP",
        authorizerType="CUSTOM_JWT",
        authorizerConfiguration={
            "customJWTAuthorizer": {
                "discoveryUrl": discovery_url,
                "allowedClients": [client_id],
                "allowedScopes": [scope],
            }
        },
    )
    print(f"  ✅ gatewayId={resp['gatewayId']}")
    print(f"  ✅ gatewayUrl={resp['gatewayUrl']}")
    return resp


def create_or_update_target(gw, gateway_id, name, lambda_arn, tool_schema):
    """Target 이 없으면 create, 있으면 update — lambdaArn + schema 강제 동기화."""
    print(f"\n=== Step 2: GatewayTarget '{name}' 추가/갱신 ===")

    target_config = {
        "mcp": {
            "lambda": {
                "lambdaArn": lambda_arn,
                "toolSchema": {"inlinePayload": tool_schema},
            }
        }
    }
    cred_configs = [{"credentialProviderType": "GATEWAY_IAM_ROLE"}]

    existing = next(
        (
            t
            for t in gw.list_gateway_targets(gatewayIdentifier=gateway_id).get("items", [])
            if t.get("name") == name
        ),
        None,
    )
    if existing:
        target_id = existing["targetId"]
        print(f"  이미 존재: targetId={target_id} — lambdaArn + schema 동기화")
        resp = gw.update_gateway_target(
            gatewayIdentifier=gateway_id,
            targetId=target_id,
            name=name,
            targetConfiguration=target_config,
            credentialProviderConfigurations=cred_configs,
        )
        print(f"  ✅ targetId={target_id} 갱신 완료")
        return resp

    resp = gw.create_gateway_target(
        gatewayIdentifier=gateway_id,
        name=name,
        targetConfiguration=target_config,
        credentialProviderConfigurations=cred_configs,
    )
    print(f"  ✅ targetId={resp['targetId']}")
    return resp


def main():
    required = [
        "DEMO_USER",
        "GATEWAY_IAM_ROLE_ARN",
        "COGNITO_USER_POOL_ID",
        "COGNITO_CLIENT_ID",
        "COGNITO_GATEWAY_SCOPE",
        "LAMBDA_WEB_SEARCH_ARN",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"환경변수 누락: {missing}", file=sys.stderr)
        print("deploy.sh 가 CFN outputs 를 export 한 뒤 호출하세요.", file=sys.stderr)
        sys.exit(1)

    gw = _client()
    gateway = create_gateway(
        gw,
        role_arn=os.environ["GATEWAY_IAM_ROLE_ARN"],
        pool_id=os.environ["COGNITO_USER_POOL_ID"],
        client_id=os.environ["COGNITO_CLIENT_ID"],
        scope=os.environ["COGNITO_GATEWAY_SCOPE"],
    )
    gateway_id = gateway["gatewayId"]
    gateway_url = gateway["gatewayUrl"]

    # Target 추가 전 Gateway READY 대기 — CREATING 상태 Target 추가 시 ValidationException
    wait_for_gateway_ready(gw, gateway_id)

    create_or_update_target(
        gw, gateway_id, TARGET_WEB_SEARCH,
        lambda_arn=os.environ["LAMBDA_WEB_SEARCH_ARN"],
        tool_schema=WEB_SEARCH_TOOL_SCHEMA,
    )

    # deploy.sh 가 stdout 에서 캡처해 .env 에 기록
    print(f"\nGATEWAY_ID={gateway_id}")
    print(f"GATEWAY_URL={gateway_url}")


if __name__ == "__main__":
    main()
