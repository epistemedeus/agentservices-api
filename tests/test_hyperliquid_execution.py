"""Hyperliquid execution door — policy, forward, paper, and no-key guarantees."""
import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

PRINCIPAL = "0x1234567890123456789012345678901234567890"
SIGNED_ORDER = {
    "action": {
        "type": "order",
        "orders": [
            {
                "a": 0,
                "b": True,
                "p": "50000",
                "s": "0.01",
                "r": False,
                "t": {"limit": {"tif": "Gtc"}},
            }
        ],
        "grouping": "na",
    },
    "nonce": 1700000000000,
    "signature": {"r": "0x" + "a" * 64, "s": "0x" + "b" * 64, "v": 27},
}

HL_OK = {
    "status": "ok",
    "response": {"type": "order", "data": {"statuses": [{"resting": {"oid": 99901}}]}},
}


def _fresh_hl_module():
    for name in list(sys.modules):
        if name == "hyperliquid_data" or name.startswith("hyperliquid_data."):
            sys.modules.pop(name, None)
    return importlib.import_module("hyperliquid_data")


@pytest.fixture()
def hl_mod(tmp_path):
    mod = _fresh_hl_module()
    with patch.object(mod, "_policy_dir", return_value=tmp_path):
        yield mod


@pytest.fixture()
def client():
    for name in list(sys.modules):
        if name in ("main", "index", "hyperliquid_data") or name.startswith("hyperliquid_data"):
            sys.modules.pop(name, None)
    from main import app

    return TestClient(app)


def test_bootstrap_documents_agent_sign_model(client):
    resp = client.get("/v1/hl/bootstrap")
    assert resp.status_code == 200
    body = resp.json()
    assert body["venue_api_keys"] == "never_collected"
    assert body["x402"] == "not_used_on_execution_path"
    assert "approveAgent" in body["human_bootstrap"][0]


def test_over_cap_order_rejected(hl_mod):
    hl_mod.set_policy(
        hl_mod.HLExecutionPolicy(principal=PRINCIPAL, max_notional_usd=100.0, allowed_coins=["BTC"])
    )
    req = hl_mod.HLForwardRequest(
        principal=PRINCIPAL,
        signed=hl_mod.SignedHLPayload(**SIGNED_ORDER),
    )
    with pytest.raises(HTTPException) as exc:
        hl_mod.forward_signed_action(req)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "max_notional_exceeded"


def test_disallowed_coin_rejected(hl_mod):
    hl_mod.set_policy(
        hl_mod.HLExecutionPolicy(principal=PRINCIPAL, max_notional_usd=1_000_000, allowed_coins=["ETH"])
    )
    req = hl_mod.HLForwardRequest(
        principal=PRINCIPAL,
        signed=hl_mod.SignedHLPayload(**SIGNED_ORDER),
    )
    with pytest.raises(HTTPException) as exc:
        hl_mod.forward_signed_action(req)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "coin_not_allowlisted"


def test_allowed_order_forwarded(hl_mod):
    hl_mod.set_policy(
        hl_mod.HLExecutionPolicy(principal=PRINCIPAL, max_notional_usd=10_000, allowed_coins=["BTC"])
    )
    req = hl_mod.HLForwardRequest(
        principal=PRINCIPAL,
        signed=hl_mod.SignedHLPayload(**SIGNED_ORDER),
    )
    mock_resp = MagicMock()
    mock_resp.json.return_value = HL_OK
    with patch("hyperliquid_data.requests.post", return_value=mock_resp) as post:
        result = hl_mod.forward_signed_action(req)
    assert post.called
    sent = post.call_args[1]["json"]
    assert "builder" not in sent["action"]
    assert result["receipt"]["order_id"] == 99901
    assert result["receipt"]["orders"][0]["coin"] == "BTC"
    assert result["receipt"]["orders"][0]["side"] == "buy"


def test_http_allowed_order_forwarded(client, tmp_path):
    hl_mod = _fresh_hl_module()
    with patch.object(hl_mod, "_policy_dir", return_value=tmp_path):
        hl_mod.set_policy(
            hl_mod.HLExecutionPolicy(principal=PRINCIPAL, max_notional_usd=10_000, allowed_coins=["BTC"])
        )
    mock_resp = MagicMock()
    mock_resp.json.return_value = HL_OK
    with patch("hyperliquid_data.requests.post", return_value=mock_resp):
        resp = client.post(
            "/v1/hl/order",
            json={"principal": PRINCIPAL, "signed": SIGNED_ORDER},
        )
    assert resp.status_code == 200
    assert resp.json()["receipt"]["order_id"] == 99901


def test_hl_order_path_not_behind_x402(client):
    """Execution must not return HTTP 402."""
    resp = client.post("/v1/hl/order", json={"principal": PRINCIPAL, "signed": SIGNED_ORDER})
    assert resp.status_code != 402


def test_eval_pass_fail(hl_mod):
    hl_mod.set_policy(
        hl_mod.HLExecutionPolicy(principal=PRINCIPAL, max_notional_usd=500, allowed_coins=["BTC"])
    )
    fail = hl_mod.eval_order_against_policy(PRINCIPAL, "BTC", "buy", 0.1, 50_000)
    assert fail["pass"] is False
    pass_result = hl_mod.eval_order_against_policy(PRINCIPAL, "BTC", "buy", 0.001, 50_000)
    assert pass_result["pass"] is True


def test_paper_order_simulated(client):
    resp = client.post(
        "/v1/hl/paper/order",
        json={"coin": "ETH", "side": "sell", "size": 0.5, "price": 3000},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["receipt"]["simulated"] is True
    assert body["receipt"]["coin"] == "ETH"


def test_no_venue_api_key_collection_in_hl_module():
    """HL execution module must not define env vars or fields for user/agent venue keys."""
    path = SRC / "hyperliquid_data.py"
    text = path.read_text()
    import re

    forbidden_patterns = [
        r"os\.environ\.get\([\"'].*API_KEY",
        r"os\.environ\[[\"'].*API_KEY",
        r"private_key\s*=",
        r"secret_key\s*=",
        r"exchange_api_key",
        r"HYPERLIQUID_API_KEY",
        r"HL_API_KEY",
    ]
    hits = [pat for pat in forbidden_patterns if re.search(pat, text, re.IGNORECASE)]
    assert hits == [], f"Forbidden key-collection patterns found: {hits}"


def test_openapi_lists_hl_routes(client):
    schema = client.get("/openapi.json").json()
    paths = schema.get("paths", {})
    assert "/v1/hl/order" in paths
    assert "/v1/hl/paper/order" in paths
    assert "/v1/hl/eval/order" in paths
    order_post = paths["/v1/hl/order"]["post"]
    assert "Hyperliquid" in order_post.get("tags", [])


def test_mcp_tools_include_hl():
    from mcp_endpoint import MCP_TOOLS

    names = {t["name"] for t in MCP_TOOLS}
    for expected in (
        "hl_place_order",
        "hl_cancel_order",
        "hl_order_status",
        "hl_get_policy",
        "hl_set_policy",
        "hl_paper_order",
        "hl_eval_order",
    ):
        assert expected in names


def test_kill_switch_blocks_orders(hl_mod):
    hl_mod.set_policy(
        hl_mod.HLExecutionPolicy(principal=PRINCIPAL, kill_switch=True, allowed_coins=["BTC"])
    )
    req = hl_mod.HLForwardRequest(
        principal=PRINCIPAL,
        signed=hl_mod.SignedHLPayload(**SIGNED_ORDER),
    )
    with pytest.raises(HTTPException) as exc:
        hl_mod.forward_signed_action(req)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"] == "kill_switch_active"
