CREATE TABLE tenants (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'suspended')),
    timezone TEXT NOT NULL,
    locale TEXT NOT NULL CHECK (locale IN ('de', 'en')),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX tenants_created_at_index ON tenants (created_at);
