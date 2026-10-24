-- Ops and billing disagree on currency (or one side mixes currencies), so the
-- amounts are not comparable.
SELECT
    transaction_ref,
    merchant,
    channel,
    ops_currency,
    settlement_currency,
    ops_amount_cents,
    settlement_total_cents
FROM matched
WHERE recon_status = 'currency_mismatch'
ORDER BY transaction_ref;
