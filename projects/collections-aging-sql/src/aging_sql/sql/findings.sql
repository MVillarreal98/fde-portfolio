-- findings.sql — rows a reviewer must look at, one CSV row per finding.
-- rejected_rows.sql covers rows that could not be parsed or are structurally
-- unusable; this file covers rows that parsed fine but do not make sense.

-- A payment against an invoice that does not exist. Cash on the books without
-- an invoice cannot be aged and cannot be applied.
SELECT
    'orphan_payment' AS code,
    payment_id AS reference,
    'unknown_invoice_id=' || invoice_id AS detail
FROM t_payments p
WHERE NOT EXISTS (
    SELECT 1 FROM t_invoices i WHERE i.invoice_id = p.invoice_id
)

UNION ALL

-- Cash received above the invoice total. The surplus is not a dunning
-- problem and must not be read as outstanding money.
SELECT
    'overpayment' AS code,
    invoice_id AS reference,
    'unapplied_cash_cents=' || CAST(SUM(pay_amt - applied_cents) AS VARCHAR) AS detail
FROM t_applied
WHERE applied_cents < pay_amt
GROUP BY invoice_id
HAVING SUM(pay_amt - applied_cents) > 0

ORDER BY code, reference;
