---
sidebar_position: 3
title: REST API
---

# REST API

Everything the console does goes through the public REST API at `/api/v1`. The running
installation serves the OpenAPI document at `/api/v1/openapi.json` and Swagger UI at
`/api/v1/docs`; the same document is checked into the repository as `frontend/openapi.json`.

:::note Scope
gShare is deliberately console-first: there are no API keys, CLI, or SDK. The API exists for the
console and for operators automating administration with a user's own token.
:::

## Authentication

```bash
curl -s -X POST https://gshare.example.com/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"jieun@example.com","password":"…"}'
# → {"access_token": "…", "token_type": "bearer", …}
```

Send the token as `Authorization: Bearer <token>`. Tokens are short-lived; there is no refresh
endpoint — sign in again. A user flagged `must_change_password` can only call the password
endpoints until they do.

## Conventions

- **Pagination** — list endpoints take `page` and `size` and return
  `{"data": [...], "pagination": {"page", "size", "total"}}`.
- **Idempotency** — every write that creates something (`POST /sessions`, `POST /storage/volumes`,
  credit operations) accepts an `Idempotency-Key` header; repeating a request with the same key
  returns the original result instead of creating a duplicate.
- **Errors** — one envelope:
  ```json
  {"error": {"code": "quota_exceeded", "message": "…", "details": {...}, "request_id": "…", "timestamp": "…"}}
  ```
  `code` is stable and is what the console maps to a message; `details` carries what to fix
  (for example the `reported_models` a fleet offers when a session is `unserviceable`).
- **Tenant scope** — every list is filtered by the caller's role; asking for more than your
  scope returns your scope, not a 403, so a token cannot be used to probe.
- **Live updates** — `GET /sessions/events` is a server-sent event stream the console listens
  to; poll the lists if you cannot hold a stream.

## Resource groups

| Prefix | What it covers |
|---|---|
| `/auth`, `/users`, `/organizations`, `/projects` | Sign-in, accounts, organizations, groups (`projects` in the API) and memberships |
| `/sessions` | Create, list (`scope=mine|all`), detail, pause/resume/restart/terminate, connect links, logs, usage, `bulk-terminate`, `preview-cost`, `gpu-availability` |
| `/queue` | Queue entries, cancel, priority |
| `/credits`, `/budgets` | Wallets, allocations, requests, refills, ledger; organization budgets |
| `/storage/volumes`, `/storage/pools` | Volumes, shares, quota, locks; storage pools |
| `/offerings`, `/presets`, `/images`, `/resource-policies` | The catalogue and policies, including quota requests |
| `/clusters`, `/nodes`, `/gpu-devices`, `/node-pools` | Infrastructure: registration, cordon/drain/delete, cards, pools |
| `/monitoring`, `/dashboard`, `/metrics` | Metrics proxies and summaries |
| `/audit` | Audit log with filters and CSV export |
| `/notifications`, `/webhooks` | The bell, and outbound webhooks per organization |
| `/system` | Branding, sign-up policy, placement policy |
| `/health` | Liveness for probes |

The **internal** plane (`/internal/...`, `/.well-known/gshare-internal-jwks.json`) is for
operators only and is authenticated with the RS256 internal JWT, never a user token.
