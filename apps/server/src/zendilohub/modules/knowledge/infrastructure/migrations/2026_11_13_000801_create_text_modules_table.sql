-- queue_ids point into the access module.
CREATE TABLE text_modules (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    keyword TEXT NOT NULL,
    body TEXT NOT NULL,
    queue_ids UUID[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT text_modules_tenant_keyword_unique UNIQUE (tenant_id, keyword)
);
