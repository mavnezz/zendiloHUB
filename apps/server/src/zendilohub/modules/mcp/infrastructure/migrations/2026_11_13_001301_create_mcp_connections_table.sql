-- user_id points into identity, tenant_id into tenancy (events clean up).
CREATE TABLE mcp_connections (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    email TEXT NOT NULL,
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    start TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ
);

CREATE INDEX mcp_connections_member_index ON mcp_connections (tenant_id, user_id);
