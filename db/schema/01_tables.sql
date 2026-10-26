-- 01_tables.sql
-- Creates the `ecom` schema and the eight Olist tables.
--
-- Run as the admin user, either:
--   * DBeaver: open this file, then "Execute script" (Alt+X), or
--   * Terminal: docker compose exec -T db psql -U admin -d olist < db/schema/01_tables.sql
--
-- Notes on design choices:
--   * Foreign keys and indexes are NOT created here. They live in 02_constraints.sql
--     and are added after loading, so the load order never matters and any data
--     problem shows up as a clear error you can write down as a "data trap".
--   * Zip codes are text so leading zeros are kept.
--   * Money columns are numeric, never float, to avoid rounding drift.
--   * Timestamps are real timestamps. Many delivery dates are legitimately NULL
--     (canceled or unfinished orders).
--   * The product measurement columns are numeric because the CSV stores them as
--     "40.0", which an integer column would reject.
--   * Two column names keep the original misspelling ("lenght") to match the CSV.
--   * order_reviews has no primary key: review_id repeats in the real data.

CREATE SCHEMA IF NOT EXISTS ecom;

-- Safe to re-run: drops and recreates everything in the ecom schema's tables.
DROP TABLE IF EXISTS
    ecom.order_reviews,
    ecom.order_payments,
    ecom.order_items,
    ecom.orders,
    ecom.customers,
    ecom.products,
    ecom.sellers,
    ecom.category_translationx
CASCADE;

CREATE TABLE ecom.customers (
    customer_id               text PRIMARY KEY,
    customer_unique_id        text,
    customer_zip_code_prefix  text,
    customer_city             text,
    customer_state            text
);

CREATE TABLE ecom.orders (
    order_id                       text PRIMARY KEY,
    customer_id                    text,
    order_status                   text,
    order_purchase_timestamp       timestamp,
    order_approved_at              timestamp,
    order_delivered_carrier_date   timestamp,
    order_delivered_customer_date  timestamp,
    order_estimated_delivery_date  timestamp
);

CREATE TABLE ecom.order_items (
    order_id             text,
    order_item_id        integer,
    product_id           text,
    seller_id            text,
    shipping_limit_date  timestamp,
    price                numeric(10, 2),
    freight_value        numeric(10, 2),
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE ecom.order_payments (
    order_id              text,
    payment_sequential    integer,
    payment_type          text,
    payment_installments  integer,
    payment_value         numeric(10, 2),
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE ecom.order_reviews (
    review_id                text,
    order_id                 text,
    review_score             integer,
    review_comment_title     text,
    review_comment_message   text,
    review_creation_date     timestamp,
    review_answer_timestamp  timestamp
);

CREATE TABLE ecom.products (
    product_id                   text PRIMARY KEY,
    product_category_name        text,
    product_name_lenght          numeric,
    product_description_lenght   numeric,
    product_photos_qty           numeric,
    product_weight_g             numeric,
    product_length_cm            numeric,
    product_height_cm            numeric,
    product_width_cm             numeric
);

CREATE TABLE ecom.sellers (
    seller_id                text PRIMARY KEY,
    seller_zip_code_prefix   text,
    seller_city              text,
    seller_state             text
);

CREATE TABLE ecom.category_translation (
    product_category_name          text PRIMARY KEY,
    product_category_name_english  text
);
