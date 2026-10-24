-- rejected_rows.sql — every input row the pipeline could not use, with the
-- reason. One row per rejected input row, never aggregated away.

SELECT
    source,
    reference,
    line_no,
    reason
FROM rejected_invoice_rows
UNION ALL
SELECT
    source,
    reference,
    line_no,
    reason
FROM rejected_payment_rows
ORDER BY source, line_no;
