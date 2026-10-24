-- Same amount settled more than once for a reference, pushing the total off
-- the recorded charge (processor retry). A split that adds up is 'matched'.
SELECT
    transaction_ref,
    merchant,
    channel,
    ops_amount_cents,
    settlement_total_cents,
    amount_difference_cents,
    settlement_count,
    statement_ids
FROM matched
WHERE recon_status = 'duplicate_settlement'
ORDER BY transaction_ref;
