-- One-sided references. Reversed charges that never settled are expected
-- ('cancelled_not_settled') and are not orphans.
SELECT
    transaction_ref,
    merchant,
    channel,
    ops_amount_cents,
    settlement_total_cents,
    CASE
        WHEN recon_status = 'billing_only'
            THEN 'settlement_without_ops_record (possible phantom revenue)'
        WHEN ops_amount_cents < 0
            THEN 'ops_without_settlement (negative amount: refund never settled)'
        ELSE 'ops_without_settlement (possible revenue leakage)'
    END AS discrepancy_type
FROM matched
WHERE recon_status IN ('ops_only', 'billing_only')
ORDER BY transaction_ref;
