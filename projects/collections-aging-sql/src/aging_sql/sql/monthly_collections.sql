-- monthly_collections.sql — cash on the books, not promises. Only payments
-- that were applied to a known invoice count; the running total and the
-- month-over-month delta reset per method. The first month of a method has no
-- prior month, so delta_prior_month_cents is empty there.

WITH applied AS (
    SELECT
        paid_date,
        method,
        pay_amt,
        applied_cents
    FROM t_applied
)
SELECT
    CAST(date_trunc('month', paid_date) AS DATE) AS month,
    method,
    SUM(pay_amt) AS gross_cents,
    SUM(applied_cents) AS applied_cents,
    SUM(pay_amt - applied_cents) AS unapplied_cents,
    SUM(pay_amt) - LAG(SUM(pay_amt)) OVER (
        PARTITION BY method
        ORDER BY CAST(date_trunc('month', paid_date) AS DATE)
    ) AS delta_prior_month_cents,
    SUM(SUM(pay_amt)) OVER (
        PARTITION BY method
        ORDER BY CAST(date_trunc('month', paid_date) AS DATE)
    ) AS running_gross_cents
FROM applied
GROUP BY 1, 2
ORDER BY month, method;
