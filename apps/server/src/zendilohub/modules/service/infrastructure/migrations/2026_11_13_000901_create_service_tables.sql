CREATE TABLE service_calendars (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    timezone TEXT NOT NULL,
    hours JSONB NOT NULL,
    holidays TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL
);

-- queue_ids point into the access module.
CREATE TABLE service_policies (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    name TEXT NOT NULL,
    position INTEGER NOT NULL,
    active BOOLEAN NOT NULL,
    queue_ids UUID[] NOT NULL DEFAULT '{}',
    priorities TEXT[] NOT NULL DEFAULT '{}',
    first_response_minutes INTEGER,
    solution_minutes INTEGER,
    calendar_id UUID REFERENCES service_calendars (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL
);

-- ticket_id points into the tickets module.
CREATE TABLE ticket_clocks (
    ticket_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    policy_id UUID NOT NULL REFERENCES service_policies (id) ON DELETE CASCADE,
    started_at TIMESTAMPTZ NOT NULL,
    first_response_due TIMESTAMPTZ,
    solution_due TIMESTAMPTZ,
    first_responded_at TIMESTAMPTZ,
    solved_at TIMESTAMPTZ,
    breached TEXT[] NOT NULL DEFAULT '{}'
);

CREATE INDEX ticket_clocks_first_due_index ON ticket_clocks (first_response_due) WHERE first_responded_at IS NULL;
CREATE INDEX ticket_clocks_solution_due_index ON ticket_clocks (solution_due) WHERE solved_at IS NULL;
CREATE INDEX ticket_clocks_tenant_index ON ticket_clocks (tenant_id);
