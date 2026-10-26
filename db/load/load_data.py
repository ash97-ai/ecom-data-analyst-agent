"""Load the Olist CSV files into the `ecom` schema in Postgres.

Run from the project root with the virtual environment active:

    python db/load/load_data.py

Before running:
  1. Postgres is up (docker compose up -d).
  2. db/schema/01_tables.sql has been run, so the empty tables exist.
  3. The Olist CSV files are in data/raw/ (or set OLIST_DATA_DIR).
  4. .env contains POSTGRES_ADMIN_USER, POSTGRES_ADMIN_PASSWORD, POSTGRES_DB.
     Optional: POSTGRES_HOST (default localhost), POSTGRES_PORT (default 5432).

Safe to re-run: it empties the tables first, then reloads everything inside one
transaction. If anything fails, nothing is changed.

After loading, run db/schema/02_constraints.sql to add foreign keys and indexes.
"""

import csv
import os
import sys
import time
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("OLIST_DATA_DIR", ROOT / "data" / "raw"))
SCHEMA = "ecom"

# table name -> (csv file name, expected column names)
#
# ORDER MATTERS: tables are loaded in this order, so every "parent" table comes
# before the tables that reference it. This lets you re-run the loader even after
# 02_constraints.sql has added foreign keys.
TABLES = {
    "customers": (
        "olist_customers_dataset.csv",
        ["customer_id", "customer_unique_id", "customer_zip_code_prefix",
         "customer_city", "customer_state"],
    ),
    "products": (
        "olist_products_dataset.csv",
        ["product_id", "product_category_name", "product_name_lenght",
         "product_description_lenght", "product_photos_qty", "product_weight_g",
         "product_length_cm", "product_height_cm", "product_width_cm"],
    ),
    "sellers": (
        "olist_sellers_dataset.csv",
        ["seller_id", "seller_zip_code_prefix", "seller_city", "seller_state"],
    ),
    "orders": (
        "olist_orders_dataset.csv",
        ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
         "order_approved_at", "order_delivered_carrier_date",
         "order_delivered_customer_date", "order_estimated_delivery_date"],
    ),
    "order_items": (
        "olist_order_items_dataset.csv",
        ["order_id", "order_item_id", "product_id", "seller_id",
         "shipping_limit_date", "price", "freight_value"],
    ),
    "order_payments": (
        "olist_order_payments_dataset.csv",
        ["order_id", "payment_sequential", "payment_type",
         "payment_installments", "payment_value"],
    ),
    "order_reviews": (
        "olist_order_reviews_dataset.csv",
        ["review_id", "order_id", "review_score", "review_comment_title",
         "review_comment_message", "review_creation_date",
         "review_answer_timestamp"],
    ),
    "category_translation": (
        "product_category_name_translation.csv",
        ["product_category_name", "product_category_name_english"],
    ),
}


def read_header(path: Path) -> list[str]:
    """Return the CSV header, tolerating a byte-order mark and stray spaces."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [name.strip() for name in next(csv.reader(f))]


def count_csv_records(path: Path) -> int:
    """Count data rows properly, including rows with line breaks inside quotes."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        return sum(1 for _ in reader)


def validate_files() -> dict[str, list[str]]:
    """Check every file exists and has the columns we expect. Return headers."""
    problems = []
    headers = {}
    for table, (filename, expected) in TABLES.items():
        path = DATA_DIR / filename
        if not path.exists():
            problems.append(f"Missing file: {path}")
            continue
        header = read_header(path)
        missing = set(expected) - set(header)
        extra = set(header) - set(expected)
        if missing or extra:
            problems.append(
                f"{filename}: column mismatch. "
                f"Missing from file: {sorted(missing) or 'none'}. "
                f"Unexpected in file: {sorted(extra) or 'none'}."
            )
            continue
        headers[table] = header  # keep the file's own column order for COPY
    if problems:
        print("Cannot start loading:\n")
        for p in problems:
            print(f"  - {p}")
        print(f"\nLooked for CSV files in: {DATA_DIR}")
        sys.exit(1)
    return headers


def connect() -> psycopg.Connection:
    missing = [k for k in ("POSTGRES_ADMIN_USER", "POSTGRES_ADMIN_PASSWORD", "POSTGRES_DB")
               if not os.environ.get(k)]
    if missing:
        print(f"Missing settings in .env: {', '.join(missing)}")
        sys.exit(1)
    return psycopg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_ADMIN_USER"],
        password=os.environ["POSTGRES_ADMIN_PASSWORD"],
    )


def load_table(cur: psycopg.Cursor, table: str, header: list[str]) -> None:
    path = DATA_DIR / TABLES[table][0]
    copy_sql = sql.SQL(
        "COPY {table} ({cols}) FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')"
    ).format(
        table=sql.Identifier(SCHEMA, table),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in header),
    )
    with open(path, "rb") as f, cur.copy(copy_sql) as copy:
        while chunk := f.read(1 << 16):
            copy.write(chunk)


def main() -> None:
    headers = validate_files()
    print(f"Loading {len(TABLES)} tables from {DATA_DIR}\n")

    results = []
    try:
        with connect() as conn:  # commits on success, rolls back on any error
            with conn.cursor() as cur:
                all_tables = sql.SQL(", ").join(
                    sql.Identifier(SCHEMA, t) for t in TABLES
                )
                cur.execute(sql.SQL("TRUNCATE {} ").format(all_tables))

                for table in TABLES:
                    start = time.time()
                    load_table(cur, table, headers[table])
                    cur.execute(
                        sql.SQL("SELECT count(*) FROM {}").format(
                            sql.Identifier(SCHEMA, table)
                        )
                    )
                    in_db = cur.fetchone()[0]
                    in_csv = count_csv_records(DATA_DIR / TABLES[table][0])
                    results.append((table, in_csv, in_db, time.time() - start))
    except (psycopg.errors.UndefinedTable, psycopg.errors.InvalidSchemaName):
        print("The ecom schema or one of its tables does not exist yet.")
        print("Run db/schema/01_tables.sql first, then run this loader again.")
        sys.exit(1)
    except psycopg.errors.IntegrityError as e:
        print("The data broke a database rule (duplicate key or missing parent row).")
        print("Nothing was changed: the whole load was rolled back.\n")
        print(f"{e}\n")
        print("If this is a foreign key error, a row refers to something that is not "
              "in its parent table. Note it as a data trap and, if you cannot fix "
              "the data, remove that foreign key from db/schema/02_constraints.sql.")
        sys.exit(1)
    except psycopg.OperationalError as e:
        print(f"Could not connect to Postgres. Is the container running?\n{e}")
        sys.exit(1)

    print(f"{'table':<24}{'csv rows':>10}{'db rows':>10}{'seconds':>10}  status")
    ok = True
    for table, in_csv, in_db, secs in results:
        status = "OK" if in_csv == in_db else "MISMATCH"
        ok = ok and in_csv == in_db
        print(f"{table:<24}{in_csv:>10}{in_db:>10}{secs:>10.1f}  {status}")

    if not ok:
        print("\nRow counts do not match. Investigate before moving on.")
        sys.exit(1)
    print("\nAll tables loaded. Next: run db/schema/02_constraints.sql")


if __name__ == "__main__":
    main()
