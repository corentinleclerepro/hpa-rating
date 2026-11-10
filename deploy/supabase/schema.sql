-- Isolated application in the existing project. PostgREST does not expose this schema.
CREATE SCHEMA hpa_rating;
REVOKE ALL ON SCHEMA hpa_rating FROM PUBLIC, anon, authenticated;
CREATE ROLE hpa_rating_guest NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE ROLE hpa_rating_admin NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
GRANT USAGE ON SCHEMA hpa_rating TO hpa_rating_guest, hpa_rating_admin;
ALTER ROLE hpa_rating_guest SET search_path = hpa_rating, pg_catalog;
ALTER ROLE hpa_rating_admin SET search_path = hpa_rating, pg_catalog;

CREATE TABLE hpa_rating.guests (
    id text PRIMARY KEY, label text NOT NULL, digest text UNIQUE,
    version integer NOT NULL DEFAULT 1, created_at text NOT NULL, last_seen text,
    revoked integer NOT NULL DEFAULT 0, code_used integer NOT NULL DEFAULT 0
);
CREATE TABLE hpa_rating.login_limits (bucket text PRIMARY KEY, since bigint NOT NULL, failures integer NOT NULL);
CREATE TABLE hpa_rating.django_session (session_key varchar(40) PRIMARY KEY, session_data text NOT NULL, expire_date timestamptz NOT NULL);
CREATE INDEX ON hpa_rating.django_session(expire_date);
CREATE TABLE hpa_rating.audits (
    id text PRIMARY KEY, owner_id text NOT NULL REFERENCES hpa_rating.guests(id), name text NOT NULL,
    type text NOT NULL DEFAULT 'camping', mention text NOT NULL DEFAULT 'tourisme', target_stars integer NOT NULL DEFAULT 3,
    profile text NOT NULL DEFAULT '{}', reference_version text NOT NULL, created_at text NOT NULL, updated_at text NOT NULL,
    resume_criterion text, profile_confirmed integer NOT NULL DEFAULT 0, proofs_reviewed integer NOT NULL DEFAULT 0
);
CREATE INDEX ON hpa_rating.audits(owner_id, updated_at);
CREATE TABLE hpa_rating.items (
    audit_id text NOT NULL REFERENCES hpa_rating.audits(id) ON DELETE CASCADE, criterion_id text NOT NULL,
    status text NOT NULL DEFAULT 'TODO', notes text NOT NULL DEFAULT '', validated_by text NOT NULL DEFAULT '',
    validated_at text, updated_at text NOT NULL, awarded_points integer, validated_stars integer,
    PRIMARY KEY(audit_id, criterion_id)
);
CREATE TABLE hpa_rating.evidences (
    id text PRIMARY KEY, audit_id text NOT NULL REFERENCES hpa_rating.audits(id) ON DELETE CASCADE,
    criterion_id text NOT NULL, kind text NOT NULL, filename text NOT NULL, original_name text NOT NULL DEFAULT '',
    url text NOT NULL DEFAULT '', caption text NOT NULL DEFAULT '', stale integer NOT NULL DEFAULT 0, created_at text NOT NULL,
    object_key text CHECK (object_key ~ '^[0-9a-f]{32}$')
);
CREATE INDEX ON hpa_rating.evidences(audit_id, criterion_id);
CREATE INDEX ON hpa_rating.evidences(object_key) WHERE object_key IS NOT NULL;
CREATE TABLE hpa_rating.activity (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY, audit_id text NOT NULL REFERENCES hpa_rating.audits(id) ON DELETE CASCADE,
    created_at text NOT NULL, message text NOT NULL, criterion_id text, step text NOT NULL
);
CREATE INDEX ON hpa_rating.activity(audit_id, id DESC);
CREATE TABLE hpa_rating.pending_files (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'), audit_id text NOT NULL REFERENCES hpa_rating.audits(id) ON DELETE CASCADE,
    criterion_id text NOT NULL, owner_id text NOT NULL REFERENCES hpa_rating.guests(id),
    original_name text NOT NULL, size_bytes bigint NOT NULL CHECK (size_bytes BETWEEN 0 AND 67108864), caption text NOT NULL DEFAULT '',
    expires_at timestamptz NOT NULL DEFAULT now() + interval '1 hour',
    evidence_id text REFERENCES hpa_rating.evidences(id) ON DELETE CASCADE
);
CREATE INDEX ON hpa_rating.pending_files(expires_at);

CREATE TABLE hpa_rating.file_blobs (
    id text PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes BETWEEN 0 AND 67108864)
);
CREATE TABLE hpa_rating.file_chunks (
    file_id text NOT NULL REFERENCES hpa_rating.file_blobs(id) ON DELETE CASCADE,
    part integer NOT NULL CHECK (part >= 0 AND part < 64),
    content bytea NOT NULL CHECK (octet_length(content) BETWEEN 1 AND 1048576),
    PRIMARY KEY (file_id, part)
);
ALTER TABLE hpa_rating.evidences ADD FOREIGN KEY (object_key) REFERENCES hpa_rating.file_blobs(id);
ALTER TABLE hpa_rating.pending_files ADD FOREIGN KEY (id) REFERENCES hpa_rating.file_blobs(id);
REVOKE ALL ON hpa_rating.file_blobs,hpa_rating.file_chunks FROM PUBLIC,anon,authenticated,service_role,hpa_rating_admin;
GRANT SELECT,INSERT,DELETE ON hpa_rating.file_blobs,hpa_rating.file_chunks TO hpa_rating_guest;
CREATE FUNCTION hpa_rating.remove_unused_file() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
DECLARE file_id text;
BEGIN
    IF TG_TABLE_NAME='evidences' THEN file_id := OLD.object_key; ELSE file_id := OLD.id; END IF;
    IF file_id IS NOT NULL THEN
        DELETE FROM hpa_rating.file_blobs b WHERE b.id=file_id
        AND NOT EXISTS (SELECT 1 FROM hpa_rating.evidences WHERE object_key=b.id)
        AND NOT EXISTS (SELECT 1 FROM hpa_rating.pending_files WHERE id=b.id);
    END IF;
    RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION hpa_rating.remove_unused_file() FROM PUBLIC,anon,authenticated,service_role;
CREATE TRIGGER remove_unlinked_file AFTER DELETE ON hpa_rating.evidences
FOR EACH ROW EXECUTE FUNCTION hpa_rating.remove_unused_file();
CREATE TRIGGER remove_aborted_upload AFTER DELETE ON hpa_rating.pending_files
FOR EACH ROW EXECUTE FUNCTION hpa_rating.remove_unused_file();

REVOKE ALL ON ALL TABLES IN SCHEMA hpa_rating FROM PUBLIC,anon,authenticated,service_role;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA hpa_rating FROM PUBLIC,anon,authenticated,service_role;
GRANT SELECT ON hpa_rating.guests TO hpa_rating_guest,hpa_rating_admin;
GRANT UPDATE(last_seen,code_used) ON hpa_rating.guests TO hpa_rating_guest;
GRANT INSERT,UPDATE ON hpa_rating.guests TO hpa_rating_admin;
GRANT SELECT,INSERT,UPDATE,DELETE ON hpa_rating.audits,hpa_rating.items,hpa_rating.evidences,hpa_rating.activity,
    hpa_rating.pending_files,hpa_rating.login_limits,hpa_rating.django_session TO hpa_rating_guest;
GRANT SELECT,INSERT,DELETE ON hpa_rating.file_blobs,hpa_rating.file_chunks TO hpa_rating_guest;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA hpa_rating TO hpa_rating_guest;
