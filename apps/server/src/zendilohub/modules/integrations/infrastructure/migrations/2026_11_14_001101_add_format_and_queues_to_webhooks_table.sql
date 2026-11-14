-- Chat formats (Slack, Microsoft Teams) and a filter by queue (empty: all queues; queue ids point into access).
ALTER TABLE webhooks
    ADD COLUMN format TEXT NOT NULL DEFAULT 'json' CHECK (format IN ('json', 'slack', 'teams')),
    ADD COLUMN queue_ids UUID[] NOT NULL DEFAULT '{}';
