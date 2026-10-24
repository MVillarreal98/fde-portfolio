-- The same transaction_id recorded more than once in the ops ledger. Matching
-- sums the rows (totals stay right); this lists them to fix at the source.
SELECT
    transaction_id,
    count(*)                                                          AS occurrences,
    sum(amount_cents)::BIGINT                                         AS ops_amount_total_cents,
    string_agg(CAST(row_number AS VARCHAR), ', ' ORDER BY row_number) AS row_numbers
FROM ops
GROUP BY transaction_id
HAVING count(*) > 1
ORDER BY transaction_id;
