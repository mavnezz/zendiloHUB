CREATE TABLE ticket_messages (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('public', 'internal')),
    direction TEXT NOT NULL CHECK (direction IN ('in', 'out')),
    author_kind TEXT NOT NULL CHECK (author_kind IN ('agent', 'customer', 'system')),
    author_id UUID,
    author_name TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL,
    body_html TEXT,
    subject TEXT,
    from_address TEXT,
    to_addresses TEXT[] NOT NULL DEFAULT '{}',
    cc_addresses TEXT[] NOT NULL DEFAULT '{}',
    email_message_id TEXT,
    in_reply_to TEXT,
    "references" TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL,
    search TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', coalesce(subject, '') || ' ' || body)) STORED
);

CREATE INDEX ticket_messages_ticket_index ON ticket_messages (ticket_id, created_at);
CREATE INDEX ticket_messages_search_index ON ticket_messages USING GIN (search);
CREATE INDEX ticket_messages_email_id_index ON ticket_messages (tenant_id, email_message_id)
    WHERE email_message_id IS NOT NULL;
