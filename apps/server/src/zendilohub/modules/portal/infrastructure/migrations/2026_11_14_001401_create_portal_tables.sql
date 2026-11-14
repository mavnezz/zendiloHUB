-- queue_id points into access, contact_id into customers.
CREATE TABLE portal_settings (
    tenant_id UUID PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    queue_id UUID,
    company_tickets BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE portal_logins (
    token_hash TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('link', 'session')),
    tenant_id UUID NOT NULL,
    contact_id UUID NOT NULL,
    email TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX portal_logins_expires_index ON portal_logins (expires_at);
