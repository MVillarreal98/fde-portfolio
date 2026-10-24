-- staging.sql — runs first, inside one DuckDB connection.
--
-- Loads both CSVs as text, casts every value defensively and splits the rows
-- into clean temp tables (t_invoices, t_payments) and rejected rows with a
-- reason. Everything downstream only reads the clean tables, so a rejected
-- row can never reach a metric. `__INVOICES_PATH__` and `__PAYMENTS_PATH__`
-- are replaced by the runner with quoted literals; `as_of` is a session
-- variable set before this script runs.

CREATE OR REPLACE TEMP TABLE raw_invoices AS
SELECT row_number() OVER () AS line_no, *
FROM read_csv('__INVOICES_PATH__', header = true, all_varchar = true);

CREATE OR REPLACE TEMP TABLE raw_payments AS
SELECT row_number() OVER () AS line_no, *
FROM read_csv('__PAYMENTS_PATH__', header = true, all_varchar = true);

CREATE OR REPLACE TEMP TABLE parsed_invoices AS
SELECT
    line_no,
    invoice_id,
    trim(invoice_id) AS invoice_id_trim,
    customer_id,
    customer_name,
    TRY_CAST(trim(issued_date) AS DATE) AS issued_date,
    TRY_CAST(trim(due_date) AS DATE) AS due_date,
    TRY_CAST(trim(amount_cents) AS BIGINT) AS amount_cents,
    issued_date AS issued_raw,
    due_date AS due_raw,
    amount_cents AS amount_raw
FROM raw_invoices;

CREATE OR REPLACE TEMP TABLE rejected_invoice_rows AS
SELECT
    'invoice' AS source,
    COALESCE(invoice_id, '') AS reference,
    line_no,
    CASE
        WHEN invoice_id IS NULL OR trim(invoice_id) = '' THEN 'blank_invoice_id'
        WHEN amount_raw IS NULL OR trim(amount_raw) = '' THEN 'blank_amount'
        -- 'unparseable_amount' = the text is not an integer literal: covers
        -- 'abc', decimals ('1500.50' -> TryCast would round to 1501 cents,
        -- a 100x error), exponent and underscore notation ('1e3', '1_000').
        WHEN NOT regexp_full_match(COALESCE(trim(amount_raw), ''), '-?[0-9]+')
            THEN 'unparseable_amount'
        WHEN amount_cents < 0 THEN 'negative_amount'
        WHEN issued_raw IS NULL OR trim(issued_raw) = '' THEN 'blank_issued_date'
        WHEN issued_date IS NULL THEN 'unparseable_issued_date'
        WHEN due_raw IS NULL OR trim(due_raw) = '' THEN 'blank_due_date'
        WHEN due_date IS NULL THEN 'unparseable_due_date'
        WHEN due_date < issued_date THEN 'due_before_issue'
    END AS reason
FROM parsed_invoices
WHERE CASE
        WHEN invoice_id IS NULL OR trim(invoice_id) = '' THEN 'blank_invoice_id'
        WHEN amount_raw IS NULL OR trim(amount_raw) = '' THEN 'blank_amount'
        WHEN NOT regexp_full_match(COALESCE(trim(amount_raw), ''), '-?[0-9]+')
            THEN 'unparseable_amount'
        WHEN amount_cents < 0 THEN 'negative_amount'
        WHEN issued_raw IS NULL OR trim(issued_raw) = '' THEN 'blank_issued_date'
        WHEN issued_date IS NULL THEN 'unparseable_issued_date'
        WHEN due_raw IS NULL OR trim(due_raw) = '' THEN 'blank_due_date'
        WHEN due_date IS NULL THEN 'unparseable_due_date'
        WHEN due_date < issued_date THEN 'due_before_issue'
      END IS NOT NULL;

-- Uniqueness pass: the first occurrence of an invoice_id (by file line)
-- is the real record; later occurrences are duplicates of it (amended or
-- re-entered rows) and go to rejected_rows. The pass only sees rows that
-- passed every field check, so a malformed twin keeps its own row-level
-- reason and cannot disqualify a valid invoice.
CREATE OR REPLACE TEMP TABLE dup_invoice_rows AS
SELECT
    'invoice' AS source,
    invoice_id_trim AS reference,
    line_no,
    'duplicate_invoice_id' AS reason
FROM (
    SELECT
        line_no,
        invoice_id_trim,
        row_number() OVER (PARTITION BY invoice_id_trim ORDER BY line_no)
            AS id_seq
    FROM parsed_invoices p
    WHERE trim(invoice_id) <> ''   -- blank ids already carry their own reason
      AND NOT EXISTS (
          SELECT 1 FROM rejected_invoice_rows r
          WHERE r.source = 'invoice' AND r.line_no = p.line_no
      )
) WHERE id_seq > 1;

INSERT INTO rejected_invoice_rows SELECT * FROM dup_invoice_rows;

CREATE OR REPLACE TEMP TABLE t_invoices AS
SELECT
    invoice_id_trim AS invoice_id,
    trim(customer_id) AS customer_id,
    COALESCE(trim(customer_name), '') AS customer_name,
    issued_date,
    due_date,
    amount_cents
FROM parsed_invoices p
WHERE NOT EXISTS (
    SELECT 1 FROM rejected_invoice_rows r
    WHERE r.source = 'invoice' AND r.line_no = p.line_no
);

CREATE OR REPLACE TEMP TABLE parsed_payments AS
SELECT
    line_no,
    payment_id,
    trim(payment_id) AS payment_id_trim,
    invoice_id,
    trim(invoice_id) AS invoice_id_trim,
    trim(method) AS method,
    TRY_CAST(trim(paid_date) AS DATE) AS paid_date,
    TRY_CAST(trim(amount_cents) AS BIGINT) AS amount_cents,
    paid_date AS paid_raw,
    amount_cents AS amount_raw
FROM raw_payments;

CREATE OR REPLACE TEMP TABLE rejected_payment_rows AS
SELECT
    'payment' AS source,
    COALESCE(payment_id, '') AS reference,
    line_no,
    CASE
        WHEN payment_id IS NULL OR trim(payment_id) = '' THEN 'blank_payment_id'
        WHEN amount_raw IS NULL OR trim(amount_raw) = '' THEN 'blank_amount'
        -- Same integer-literal guard as the invoice side: decimals would be
        -- rounded by the BIGINT cast with no trace.
        WHEN NOT regexp_full_match(COALESCE(trim(amount_raw), ''), '-?[0-9]+')
            THEN 'unparseable_amount'
        WHEN amount_cents < 0 THEN 'negative_amount'
        WHEN invoice_id IS NULL OR trim(invoice_id) = '' THEN 'blank_invoice_ref'
        WHEN paid_raw IS NULL OR trim(paid_raw) = '' THEN 'blank_paid_date'
        WHEN paid_date IS NULL THEN 'unparseable_payment_date'
        WHEN paid_date > getvariable('as_of') THEN 'future_payment'
    END AS reason
FROM parsed_payments
WHERE CASE
        WHEN payment_id IS NULL OR trim(payment_id) = '' THEN 'blank_payment_id'
        WHEN amount_raw IS NULL OR trim(amount_raw) = '' THEN 'blank_amount'
        WHEN NOT regexp_full_match(COALESCE(trim(amount_raw), ''), '-?[0-9]+')
            THEN 'unparseable_amount'
        WHEN amount_cents < 0 THEN 'negative_amount'
        WHEN invoice_id IS NULL OR trim(invoice_id) = '' THEN 'blank_invoice_ref'
        WHEN paid_raw IS NULL OR trim(paid_raw) = '' THEN 'blank_paid_date'
        WHEN paid_date IS NULL THEN 'unparseable_payment_date'
        WHEN paid_date > getvariable('as_of') THEN 'future_payment'
      END IS NOT NULL;

-- Same uniqueness pass for payments: a repeated payment_id (a double
-- entry in the payments file) is rejected after its first occurrence, so
-- an invoice cannot be silently paid in full by a re-loaded payment.
CREATE OR REPLACE TEMP TABLE dup_payment_rows AS
SELECT
    'payment' AS source,
    payment_id_trim AS reference,
    line_no,
    'duplicate_payment_id' AS reason
FROM (
    SELECT
        line_no,
        payment_id_trim,
        row_number() OVER (PARTITION BY payment_id_trim ORDER BY line_no)
            AS id_seq
    FROM parsed_payments p
    WHERE trim(payment_id) <> ''
      AND NOT EXISTS (
          SELECT 1 FROM rejected_payment_rows r
          WHERE r.source = 'payment' AND r.line_no = p.line_no
      )
) WHERE id_seq > 1;

INSERT INTO rejected_payment_rows SELECT * FROM dup_payment_rows;

CREATE OR REPLACE TEMP TABLE t_payments AS
SELECT
    payment_id_trim AS payment_id,
    line_no,
    invoice_id_trim AS invoice_id,
    paid_date,
    amount_cents,
    COALESCE(method, 'UNKNOWN') AS method
FROM parsed_payments p
WHERE NOT EXISTS (
    SELECT 1 FROM rejected_payment_rows r
    WHERE r.source = 'payment' AND r.line_no = p.line_no
);

-- FIFO cash application: payments are applied to their invoice in paid_date
-- order, ties broken by file line_no (earlier in the file wins) and then by
-- payment_id, so application never depends on text ordering of the ID
-- ('PAY-10' vs 'PAY-9'). Each payment is applied only up to what the invoice
-- still owed when it arrived; the rest is unapplied cash and is reported as
-- such.
CREATE OR REPLACE TEMP TABLE t_applied AS
WITH matched AS (
    SELECT
        p.payment_id,
        p.invoice_id,
        p.line_no,
        i.customer_id,
        p.paid_date,
        p.method,
        p.amount_cents AS pay_amt,
        i.amount_cents AS inv_amt
    FROM t_payments p
    JOIN t_invoices i ON p.invoice_id = i.invoice_id
),
ordered AS (
    SELECT
        matched.*,
        SUM(pay_amt) OVER (
            PARTITION BY invoice_id
            ORDER BY paid_date, line_no, payment_id
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cum_paid
    FROM matched
)
SELECT
    payment_id,
    invoice_id,
    customer_id,
    paid_date,
    method,
    pay_amt,
    GREATEST(0, LEAST(inv_amt - (cum_paid - pay_amt), pay_amt)) AS applied_cents
FROM ordered;
