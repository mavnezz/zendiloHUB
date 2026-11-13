ALTER TABLE tickets ADD COLUMN fields JSONB NOT NULL DEFAULT '{}';

CREATE TABLE ticket_fields (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    key TEXT NOT NULL,
    label TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('text', 'number', 'select', 'checkbox', 'date')),
    options TEXT[] NOT NULL DEFAULT '{}',
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ticket_fields_tenant_key_unique UNIQUE (tenant_id, key)
);

CREATE TABLE ticket_checklist_items (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    ticket_id UUID NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    text TEXT NOT NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    position INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ticket_checklist_items_ticket_index ON ticket_checklist_items (ticket_id, position);
