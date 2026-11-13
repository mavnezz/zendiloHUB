-- Macros, triggers and scheduled jobs; queue and user ids in the actions point into other modules.
CREATE TABLE automation_rules (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('macro', 'trigger', 'schedule')),
    name TEXT NOT NULL,
    active BOOLEAN NOT NULL,
    position INTEGER NOT NULL,
    event TEXT,
    conditions JSONB NOT NULL DEFAULT '[]',
    schedule JSONB,
    actions JSONB NOT NULL,
    last_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX automation_rules_tenant_index ON automation_rules (tenant_id, kind, position);
