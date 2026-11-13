-- tenant_id, queue_id, customer_id, owner_id and responsible_id point into other modules (tenancy, access,
-- customers, identity) without foreign keys; integration events and contracts keep them right.
CREATE TABLE ticket_counters (
    tenant_id UUID PRIMARY KEY,
    last_number BIGINT NOT NULL
);

CREATE TABLE tickets (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    number BIGINT NOT NULL,
    subject TEXT NOT NULL,
    queue_id UUID NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('new', 'open', 'pending_reminder', 'pending_close', 'closed', 'merged')),
    priority TEXT NOT NULL CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    channel TEXT NOT NULL,
    customer_id UUID,
    owner_id UUID,
    responsible_id UUID,
    tags TEXT[] NOT NULL DEFAULT '{}',
    pending_until TIMESTAMPTZ,
    merged_into_id UUID REFERENCES tickets (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    first_response_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    last_message_at TIMESTAMPTZ,
    CONSTRAINT tickets_tenant_number_unique UNIQUE (tenant_id, number)
);

CREATE INDEX tickets_queue_state_index ON tickets (tenant_id, queue_id, state, updated_at DESC);
CREATE INDEX tickets_owner_index ON tickets (tenant_id, owner_id) WHERE owner_id IS NOT NULL;
CREATE INDEX tickets_customer_index ON tickets (tenant_id, customer_id);
CREATE INDEX tickets_pending_index ON tickets (state, pending_until) WHERE pending_until IS NOT NULL;
CREATE INDEX tickets_tags_index ON tickets USING GIN (tags);
