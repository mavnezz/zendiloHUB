-- tenant_id and actor_id point to other modules' tables; no foreign keys across modules.
CREATE TABLE audit_log (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    actor_id UUID,
    actor_email TEXT,
    action TEXT NOT NULL,
    target TEXT,
    succeeded BOOLEAN NOT NULL,
    status SMALLINT NOT NULL,
    client TEXT,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX audit_log_tenant_index ON audit_log (tenant_id, created_at DESC, id DESC);
CREATE INDEX audit_log_created_at_index ON audit_log (created_at DESC, id DESC);
CREATE INDEX audit_log_actor_index ON audit_log (actor_id);
