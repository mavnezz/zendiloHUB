CREATE TABLE login_challenges (
    -- SHA-256 of the token the browser holds between the password and the code.
    id TEXT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX login_challenges_user_id_index ON login_challenges (user_id);
CREATE INDEX login_challenges_expires_at_index ON login_challenges (expires_at);
