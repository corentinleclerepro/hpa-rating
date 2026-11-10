-- Dedicated HTTPS operator. Django migrations run once inside its own schema.
CREATE ROLE hpa_rating_webadmin NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS;
CREATE SCHEMA hpa_rating_staff;
REVOKE ALL ON SCHEMA hpa_rating_staff FROM PUBLIC,anon,authenticated,service_role,hpa_rating_guest,hpa_rating_admin;
GRANT USAGE,CREATE ON SCHEMA hpa_rating_staff TO hpa_rating_webadmin;
GRANT USAGE ON SCHEMA hpa_rating TO hpa_rating_webadmin;
ALTER ROLE hpa_rating_webadmin SET search_path=hpa_rating_staff,hpa_rating,pg_catalog;
GRANT SELECT,INSERT,UPDATE ON hpa_rating.guests TO hpa_rating_webadmin;
GRANT SELECT,UPDATE(status,decided_at,guest_id) ON hpa_rating.access_requests TO hpa_rating_webadmin;

CREATE TABLE hpa_rating_staff.login_limits (bucket text PRIMARY KEY, since bigint NOT NULL, failures integer NOT NULL);
CREATE TABLE hpa_rating_staff.local_setup (id integer PRIMARY KEY CHECK (id=1), digest text NOT NULL, expires bigint NOT NULL);
CREATE TABLE hpa_rating_staff.recovery_codes (digest text PRIMARY KEY, user_id integer NOT NULL);
REVOKE ALL ON ALL TABLES IN SCHEMA hpa_rating_staff FROM PUBLIC,anon,authenticated,service_role,hpa_rating_guest,hpa_rating_admin;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA hpa_rating_staff TO hpa_rating_webadmin;
