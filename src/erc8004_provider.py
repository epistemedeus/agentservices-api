"""Read adapter for an external ERC-8004 indexer.

The provider is QuickNode's ERC-8004 Explorer REST API by default. AgentServices
never invents registry data: every read is fetched from the configured provider
and provider response metadata is preserved. Set ERC8004_PROVIDER_BASE_URL to
another compatible indexer when needed.
"""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlencode


class _HTTP:
    @staticmethod
    def get(url: str, params=None, headers=None, timeout=15):
        if params:
            url += "?" + urlencode(params)
        request = Request(url, headers=headers or {}, method="GET")
        try:
            response = urlopen(request, timeout=timeout)
            status = response.status
            body = response.read().decode()
        except HTTPError as error:
            status = error.code
            body = error.read().decode()

        class Response:
            status_code = status
            text = body
            def json(self):
                return json.loads(self.text)
        return Response()


requests = _HTTP()

BASE_URL = os.environ.get("ERC8004_PROVIDER_BASE_URL", "https://erc-8004.quicknode.com")
TIMEOUT = float(os.environ.get("ERC8004_PROVIDER_TIMEOUT", "15"))


def _get(path: str, params: dict[str, Any] | None = None, payment: str = "") -> Any:
    headers = {"Accept": "application/json"}
    if payment:
        headers["X-PAYMENT"] = payment
    response = requests.get(f"{BASE_URL.rstrip('/')}{path}", params=params, headers=headers, timeout=TIMEOUT)
    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:1000]
        error = RuntimeError(f"ERC-8004 provider returned HTTP {response.status_code}")
        setattr(error, "status_code", response.status_code)
        setattr(error, "detail", detail)
        raise error
    return response.json()


def agents(limit: int = 25, offset: int = 0, chain_id: int | None = None, payment: str = "") -> Any:
    params: dict[str, Any] = {"limit": limit, "offset": offset}
    if chain_id is not None:
        params["chain_id"] = chain_id
    return _get("/v1/agents", params, payment)


def agent(agent_id: str, payment: str = "") -> Any:
    return _get(f"/v1/agents/{quote(agent_id, safe='')}", payment=payment)


def reputation(agent_id: str, payment: str = "") -> Any:
    return _get(f"/v1/agents/{quote(agent_id, safe='')}/reputation", payment=payment)


def feedback(agent_id: str, limit: int = 25, offset: int = 0, payment: str = "") -> Any:
    return _get(f"/v1/agents/{quote(agent_id, safe='')}/feedback",
                {"limit": limit, "offset": offset}, payment)


def validations(agent_id: str, limit: int = 25, offset: int = 0, payment: str = "") -> Any:
    return _get(f"/v1/agents/{quote(agent_id, safe='')}/validations",
                {"limit": limit, "offset": offset}, payment)


def provider_info() -> dict[str, str]:
    return {"provider": "erc-8004-indexer", "base_url": BASE_URL,
            "source": "external ERC-8004 registry/indexer", "payment": "provider x402 passthrough"}
