CREATE TABLE password_resets (
    -- SHA-256 of the token in the reset link.
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX password_resets_user_id_index ON password_resets (user_id);
CREATE INDEX password_resets_expires_at_index ON password_resets (expires_at);
