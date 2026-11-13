# Security

## Supported versions

Security fixes go into the latest release only. Please update before reporting.

## Reporting a vulnerability

Please do not open a public issue. Report vulnerabilities privately through GitHub instead:
[Security → Report a vulnerability](https://github.com/mavnezz/zendiloHUB/security/advisories/new).

Include the version, steps to reproduce and the impact you see. You get an answer as soon as possible, a fix in a new
release, and credit in the changelog if you want it.

## How zendiloHUB protects your data

- **Setup**: a new self-hosted instance opens a setup wizard that asks for a one-time code the server writes to its log
  and to `/data/setup-token`. Whoever reaches the instance first cannot take it over without access to the server.
- **Accounts**: on a self-hosted instance only people an organization invited can create an account. Passwords are
  hashed with Argon2id. A session is a random token stored hashed; the browser keeps it in an `HttpOnly`,
  `SameSite=Lax` cookie for 30 days. Failed logins are rate-limited per address and per client.
- **API keys**: only their SHA-256 is stored; a key is shown once, acts in its organization only and with exactly the
  permissions it was given.
- **Stored secrets**: encrypted with AES-256-GCM, using `ZENDILOHUB_SECRET_KEY` or the key generated into
  `/data/secret_key`. Whoever can read the data volume can decrypt them, so protect it and its backups.
- **Audit log**: logins and every change are recorded with user and IP address, without passwords or tokens.
- **Container**: runs as an unprivileged user (`PUID`/`PGID`) and serves plain HTTP on one port; TLS belongs to your
  reverse proxy.
