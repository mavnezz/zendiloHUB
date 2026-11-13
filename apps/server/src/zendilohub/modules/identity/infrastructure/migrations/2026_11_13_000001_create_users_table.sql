CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'admin')),
    locale TEXT NOT NULL CHECK (locale IN ('de', 'en')),
    email_verified_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT users_email_unique UNIQUE (email)
);

CREATE INDEX users_role_index ON users (role);
CREATE INDEX users_created_at_index ON users (created_at);
