-- Responses are kept apart from the operator's request list and disappear on refusal.
CREATE TABLE hpa_rating.request_starters (
    request_id text PRIMARY KEY REFERENCES hpa_rating.access_requests(id) ON DELETE CASCADE,
    content text NOT NULL CHECK (octet_length(content) BETWEEN 2 AND 2048)
);
CREATE TABLE hpa_rating.starter_imports (
    owner_id text NOT NULL REFERENCES hpa_rating.guests(id), draft_id text NOT NULL CHECK (draft_id ~ '^[0-9a-f]{32}$'),
    audit_id text NOT NULL UNIQUE REFERENCES hpa_rating.audits(id) ON DELETE CASCADE,
    continued integer NOT NULL DEFAULT 0, PRIMARY KEY(owner_id,draft_id)
);
CREATE TABLE hpa_rating.starter_daily (
    day text NOT NULL, event text NOT NULL CHECK (event IN ('home','start','request','continued')),
    total bigint NOT NULL, PRIMARY KEY(day,event)
);
REVOKE ALL ON hpa_rating.request_starters,hpa_rating.starter_imports,hpa_rating.starter_daily
    FROM PUBLIC,anon,authenticated,service_role,hpa_rating_admin,hpa_rating_webadmin,hpa_rating_guest;
GRANT SELECT,INSERT,UPDATE ON hpa_rating.starter_imports TO hpa_rating_guest;
GRANT SELECT ON hpa_rating.starter_daily TO hpa_rating_webadmin,hpa_rating_admin;

CREATE FUNCTION hpa_rating.count_starter_event(kind text)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    INSERT INTO hpa_rating.starter_daily AS tally(day,event,total)
    VALUES (to_char(now() AT TIME ZONE 'UTC','YYYY-MM-DD'),kind,1)
    ON CONFLICT(day,event) DO UPDATE SET total=tally.total+1;
$$;
CREATE FUNCTION hpa_rating.submit_starter_request(rid text,camping_name text,contact text,submitted text,body text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
BEGIN
    INSERT INTO hpa_rating.access_requests(id,camping,email,created_at)
        VALUES(rid,camping_name,contact,submitted) ON CONFLICT DO NOTHING;
    IF FOUND THEN
        IF body IS NOT NULL THEN
            INSERT INTO hpa_rating.request_starters VALUES(rid,body);
        END IF;
        PERFORM hpa_rating.count_starter_event('request');
    END IF;
END;
$$;
CREATE FUNCTION hpa_rating.approved_starter(gid text)
RETURNS TABLE(content text,camping text) LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
    SELECT s.content,r.camping FROM hpa_rating.request_starters s
        JOIN hpa_rating.access_requests r ON r.id=s.request_id
        WHERE r.status='approved' AND r.guest_id=gid;
$$;
CREATE FUNCTION hpa_rating.clear_approved_starter(gid text)
RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DELETE FROM hpa_rating.request_starters s USING hpa_rating.access_requests r
        WHERE s.request_id=r.id AND r.status='approved' AND r.guest_id=gid;
$$;
REVOKE ALL ON FUNCTION hpa_rating.count_starter_event(text), hpa_rating.submit_starter_request(text,text,text,text,text),
    hpa_rating.approved_starter(text),hpa_rating.clear_approved_starter(text)
    FROM PUBLIC,anon,authenticated,service_role,hpa_rating_admin,hpa_rating_webadmin;
GRANT EXECUTE ON FUNCTION hpa_rating.count_starter_event(text), hpa_rating.submit_starter_request(text,text,text,text,text),
    hpa_rating.approved_starter(text),hpa_rating.clear_approved_starter(text) TO hpa_rating_guest;
