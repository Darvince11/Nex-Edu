-- Run once per cell, in the "postgres" database, as the cell admin.
-- Lets PgBouncer look up SCRAM verifiers without being a superuser.

CREATE ROLE pgbouncer_auth WITH LOGIN PASSWORD :'pgbouncer_auth_password';
CREATE SCHEMA IF NOT EXISTS pgbouncer AUTHORIZATION CURRENT_USER;
REVOKE ALL ON SCHEMA pgbouncer FROM PUBLIC;
GRANT USAGE ON SCHEMA pgbouncer TO pgbouncer_auth;

CREATE OR REPLACE FUNCTION pgbouncer.get_auth(p_usename text)
RETURNS TABLE (usename name, passwd text)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog AS $$
    -- Only school roles (school_*) can log in through PgBouncer; never the admin.
    SELECT usename, passwd FROM pg_catalog.pg_shadow
    WHERE usename = p_usename AND usename LIKE 'school\_%';
$$;

REVOKE ALL ON FUNCTION pgbouncer.get_auth(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pgbouncer.get_auth(text) TO pgbouncer_auth;
