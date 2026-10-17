# Worker

The worker processes PostgreSQL outbox jobs created transactionally by the API.

Run it from the repository root:

```powershell
python worker/main.py
```

It uses `FOR UPDATE SKIP LOCKED` to safely claim jobs when multiple worker
instances run, retries failures with capped exponential backoff, and marks
jobs as completed or terminally failed. Handlers must be idempotent because a
worker can crash after an external side effect and before committing the
completed state.
