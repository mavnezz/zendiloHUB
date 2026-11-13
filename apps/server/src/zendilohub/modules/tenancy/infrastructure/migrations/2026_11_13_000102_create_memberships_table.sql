-- user_id points to identity's users; no foreign key across modules (UserDeleted cleans up).
CREATE TABLE memberships (
    tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'manager', 'agent')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, user_id),
    CONSTRAINT memberships_tenant_email_unique UNIQUE (tenant_id, email)
);

CREATE INDEX memberships_user_id_index ON memberships (user_id);
