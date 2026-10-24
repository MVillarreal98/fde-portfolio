-- Present on both sides, settled total differs from the recorded amount beyond
-- tolerance. Biggest absolute difference first.
SELECT
    transaction_ref,
    merchant,
    channel,
    ops_amount_cents,
    settlement_total_cents,
    amount_difference_cents
FROM matched
WHERE recon_status = 'amount_mismatch'
ORDER BY abs(amount_difference_cents) DESC, transaction_ref;
