-- S/MIME of received e-mails: {signed, signature, signer, encrypted}; NULL when neither signed nor encrypted.
ALTER TABLE ticket_messages ADD COLUMN security JSONB;
