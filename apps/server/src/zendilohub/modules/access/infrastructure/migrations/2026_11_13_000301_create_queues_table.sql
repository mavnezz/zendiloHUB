-- tenant_id points to tenancy's tenants; no foreign key across modules (TenantDeleted cleans up).
CREATE TABLE queues (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX queues_tenant_name_unique ON queues (tenant_id, lower(name));
