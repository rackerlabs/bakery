# Bakery Providers

Bakery providers are the integration boundary between Bakery's operation queue and external
ticketing or messaging systems.

Bakery is a direct action engine. It does not plan recipes, hydrate ingredients, or orchestrate
workloads. The central runtime flow is:

```text
API request -> TicketOperation row -> worker claim -> provider -> persisted result
```

That flow is intentionally static. Bakery does not fork its internal processing for Jira,
Rackspace Core, ServiceNow, or any other backend. Backend-specific payload shape, validation,
status translation, and API semantics belong inside the provider adapter.

## Contract

Providers implement:

- `normalize_payload(ctx)` to translate Bakery's canonical ticket payload into provider-native
  fields.
- `validate_payload(ctx)` to reject missing provider-native requirements before dispatch.
- `execute(ctx)` to perform provider writes or searches and return a typed result.
- `health_check()` to verify provider configuration/connectivity without exposing secrets.
- `supported_actions()` to advertise supported operations.
- `registration_manifest()` to expose the non-secret provider manifest stored in Bakery's
  provider catalog.
- `bootstrap()` to let a provider prepare provider-owned state before activation. The default
  implementation reports `ready` and performs no mutation.

The typed runtime models live in `bakery/providers/types.py`, and the registry lives in
`bakery/providers/registry.py`.

## Bootstrap

Provider bootstrap syncs every registered provider into `provider_configs` with:

- provider type
- supported actions
- non-secret config schema
- non-secret credential requirement descriptors
- last bootstrap result

The API process performs this sync on startup. Operators can also trigger it explicitly with
`POST /api/v1/providers/bootstrap`. Bootstrap never stores provider secrets; those remain in the
runtime secret source used by each provider.

## Boundaries

Providers must not claim queue rows, mutate Bakery database state, make retry/dead-letter
decisions, or bypass the worker. The worker owns operation lifecycle and persistence; provider
plugins own provider-specific translation, validation, backend calls, and health checks.

Provider results may include canonical Bakery fields such as `data.state` when a backend has a
more precise state than Bakery's default action transition. The worker consumes only those
canonical fields; it must not branch on provider type.
