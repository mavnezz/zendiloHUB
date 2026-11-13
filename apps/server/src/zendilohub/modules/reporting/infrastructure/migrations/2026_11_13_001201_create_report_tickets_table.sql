-- The reporting module's own copy of each ticket's key dates (kept up to date from ticket events).
CREATE TABLE report_tickets (
    ticket_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    queue_id UUID NOT NULL,
    priority TEXT NOT NULL,
    channel TEXT NOT NULL,
    owner_id UUID,
    state TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    first_response_at TIMESTAMPTZ,
    closed_at TIMESTAMPTZ,
    reopened INTEGER NOT NULL DEFAULT 0,
    breaches INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX report_tickets_created_index ON report_tickets (tenant_id, created_at);
CREATE INDEX report_tickets_closed_index ON report_tickets (tenant_id, closed_at) WHERE closed_at IS NOT NULL;
