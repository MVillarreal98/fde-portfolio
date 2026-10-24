-- duplicate_payment_candidates.sql — pairs of payments that look like the same
-- charge paid twice: same customer, same amount, receipt dates within a
-- 7-day window. Deliberately a heuristic, not a verdict: split installments
-- can match it. Candidate pairs go to a reviewer; nothing is reversed
-- automatically. Payments rejected at staging and payments against unknown
-- invoices never reach this file.

WITH applied_payments AS (
    SELECT
        payment_id,
        customer_id,
        paid_date,
        pay_amt AS amount_cents
    FROM t_applied
)
SELECT
    a.payment_id AS payment_id_a,
    b.payment_id AS payment_id_b,
    a.customer_id,
    a.amount_cents,
    a.paid_date AS paid_date_a,
    b.paid_date AS paid_date_b,
    abs(date_diff('day', a.paid_date, b.paid_date)) AS days_apart
FROM applied_payments a
JOIN applied_payments b
    ON a.customer_id = b.customer_id
    AND a.amount_cents = b.amount_cents
    AND a.payment_id < b.payment_id
    AND abs(date_diff('day', a.paid_date, b.paid_date)) <= 7
ORDER BY a.paid_date, payment_id_a, payment_id_b;
