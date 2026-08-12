import importlib


def test_provider_adapter_passthrough(monkeypatch):
    import src.erc8004_provider as p
    calls = []
    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append((url, params, headers, timeout))
        class Response:
            status_code = 200
            def json(self): return {"agents": [{"agentId": "7"}]}
        return Response()
    monkeypatch.setattr(p.requests, "get", fake_get)
    assert p.agents(limit=2, chain_id=8453, payment="signed") == {"agents": [{"agentId": "7"}]}
    assert calls[0][1] == {"limit": 2, "offset": 0, "chain_id": 8453}
    assert calls[0][2]["X-PAYMENT"] == "signed"


def test_provider_errors_preserve_status_and_detail(monkeypatch):
    import src.erc8004_provider as p
    def fake_get(*args, **kwargs):
        class Response:
            status_code = 402
            text = "payment required"
            def json(self): return {"accepts": [{"maxAmountRequired": "1000"}]}
        return Response()
    monkeypatch.setattr(p.requests, "get", fake_get)
    try:
        p.agent("1")
        assert False
    except RuntimeError as exc:
        assert exc.status_code == 402
        assert exc.detail["accepts"][0]["maxAmountRequired"] == "1000"
