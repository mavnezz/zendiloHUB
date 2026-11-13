-- Sign-ups waiting for their e-mail confirmation; the account is created on confirmation.
CREATE TABLE registrations (
    -- SHA-256 of the token in the confirmation link.
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    locale TEXT NOT NULL CHECK (locale IN ('de', 'en')),
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX registrations_email_index ON registrations (email, created_at);
CREATE INDEX registrations_expires_at_index ON registrations (expires_at);
