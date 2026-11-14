ALTER TABLE users
    ADD COLUMN totp_secret BYTEA,
    ADD COLUMN totp_pending BYTEA,
    ADD COLUMN totp_enabled_at TIMESTAMPTZ,
    ADD COLUMN totp_last_step BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN recovery_codes TEXT[] NOT NULL DEFAULT '{}';
