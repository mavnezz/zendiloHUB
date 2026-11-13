-- An organization's API keys: only the SHA-256 of each key is stored, and its first characters to tell keys apart.
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    permissions TEXT[] NOT NULL CHECK (cardinality(permissions) > 0),
    key_hash TEXT NOT NULL,
    start TEXT NOT NULL,
    created_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    last_used_at TIMESTAMPTZ,
    CONSTRAINT api_keys_key_hash_unique UNIQUE (key_hash)
);

CREATE INDEX api_keys_tenant_index ON api_keys (tenant_id, created_at);
