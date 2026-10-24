-- Refunded / cancelled / void in ops, yet its settlements do not net to zero.
SELECT
    transaction_ref,
    merchant,
    channel,
    status,
    ops_amount_cents,
    settlement_total_cents,
    statement_ids
FROM matched
WHERE recon_status = 'settled_but_cancelled'
ORDER BY transaction_ref;
