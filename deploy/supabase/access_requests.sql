-- Apply to the existing Hpa Rating installation before publishing the public form.
CREATE TABLE hpa_rating.access_requests (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    camping text NOT NULL CHECK (length(camping) BETWEEN 1 AND 140),
    email text NOT NULL CHECK (length(email) BETWEEN 3 AND 254 AND email=lower(email)),
    created_at text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','approved','declined')),
    decided_at text,
    guest_id text REFERENCES hpa_rating.guests(id)
);
CREATE UNIQUE INDEX pending_access_email ON hpa_rating.access_requests(email) WHERE status IN ('pending','approved');
REVOKE ALL ON hpa_rating.access_requests FROM PUBLIC, anon, authenticated, service_role, hpa_rating_guest;
GRANT SELECT,UPDATE(status,decided_at,guest_id) ON hpa_rating.access_requests TO hpa_rating_admin;

CREATE FUNCTION hpa_rating.submit_access_request(rid text, camping_name text, contact text, submitted text)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    INSERT INTO hpa_rating.access_requests(id,camping,email,created_at)
    VALUES (rid,camping_name,contact,submitted) ON CONFLICT DO NOTHING;
$$;
REVOKE ALL ON FUNCTION hpa_rating.submit_access_request(text,text,text,text)
    FROM PUBLIC,anon,authenticated,service_role;
GRANT EXECUTE ON FUNCTION hpa_rating.submit_access_request(text,text,text,text) TO hpa_rating_guest;
