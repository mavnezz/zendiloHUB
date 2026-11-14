-- How each organization numbers its tickets; organizations without a row use the defaults (1001, 1002, … as [#1001]).
CREATE TABLE ticket_numberings (
    tenant_id UUID PRIMARY KEY,
    format TEXT NOT NULL CHECK (format IN ('increment', 'date')),
    start BIGINT NOT NULL,
    date_digits INTEGER NOT NULL CHECK (date_digits BETWEEN 3 AND 6),
    checksum BOOLEAN NOT NULL,
    prefix TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

-- The day and the count of that day, for numbers like 202611140001.
ALTER TABLE ticket_counters
    ADD COLUMN day DATE,
    ADD COLUMN day_count INTEGER NOT NULL DEFAULT 0;
