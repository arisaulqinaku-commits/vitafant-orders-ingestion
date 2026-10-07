-- Net revenue and units sold per product for one month, ranked by revenue.
--
-- To use another month, change the value on the next line (format YYYY-MM).
-- The month is taken from the order date as written in the data (local time,
-- +02:00). substr() is used on purpose: SQLite's strftime() would convert the
-- timestamp to UTC first and could move an order near midnight to another month.
--
-- Money is stored as integer cents, so it is divided by 100 only for display.
-- (All orders in this data are in EUR.)
-- Cancelled orders and shipping lines are already excluded by the ingestion job.

WITH params AS (SELECT '2026-06' AS month)

SELECT
    RANK() OVER (ORDER BY SUM(l.net_revenue_cents) DESC) AS revenue_rank,
    l.sku                                                AS sku,
    MIN(l.product_title)                                 AS product_title,
    SUM(l.quantity)                                      AS units_sold,
    ROUND(SUM(l.net_revenue_cents) / 100.0, 2)           AS net_revenue
FROM order_line_items AS l
CROSS JOIN params AS p
WHERE substr(l.order_created_at, 1, 7) = p.month
GROUP BY l.sku
ORDER BY SUM(l.net_revenue_cents) DESC, l.sku;