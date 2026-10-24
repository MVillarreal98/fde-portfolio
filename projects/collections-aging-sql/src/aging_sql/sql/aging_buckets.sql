-- aging_buckets.sql — one row per open invoice (outstanding > 0).
--
-- The aging bucket comes from the policy due date, not the issue date, and
-- days past due are clamped at 0 for invoices that are not due yet. The
-- balances CTE is repeated in each report file on purpose: one SQL file
-- produces one self-contained artifact.

WITH balances AS (
    SELECT
        i.invoice_id,
        i.customer_id,
        i.customer_name,
        i.issued_date,
        i.due_date,
        i.amount_cents,
        COALESCE(SUM(a.applied_cents), 0) AS paid_cents
    FROM t_invoices i
    LEFT JOIN t_applied a USING (invoice_id)
    GROUP BY ALL
),
aged AS (
    SELECT
        *,
        amount_cents - paid_cents AS outstanding_cents,
        GREATEST(0, date_diff('day', due_date, getvariable('as_of'))) AS days_past_due
    FROM balances
)
SELECT
    invoice_id,
    customer_id,
    customer_name,
    issued_date,
    due_date,
    amount_cents,
    paid_cents,
    outstanding_cents,
    days_past_due,
    CASE
        WHEN days_past_due <= 0 THEN 'current'
        WHEN days_past_due <= 30 THEN '1-30'
        WHEN days_past_due <= 60 THEN '31-60'
        WHEN days_past_due <= 90 THEN '61-90'
        ELSE '91-plus'
    END AS aging_bucket
FROM aged
WHERE outstanding_cents > 0
ORDER BY days_past_due DESC, invoice_id;
