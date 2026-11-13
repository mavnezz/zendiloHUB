CREATE TABLE contacts (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    company_id UUID REFERENCES companies (id) ON DELETE SET NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX contacts_tenant_email_unique ON contacts (tenant_id, email) WHERE email IS NOT NULL;
CREATE INDEX contacts_tenant_phone_index ON contacts (tenant_id, phone) WHERE phone IS NOT NULL;
CREATE INDEX contacts_tenant_name_index ON contacts (tenant_id, lower(name));
CREATE INDEX contacts_company_index ON contacts (company_id);
