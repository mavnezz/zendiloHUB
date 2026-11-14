CREATE TABLE ticket_attachments (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    -- NULL while an upload waits for the message being written.
    message_id UUID REFERENCES ticket_messages (id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    size BIGINT NOT NULL CHECK (size >= 0),
    sha256 TEXT NOT NULL,
    content_id TEXT,
    created_by UUID,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ticket_attachments_message_index ON ticket_attachments (message_id, created_at);
CREATE INDEX ticket_attachments_ticket_index ON ticket_attachments (ticket_id);
CREATE INDEX ticket_attachments_pending_index ON ticket_attachments (created_at) WHERE message_id IS NULL;
