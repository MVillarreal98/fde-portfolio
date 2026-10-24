-- findings.sql — rows a reviewer must look at, one CSV row per finding.
-- rejected_rows.sql covers rows that could not be parsed or are structurally
-- unusable; this file covers rows that parsed fine but do not make sense.

-- A payment against an invoice that does not exist. Cash on the books without
-- an invoice cannot be aged and cannot be applied. When the invoice came in
-- but was rejected at staging (e.g. an unparseable amount), the detail says
-- so instead of claiming it was unknown.
SELECT
    'orphan_payment' AS code,
    payment_id AS reference,
    CASE
        WHEN EXISTS (
            SELECT 1 FROM rejected_invoice_rows r
            WHERE r.source = 'invoice' AND r.reference = p.invoice_id
        )
        THEN 'invoice_rejected_at_staging=' || p.invoice_id
        ELSE 'unknown_invoice_id=' || p.invoice_id
    END AS detail
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
