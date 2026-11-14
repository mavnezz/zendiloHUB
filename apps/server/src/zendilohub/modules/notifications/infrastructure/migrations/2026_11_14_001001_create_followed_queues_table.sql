-- Queues a member follows (queue and user ids point into other modules: access, identity).
CREATE TABLE followed_queues (
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    queue_id UUID NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('new', 'all')),
    PRIMARY KEY (tenant_id, user_id, queue_id)
);

CREATE INDEX followed_queues_queue_index ON followed_queues (tenant_id, queue_id);
