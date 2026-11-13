-- The organization's own roles; a member's role is a built-in one or the id of one of these.
CREATE TABLE roles (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    permissions TEXT[] NOT NULL CHECK (cardinality(permissions) > 0),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX roles_tenant_name_unique ON roles (tenant_id, lower(name));

ALTER TABLE memberships DROP CONSTRAINT memberships_role_check;
ALTER TABLE invitations DROP CONSTRAINT invitations_role_check;
CREATE INDEX memberships_role_index ON memberships (tenant_id, role);
