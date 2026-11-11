CREATE TABLE hpa_rating_staff.admin_email_challenge (
    id integer PRIMARY KEY CHECK (id=1), nonce text NOT NULL, proof text NOT NULL,
    sent_at bigint NOT NULL, expires bigint NOT NULL, failures integer NOT NULL
);
REVOKE ALL ON hpa_rating_staff.admin_email_challenge
    FROM PUBLIC, anon, authenticated, service_role, hpa_rating_guest, hpa_rating_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON hpa_rating_staff.admin_email_challenge TO hpa_rating_webadmin;
