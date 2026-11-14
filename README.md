# zendiloHUB

The open-source helpdesk of the zendilo family: tickets, queues and e-mail for your team, self-hosted with Docker.
AI assistants such as Claude work with tickets through the built-in MCP server.

> **Status:** all phases of the [plan](docs/PLAN.md) are built:
>
> - **Team**: organizations, roles (also custom ones), groups, queues with a rights matrix, audit log, API keys,
>   two-factor login with authenticator apps.
> - **Tickets**: views, search, states with reminders, priorities, tags, watchers and `@` mentions, merge, split,
>   links, time tracking, custom fields, checklists, bulk actions, collision detection, similar tickets, attachments.
> - **E-mail**: mailboxes (IMAP/SMTP, password or OAuth2 for Google and Microsoft 365) with their own rules and a
>   default queue, a sending mailbox per queue, threading, loop protection, signatures and salutations, automatic
>   replies, mail filters with a test, failed e-mails, attachments, S/MIME (sign, encrypt, verify, decrypt),
>   configurable ticket numbers.
> - **Teamwork**: macros, triggers, scheduled jobs, text modules (`::`), SLAs with business hours, notifications
>   (also for followed queues), alert e-mails from triggers.
> - **Reports and integrations**: key figures per day, queue, owner and channel; signed webhooks,
>   also as Slack or Microsoft Teams messages per queue.
> - **Self-service**: knowledge base with a public help center (`/help/<organization>`) and a customer portal
>   (`/portal/<organization>`, sign-in by e-mail link).
> - **AI**: an MCP server (`/mcp`) for Claude and other assistants with each member's rights; optional ticket
>   summaries and draft replies with Claude (`ZENDILOHUB_ANTHROPIC_API_KEY`).

## Quick start

```bash
cp .env.example .env
# Set POSTGRES_PASSWORD in .env, e.g. with: openssl rand -hex 24
docker compose up -d --build
docker compose logs zendilohub | grep "setup code"
```

Open <http://localhost:8080>, enter the setup code from the log and create the administrator and your organization.
Everyone else joins by invitation (**Team → Invite**). Without SMTP settings, e-mails only go to the log
(`docker compose logs zendilohub`), which is fine for a first look.

Behind your reverse proxy, point it at `ZENDILOHUB_HTTP_PORT` and set `ZENDILOHUB_PUBLIC_URL` to the public address.
All settings are in [`.env.example`](.env.example).

## Self-hosted or SaaS

- **Self-hosted** (default): one organization, made by the setup wizard; only invited people can create an account.
- **SaaS** (`ZENDILOHUB_MULTI_TENANT=true`): everyone signs up and creates organizations of their own.

## Operations

- **Data** lives in Docker volumes: `postgres-data` (the database) and `zendilohub-data` (the secret key and
  attachments). Back up both; without the secret key stored secrets cannot be decrypted.
- **Updates**: `docker compose pull` (or `--build`) and `docker compose up -d`; migrations run on start.
- **Memory**: every container has a limit (`ZENDILOHUB_MEMORY_LIMIT`, `POSTGRES_MEMORY_LIMIT`, `REDIS_MEMORY_LIMIT`).
  The whole stack runs on a host with 2 GB of RAM.
- **Workers**: `docker compose up -d --scale worker=3`.
- **API**: keys under **API keys**; the reference is at `/api/reference`.
- **Google and Microsoft 365 mailboxes** (optional): register an app at the provider with the redirect URI
  `<ZENDILOHUB_PUBLIC_URL>/api/v1/email-oauth/callback` and set `ZENDILOHUB_GOOGLE_CLIENT_ID`/`_SECRET` or
  `ZENDILOHUB_MICROSOFT_CLIENT_ID`/`_SECRET`; then **E-mail accounts → Connect**.
- **AI assistant** (optional): set `ZENDILOHUB_ANTHROPIC_API_KEY`; the model is `ZENDILOHUB_AI_MODEL`
  (default `claude-opus-5-5`).

## Development

Python 3.14 with [uv](https://docs.astral.sh/uv/), Node 24, Docker (the server's tests start PostgreSQL and Redis with
testcontainers).

```bash
uv sync --all-packages
npm install
docker compose -f compose.dev.yaml up -d   # PostgreSQL, Redis and Mailpit on localhost
npm run dev:server                     # API on :8096
npm run dev:web                        # web app with hot reload
```

Checks (CI runs the same):

```bash
npm run check:server                   # ruff, mypy strict, pytest with coverage
npm run lint && npm run format:check && npm run typecheck && npm run test:coverage
npm run api:types                      # after changing the API: regenerate the web app's types
```

The structure follows hexagonal design with DDD: modules in `apps/server/src/zendilohub/modules/<module>/` with the
layers `domain`, `application`, `infrastructure` and `ui`, a small core, and an architecture test that keeps the
boundaries. See [docs/PLAN.md](docs/PLAN.md) for the architecture and the roadmap.

## License

[AGPL-3.0](LICENSE). Security issues: see [SECURITY.md](SECURITY.md).
