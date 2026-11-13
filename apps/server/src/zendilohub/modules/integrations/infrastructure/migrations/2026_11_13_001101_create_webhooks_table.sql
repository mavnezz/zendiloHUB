CREATE TABLE webhooks (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    url TEXT NOT NULL,
    events TEXT[] NOT NULL,
    active BOOLEAN NOT NULL,
    secret BYTEA,
    created_at TIMESTAMPTZ NOT NULL,
    last_delivery_at TIMESTAMPTZ,
    last_status INTEGER,
    last_error TEXT
);

CREATE INDEX webhooks_tenant_index ON webhooks (tenant_id);

CREATE TABLE webhook_deliveries (
    id UUID PRIMARY KEY,
    webhook_id UUID NOT NULL REFERENCES webhooks (id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    event TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    status INTEGER,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX webhook_deliveries_webhook_index ON webhook_deliveries (webhook_id, created_at DESC);
