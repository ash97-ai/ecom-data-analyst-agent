"""Proves the `ecom_agent` role can read the data and nothing else.

Run from the project root with the virtual environment active:

    python -m pytest tests/test_agent_role.py -v

Needs Postgres running, the data loaded, db/roles/01_agent_role.sql applied, and
these values in .env:

    AGENT_DB_PASSWORD=the password you passed to 01_agent_role.sql
    # optional: AGENT_DB_USER (default ecom_agent), POSTGRES_HOST, POSTGRES_PORT

Every test connects as the AGENT, never as admin. If any "must fail" test ever
starts passing, the role is too powerful: fix it before the agent touches it.
"""

import os
from pathlib import Path

import psycopg
import pytest
from dotenv import load_dotenv
from psycopg import errors

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

DENIED = (errors.InsufficientPrivilege, errors.ReadOnlySqlTransaction)


def _connect():
    password = os.environ.get("AGENT_DB_PASSWORD")
    if not password:
        pytest.skip("AGENT_DB_PASSWORD is not set in .env")
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "olist"),
        user=os.environ.get("AGENT_DB_USER", "ecom_agent"),
        password=password,
    )


@pytest.fixture
def conn():
    c = _connect()
    yield c
    c.rollback()
    c.close()


# --- What the agent SHOULD be able to do -------------------------------------

def test_can_read_every_table(conn):
    for table in ["customers", "orders", "order_items", "order_payments",
                  "order_reviews", "products", "sellers", "category_translation"]:
        n = conn.execute(f"SELECT count(*) FROM ecom.{table}").fetchone()[0]
        assert n > 0, f"{table} is empty or unreadable"


def test_schema_prefix_is_optional(conn):
    # search_path is set to ecom, so the model can write plain table names.
    assert conn.execute("SELECT count(*) FROM orders").fetchone()[0] > 0


def test_can_read_the_catalog_to_discover_the_schema(conn):
    cols = conn.execute(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'ecom'"
    ).fetchone()[0]
    assert cols > 20


def test_defaults_are_set(conn):
    assert conn.execute("SHOW default_transaction_read_only").fetchone()[0] == "on"
    assert conn.execute("SHOW statement_timeout").fetchone()[0] == "10s"
    assert conn.execute("SHOW search_path").fetchone()[0] == "ecom"


# --- What the agent must NOT be able to do ------------------------------------

@pytest.mark.parametrize("statement", [
    "INSERT INTO ecom.sellers (seller_id) VALUES ('x')",
    "UPDATE ecom.orders SET order_status = 'hacked'",
    "DELETE FROM ecom.orders",
    "TRUNCATE ecom.orders",
    "DROP TABLE ecom.orders",
    "ALTER TABLE ecom.orders ADD COLUMN evil text",
    "CREATE TABLE ecom.evil (id int)",
    "CREATE TABLE public.evil (id int)",
    "CREATE TEMP TABLE evil (id int)",
    "CREATE SCHEMA evil",
    "DROP SCHEMA ecom CASCADE",
    "CREATE ROLE evil LOGIN",
    "ALTER ROLE ecom_agent SUPERUSER",
])
def test_writes_and_ddl_are_blocked(conn, statement):
    with pytest.raises(errors.Error):
        conn.execute(statement)


@pytest.mark.parametrize("statement", [
    "INSERT INTO ecom.sellers (seller_id) VALUES ('x')",
    "UPDATE ecom.orders SET order_status = 'hacked'",
    "DELETE FROM ecom.orders",
    "TRUNCATE ecom.orders",
])
def test_privileges_hold_even_if_read_only_is_switched_off(conn, statement):
    """The read-only default is only a default. Prove the grants are the real wall."""
    conn.execute("SET TRANSACTION READ WRITE")
    with pytest.raises(errors.InsufficientPrivilege):
        conn.execute(statement)


def test_cannot_read_password_hashes(conn):
    with pytest.raises(errors.InsufficientPrivilege):
        conn.execute("SELECT * FROM pg_authid")


@pytest.mark.parametrize("statement", [
    "COPY (SELECT 1) TO PROGRAM 'id'",
    "SELECT pg_read_file('/etc/passwd')",
    "SELECT pg_ls_dir('/')",
])
def test_cannot_reach_the_server_machine(conn, statement):
    with pytest.raises(errors.InsufficientPrivilege):
        conn.execute(statement)


def test_runaway_query_is_stopped_by_the_timeout(conn):
    # statement_timeout is 10s, so a 30s sleep must be cancelled. Takes ~10s.
    with pytest.raises(errors.QueryCanceled):
        conn.execute("SELECT pg_sleep(30)")


def test_cannot_log_in_with_a_wrong_password():
    with pytest.raises(psycopg.OperationalError):
        psycopg.connect(
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            dbname=os.environ.get("POSTGRES_DB", "olist"),
            user=os.environ.get("AGENT_DB_USER", "ecom_agent"),
            password="definitely-not-the-password",
        )