-- 02_constraints.sql
-- Run AFTER db/load/load_data.py has loaded the data.
-- Adds foreign keys, indexes, and refreshes planner statistics.
--
-- If a foreign key fails, Postgres reports that some rows have no matching parent.
-- Do not force it through. Leave that key out, and write the finding in your
-- README "data traps" list (for example: "order_items has product_ids missing
-- from products"). That is useful interview material.
--
-- Deliberately NOT created: products.product_category_name -> category_translation,
-- because some product categories have no English translation row.
--
-- In DBeaver, if one statement fails, comment it out and run the rest.

-- Foreign keys -------------------------------------------------------------
ALTER TABLE ecom.orders
    ADD CONSTRAINT fk_orders_customer
    FOREIGN KEY (customer_id) REFERENCES ecom.customers (customer_id);

ALTER TABLE ecom.order_items
    ADD CONSTRAINT fk_items_order
    FOREIGN KEY (order_id) REFERENCES ecom.orders (order_id);

ALTER TABLE ecom.order_items
    ADD CONSTRAINT fk_items_product
    FOREIGN KEY (product_id) REFERENCES ecom.products (product_id);

ALTER TABLE ecom.order_items
    ADD CONSTRAINT fk_items_seller
    FOREIGN KEY (seller_id) REFERENCES ecom.sellers (seller_id);

ALTER TABLE ecom.order_payments
    ADD CONSTRAINT fk_payments_order
    FOREIGN KEY (order_id) REFERENCES ecom.orders (order_id);

ALTER TABLE ecom.order_reviews
    ADD CONSTRAINT fk_reviews_order
    FOREIGN KEY (order_id) REFERENCES ecom.orders (order_id);

-- Indexes for the joins and filters the agent will use most -----------------
CREATE INDEX idx_orders_customer         ON ecom.orders (customer_id);
CREATE INDEX idx_orders_status           ON ecom.orders (order_status);
CREATE INDEX idx_orders_purchase_ts      ON ecom.orders (order_purchase_timestamp);
CREATE INDEX idx_items_product           ON ecom.order_items (product_id);
CREATE INDEX idx_items_seller            ON ecom.order_items (seller_id);
CREATE INDEX idx_reviews_order           ON ecom.order_reviews (order_id);
CREATE INDEX idx_customers_unique        ON ecom.customers (customer_unique_id);
CREATE INDEX idx_products_category       ON ecom.products (product_category_name);

-- Refresh statistics so query plans are good -------------------------------
ANALYZE ecom.customers;
ANALYZE ecom.orders;
ANALYZE ecom.order_items;
ANALYZE ecom.order_payments;
ANALYZE ecom.order_reviews;
ANALYZE ecom.products;
ANALYZE ecom.sellers;
ANALYZE ecom.category_translation;
