-- The operator can decide a pending request without gaining DELETE on the registry.
CREATE OR REPLACE FUNCTION hpa_rating.erase_refused_request()
RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog
AS $$
BEGIN
    DELETE FROM hpa_rating.access_requests WHERE id = NEW.id AND status = 'declined';
    RETURN NULL;
END;
$$;
REVOKE ALL ON FUNCTION hpa_rating.erase_refused_request() FROM PUBLIC, anon, authenticated, service_role;
DROP TRIGGER IF EXISTS erase_refused_request ON hpa_rating.access_requests;
CREATE TRIGGER erase_refused_request AFTER UPDATE OF status ON hpa_rating.access_requests
    FOR EACH ROW WHEN (OLD.status = 'pending' AND NEW.status = 'declined')
    EXECUTE FUNCTION hpa_rating.erase_refused_request();
DELETE FROM hpa_rating.access_requests WHERE status = 'declined';
