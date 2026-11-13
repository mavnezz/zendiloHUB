CREATE TABLE groups (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE UNIQUE INDEX groups_tenant_name_unique ON groups (tenant_id, lower(name));

-- user_id points to identity's users; MemberRemoved and UserDeleted clean up.
CREATE TABLE group_members (
    group_id UUID NOT NULL REFERENCES groups (id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    PRIMARY KEY (group_id, user_id)
);

CREATE INDEX group_members_user_index ON group_members (user_id);
