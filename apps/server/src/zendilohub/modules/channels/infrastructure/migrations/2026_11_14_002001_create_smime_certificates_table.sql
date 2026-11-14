-- S/MIME: own certificates with their sealed private keys, contacts' certificates and trusted authorities.
CREATE TABLE smime_certificates (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('own', 'contact', 'ca')),
    fingerprint TEXT NOT NULL,
    subject TEXT NOT NULL,
    issuer TEXT NOT NULL,
    serial TEXT NOT NULL,
    emails TEXT[] NOT NULL,
    not_before TIMESTAMPTZ NOT NULL,
    not_after TIMESTAMPTZ NOT NULL,
    is_ca BOOLEAN NOT NULL,
    certificate TEXT NOT NULL,
    private_key BYTEA,
    created_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT smime_certificates_unique UNIQUE (tenant_id, kind, fingerprint)
);

CREATE INDEX smime_certificates_emails_index ON smime_certificates USING GIN (emails);

ALTER TABLE queue_channels
    ADD COLUMN smime_sign BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN smime_encrypt TEXT NOT NULL DEFAULT 'never' CHECK (smime_encrypt IN ('never', 'when_possible', 'always'));
