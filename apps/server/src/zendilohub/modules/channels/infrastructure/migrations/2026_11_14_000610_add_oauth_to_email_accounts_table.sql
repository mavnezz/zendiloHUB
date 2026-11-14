-- Mailboxes connected with OAuth (Google, Microsoft 365): the provider instead of passwords, its tokens sealed.
ALTER TABLE email_accounts
    ADD COLUMN provider TEXT CHECK (provider IN ('google', 'microsoft')),
    ADD COLUMN needs_reconnect BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN oauth_refresh BYTEA,
    ADD COLUMN oauth_access BYTEA,
    ADD COLUMN oauth_access_expires_at TIMESTAMPTZ;

-- What an administrator asked for before going to the provider; each one is used once, within ten minutes.
CREATE TABLE email_connect_requests (
    -- SHA-256 of the OAuth state.
    id TEXT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    provider TEXT NOT NULL CHECK (provider IN ('google', 'microsoft')),
    verifier TEXT NOT NULL,
    account_id UUID REFERENCES email_accounts (id) ON DELETE CASCADE,
    queue_id UUID,
    name TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX email_connect_requests_expires_at_index ON email_connect_requests (expires_at);
CREATE INDEX email_connect_requests_tenant_index ON email_connect_requests (tenant_id);
