-- What a group may do in a queue; no row: nothing.
CREATE TABLE queue_grants (
    group_id UUID NOT NULL REFERENCES groups (id) ON DELETE CASCADE,
    queue_id UUID NOT NULL REFERENCES queues (id) ON DELETE CASCADE,
    rights TEXT[] NOT NULL CHECK (cardinality(rights) > 0),
    PRIMARY KEY (group_id, queue_id)
);

CREATE INDEX queue_grants_queue_index ON queue_grants (queue_id);
