-- Customer organizations; tenant_id points to tenancy's tenants, without a foreign key across modules
-- (TenantDeleted cleans up).
CREATE TABLE companies (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    domain TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX companies_tenant_name_unique ON companies (tenant_id, lower(name));
CREATE UNIQUE INDEX companies_tenant_domain_unique ON companies (tenant_id, domain) WHERE domain IS NOT NULL;
