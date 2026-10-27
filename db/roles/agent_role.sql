-- 01_agent_role.sql
-- Creates `ecom_agent`, the restricted login the AI agent uses to query the data.
--
-- Run as the ADMIN user, from PowerShell in the project root (NOT in DBeaver:
-- this file uses psql features such as \if and a password variable):
--
--   Get-Content db/roles/01_agent_role.sql | docker compose exec -T db psql -U admin -d olist -v ON_ERROR_STOP=1 -v agent_password=YOUR_PASSWORD
--
-- Use letters and digits only in the password, so PowerShell does not mangle it.
-- Put the same value in .env as AGENT_DB_PASSWORD. Never write it in this file.
--
-- Safe to re-run: it creates the role if missing, then re-applies every setting.
-- Run it again after `drop schema ecom cascade` (the grants live on the schema).
--
-- Layers of protection, from hardest to softest:
--   1. PRIVILEGES: the role is granted SELECT only. It owns nothing, so it cannot
--      insert, update, delete, truncate, or create/drop anything. This is the
--      hard boundary and it cannot be switched off by the role itself.
--   2. READ-ONLY DEFAULT: every transaction starts read-only.
--   3. TIME LIMITS: statement, lock and idle timeouts stop runaway queries.
--   Layers 2 and 3 are DEFAULTS. A connected session can change them with SET,
--   so the agent's SQL tool must ALSO refuse anything but a single SELECT.

\if :{?agent_password}
\else
    \echo 'ERROR: pass the password with  -v agent_password=YOUR_PASSWORD'
    \quit
\endif

-- 1. Create the role (login only, no special powers) -------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ecom_agent') THEN
        CREATE ROLE ecom_agent LOGIN;
    END IF;
END
$$;

ALTER ROLE ecom_agent WITH LOGIN
    NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 10
    PASSWORD :'agent_password';

-- 2. Defaults applied to every session of this role --------------------------
ALTER ROLE ecom_agent SET default_transaction_read_only = on;
ALTER ROLE ecom_agent SET statement_timeout = '10s';
ALTER ROLE ecom_agent SET lock_timeout = '5s';
ALTER ROLE ecom_agent SET idle_in_transaction_session_timeout = '30s';
-- Lets the model write `orders` instead of `ecom.orders`.
ALTER ROLE ecom_agent SET search_path = ecom;

-- 3. Privileges: connect, look inside ecom, SELECT on its tables -------------
GRANT CONNECT ON DATABASE olist TO ecom_agent;

-- Nobody but admin may create temporary tables or objects in public.
REVOKE TEMPORARY ON DATABASE olist FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

GRANT USAGE ON SCHEMA ecom TO ecom_agent;
GRANT SELECT ON ALL TABLES IN SCHEMA ecom TO ecom_agent;

-- Tables that admin creates later (for example when 01_tables.sql is re-run)
-- are automatically readable too.
ALTER DEFAULT PRIVILEGES IN SCHEMA ecom GRANT SELECT ON TABLES TO ecom_agent;

-- Show the result ------------------------------------------------------------
\echo
\echo 'Role created. Privileges on the ecom tables:'
SELECT table_name, string_agg(privilege_type, ', ') AS privileges
FROM information_schema.role_table_grants
WHERE grantee = 'ecom_agent' AND table_schema = 'ecom'
GROUP BY table_name
ORDER BY table_name;