-- user_id and ticket_id point into other modules (identity, tickets).
CREATE TABLE notifications (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    kind TEXT NOT NULL,
    ticket_id UUID NOT NULL,
    ticket_number BIGINT NOT NULL,
    subject TEXT NOT NULL,
    actor TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    read_at TIMESTAMPTZ
);

CREATE INDEX notifications_user_index ON notifications (tenant_id, user_id, created_at DESC);
CREATE INDEX notifications_unread_index ON notifications (tenant_id, user_id) WHERE read_at IS NULL;

CREATE TABLE notification_settings (
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    email BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (tenant_id, user_id)
);
