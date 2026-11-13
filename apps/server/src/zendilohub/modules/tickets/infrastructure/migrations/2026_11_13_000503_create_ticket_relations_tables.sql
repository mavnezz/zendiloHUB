CREATE TABLE ticket_history (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    actor_id UUID,
    actor_name TEXT NOT NULL,
    action TEXT NOT NULL,
    field TEXT,
    old TEXT,
    new TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ticket_history_ticket_index ON ticket_history (ticket_id, created_at);

CREATE TABLE ticket_watchers (
    ticket_id UUID NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    PRIMARY KEY (ticket_id, user_id)
);

CREATE INDEX ticket_watchers_user_index ON ticket_watchers (tenant_id, user_id);

-- Each link is stored once per direction: (a, b, 'parent') means b is the parent of a.
CREATE TABLE ticket_links (
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    other_id UUID NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('related', 'parent', 'child')),
    PRIMARY KEY (ticket_id, other_id)
);

CREATE TABLE ticket_time (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    minutes INTEGER NOT NULL CHECK (minutes > 0),
    message_id UUID,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ticket_time_ticket_index ON ticket_time (ticket_id);
