# AgentServices Buyer Quickstart

AgentServices gives AI agents paid access to research, market intelligence, on-chain data, and inference without API-key provisioning or a subscription. Requests settle per call in USDC on Base through [x402](https://x402.org).

## 1. Test the free surface

```bash
curl "https://api.agentservices.to/v1/prices?symbols=BTC,ETH"
```

## 2. Pick an outcome

Use a bundled endpoint when the agent needs a result, not raw plumbing:

| Outcome | Endpoint | Price* |
|---|---|---:|
| Deep research brief | `GET /v1/research?q=...` | $0.05 |
| Market pulse | `GET /v1/market-pulse` | $0.05 |
| Token risk report | `GET /v1/token-risk/{symbol}` | $0.03 |
| Portfolio intelligence | `GET /v1/portfolio?symbol=BTC` | $0.10 |
| On-chain overview | `GET /v1/onchain-overview` | $0.15 |
| Agent inference | `POST /v1/inference` | $0.03 |

`*` Indicative prices shown in the live catalog; the HTTP 402 response is authoritative for the requested call.

## 3. Let x402 handle payment

A paid request follows one simple loop:

1. Request the endpoint.
2. Receive `402 Payment Required` with the payment requirements.
3. Pay the stated amount in USDC on Base.
4. Retry with the x402 payment proof.
5. Receive the result.

There is no AgentServices API key to rotate. Keep wallet credentials in your agent runtime, never in source code or prompts.

## 4. Connect an agent directly

For MCP-compatible clients, add the hosted Streamable HTTP server:

```json
{
  "mcpServers": {
    "agentservices": {
      "url": "https://agentservices.to/mcp",
      "transport": "streamable-http"
    }
  }
}
```

For direct integrations, use the [OpenAPI docs](https://api.agentservices.to/docs) or the [JavaScript SDK](https://www.npmjs.com/package/@agentservices/client).

## 5. Run a no-spend buyer proof

Verify a real free response and decode the live x402 requirements for a paid token-risk report—without signing or settling any payment:

```bash
python3 examples/token_risk_buyer_proof.py BTC
```

The script uses the canonical `api.agentservices.to` domain, confirms the free price surface, then verifies and displays the exact Base/USDC payment challenge for `GET /v1/token-risk/BTC`.

## 6. Start with one paid call

```text
Goal: produce a concise research brief on the Base ecosystem.
Call: GET https://api.agentservices.to/v1/research?q=Base ecosystem
Budget: $0.05 USDC on Base
Output: synthesized research returned to the agent after payment.
```

## Links

- [Live API](https://agentservices.to)
- [OpenAPI docs](https://api.agentservices.to/docs)
- [MCP endpoint](https://agentservices.to/mcp)
- [x402 discovery](https://agentservices.to/.well-known/x402)
- [Source and SDK](https://github.com/vbkotecha/agentservices-api)
