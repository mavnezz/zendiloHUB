-- Rules of one mailbox (NULL: for all mailboxes, which run first); each scope has its own order.
ALTER TABLE mail_filters ADD COLUMN account_id UUID REFERENCES email_accounts (id) ON DELETE CASCADE;
CREATE INDEX mail_filters_account_index ON mail_filters (account_id) WHERE account_id IS NOT NULL;

-- A mailbox for incoming mail only: no SMTP server, so no queue sends with it.
ALTER TABLE email_accounts ALTER COLUMN smtp DROP NOT NULL;

-- The mailbox each ticket's latest customer e-mail came in by: replies of a queue without its own account go out
-- there. ticket_id points into the tickets module.
CREATE TABLE ticket_mailboxes (
    ticket_id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    account_id UUID NOT NULL REFERENCES email_accounts (id) ON DELETE CASCADE,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX ticket_mailboxes_tenant_index ON ticket_mailboxes (tenant_id);
