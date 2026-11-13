CREATE TABLE knowledge_articles (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    tags TEXT[] NOT NULL DEFAULT '{}',
    visibility TEXT NOT NULL CHECK (visibility IN ('internal', 'public')),
    author TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    search TSVECTOR GENERATED ALWAYS AS (to_tsvector('simple', title || ' ' || body)) STORED
);

CREATE INDEX knowledge_articles_tenant_index ON knowledge_articles (tenant_id, updated_at DESC);
CREATE INDEX knowledge_articles_search_index ON knowledge_articles USING GIN (search);
