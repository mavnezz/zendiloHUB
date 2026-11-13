CREATE TABLE invitations (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'admin', 'manager', 'agent')),
    -- SHA-256 of the token in the invitation link.
    token_hash TEXT NOT NULL,
    invited_by UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT invitations_token_hash_unique UNIQUE (token_hash),
    CONSTRAINT invitations_tenant_email_unique UNIQUE (tenant_id, email)
);

CREATE INDEX invitations_expires_at_index ON invitations (expires_at);
