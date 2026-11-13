-- tenant_id and queue_id point into other modules (tenancy, access) without foreign keys.
CREATE TABLE email_accounts (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    address TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    queue_id UUID NOT NULL,
    imap JSONB NOT NULL,
    smtp JSONB NOT NULL,
    imap_password BYTEA,
    smtp_password BYTEA,
    folder TEXT NOT NULL DEFAULT 'INBOX',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_uid BIGINT NOT NULL DEFAULT 0,
    uid_validity BIGINT,
    last_fetch_at TIMESTAMPTZ,
    last_error TEXT,
    failing_since TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT email_accounts_tenant_address_unique UNIQUE (tenant_id, address)
);

CREATE TABLE channel_templates (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('signature', 'salutation')),
    name TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX channel_templates_tenant_index ON channel_templates (tenant_id, kind);

CREATE TABLE queue_channels (
    tenant_id UUID NOT NULL,
    queue_id UUID PRIMARY KEY,
    account_id UUID REFERENCES email_accounts (id) ON DELETE SET NULL,
    signature_id UUID REFERENCES channel_templates (id),
    salutation_id UUID REFERENCES channel_templates (id),
    auto_reply BOOLEAN NOT NULL DEFAULT FALSE,
    auto_reply_subject TEXT NOT NULL DEFAULT '',
    auto_reply_body TEXT NOT NULL DEFAULT ''
);

CREATE INDEX queue_channels_tenant_index ON queue_channels (tenant_id);

CREATE TABLE personal_settings (
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    signature TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE mail_filters (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    position INTEGER NOT NULL,
    active BOOLEAN NOT NULL,
    match TEXT NOT NULL CHECK (match IN ('all', 'any')),
    conditions JSONB NOT NULL,
    actions JSONB NOT NULL,
    stop BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX mail_filters_tenant_index ON mail_filters (tenant_id, position);

CREATE TABLE failed_emails (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    account_id UUID REFERENCES email_accounts (id) ON DELETE SET NULL,
    raw BYTEA NOT NULL,
    error TEXT NOT NULL,
    received_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX failed_emails_tenant_index ON failed_emails (tenant_id, received_at DESC);

-- message_id and ticket_id point into the tickets module.
CREATE TABLE email_deliveries (
    message_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'sent', 'failed', 'skipped')),
    account_id UUID REFERENCES email_accounts (id) ON DELETE SET NULL,
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX email_deliveries_ticket_index ON email_deliveries (tenant_id, ticket_id);
