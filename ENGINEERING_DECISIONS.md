# Engineering Decisions

This document records decisions as the system is built. Each decision will
include its context, alternatives, chosen approach, and trade-offs.

## PostgreSQL domain schema

### Context

The application needs current work-item state, durable history, duplicate
request protection, and reliable asynchronous work.

### Options considered

- Store history and jobs inside JSON fields on work items.
- Use separate relational tables for history, idempotency, and outbox records.
- Introduce a separate event-streaming platform.

### Chosen approach

Use separate PostgreSQL tables for memberships, work items, append-only
activity events, comments, idempotency keys, and outbox jobs. Use foreign keys,
unique constraints, indexes, and PostgreSQL enums for the core invariants.

### Trade-off

The schema is more explicit than a single JSON document, but it supports
transactional consistency, indexed queries, independent pagination, and
testable retry behavior without adding another service.

## Authentication and password storage

### Context

The challenge needs seeded login accounts and a trusted server-side identity
for team-scoped authorization, but does not require SSO or a registration
flow.

### Options considered

- Add an external identity provider.
- Store plaintext development passwords.
- Use signed bearer tokens with one-way password hashes.

### Chosen approach

Use an eight-hour signed JWT access token and PBKDF2-HMAC-SHA256 password
hashes. The token contains only the user ID; every protected request reloads
the active user from PostgreSQL.

### Trade-off

This is intentionally smaller than production SSO. It is appropriate for the
seeded assessment application, avoids plaintext credentials, and keeps
authorization server-authoritative. A production deployment should replace
local login with the organization's identity provider and rotate secrets.

## Work-item API consistency

### Context

Work items can be changed by several users and can be retried by clients.
Plain read-then-write CRUD would allow lost updates and duplicate side effects.

### Options considered

- Trust the latest write.
- Serialize all writes with a global lock.
- Use conditional database updates, explicit transitions, and scoped
  idempotency records.

### Chosen approach

Use PostgreSQL conditional updates for version-aware edits and claims, an
explicit server-side transition map, team membership checks on every item
operation, cursor pagination, and idempotency keys for creation retries.
Important mutation history and notification jobs are inserted in the same
transaction as the work-item change.

### Trade-off

Clients must send an expected version and handle `409 Conflict`, but no user
silently overwrites another user's work. Conditional row updates also avoid a
global lock while preserving atomic claiming.

## PostgreSQL outbox worker

### Context

Assignment notifications are secondary work. They should not make the primary
claim fail, but they must survive process crashes and temporary failures.

### Options considered

- Send the notification inside the API request.
- Use a separate queue service immediately.
- Store a durable outbox row in the same PostgreSQL transaction and process it
  with a worker.

### Chosen approach

Use the PostgreSQL outbox table. The worker claims one ready row with
`FOR UPDATE SKIP LOCKED`, increments its attempt count, runs an idempotent
handler, and records completion or a retry/terminal failure.

### Trade-off

The worker is less feature-rich than a managed queue, but it keeps the
assessment deployable with only PostgreSQL and demonstrates durable retries,
backoff, and duplicate-delivery safety. A production notification provider
would require an external-effect idempotency key.

## React server-state handling

### Context

The dashboard and item detail screen read server-owned data that can change
while a user is viewing it. Treating local component state as authoritative
would make conflicts and stale results easy to hide.

### Options considered

- Fetch data manually in each component.
- Store all server data in a global client-side store.
- Use TanStack Query for cached server state and explicit invalidation.

### Chosen approach

Use TanStack Query for item, activity, and current-user queries. Mutations
replace authoritative item data from the API and invalidate activity or list
queries when needed. API conflicts and forbidden responses are surfaced as
user-visible messages.

### Trade-off

This adds a query-cache dependency, but it avoids duplicated loading/error
logic and keeps the browser from pretending an optimistic action succeeded
when the server rejected it.

## Initial scaffold

### Context

The project needs a reproducible local environment for a two-day build.

### Options considered

- Run every dependency directly on the host.
- Use PostgreSQL in Docker while running application processes locally.
- Containerize the entire development environment immediately.

### Chosen approach

Use Docker Compose for PostgreSQL and run FastAPI and React with their native
development commands during implementation.

### Trade-off

This keeps iteration and debugging fast while making the database dependency
consistent. Full application containers can be added later if the fresh-clone
workflow benefits from them.

## Local PostgreSQL port

### Context

The development machine may already have PostgreSQL installed on port 5432.
Binding the Compose database to the same host port makes startup fail or can
silently connect commands to the wrong database.

### Chosen approach

Expose the Compose PostgreSQL service on host port `5433` while retaining
container port `5432`. The application defaults, Alembic configuration, and
`.env.example` use `5433`.

### Trade-off

The local URL is slightly different from PostgreSQL's conventional host port,
but Compose can run without stopping or modifying another PostgreSQL service.
