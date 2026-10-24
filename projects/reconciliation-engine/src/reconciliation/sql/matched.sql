-- Reconciliation core (DuckDB). Mirrors matching.py.
--
-- Aggregates each side per transaction reference, FULL OUTER JOINs the two
-- aggregates (one row per reference on each side, so the join is one-to-one
-- and totals are conserved) and gives every reference exactly ONE status.
--
-- Inputs : ops(row_number, transaction_id, merchant, channel, currency, status,
--              recorded_at, amount_cents)
--          billing(row_number, statement_id, transaction_ref, currency, amount_cents)
-- Params : SET VARIABLE tolerance_cents = 1;
--          SET VARIABLE void_statuses = ['canceled', 'cancelled', 'refunded', 'void'];
CREATE OR REPLACE TEMP TABLE matched AS
WITH ops_agg AS (
    SELECT
        transaction_id                     AS transaction_ref,
        arg_min(merchant, row_number)      AS merchant,        -- first row in file order
        arg_min(channel, row_number)       AS channel,
        arg_min(status, row_number)        AS status,
        min(currency)                      AS ops_currency_min,
        max(currency)                      AS ops_currency_max,
        count(*)                           AS ops_rows,
        sum(amount_cents)::BIGINT          AS ops_amount_cents
    FROM ops
    GROUP BY transaction_id
),
billing_rows AS (
    SELECT
        *,
        -- entries sharing reference AND amount: a processor retry repeats the amount
        count(*) OVER (PARTITION BY transaction_ref, amount_cents) AS amount_repeat
    FROM billing
),
billing_agg AS (
    SELECT
        transaction_ref,
        min(currency)                                      AS settlement_currency_min,
        max(currency)                                      AS settlement_currency_max,
        count(*)                                           AS settlement_count,
        sum(amount_cents)::BIGINT                          AS settlement_total_cents,
        max(amount_repeat)                                 AS max_repeat,
        string_agg(statement_id, ', ' ORDER BY row_number) AS statement_ids
    FROM billing_rows
    GROUP BY transaction_ref
),
joined AS (
    SELECT
        coalesce(o.transaction_ref, b.transaction_ref)     AS transaction_ref,
        o.merchant,
        o.channel,
        o.status,
        o.ops_currency_min,
        o.ops_currency_max,
        b.settlement_currency_min,
        b.settlement_currency_max,
        o.transaction_ref IS NOT NULL                      AS has_ops,
        b.transaction_ref IS NOT NULL                      AS has_billing,
        coalesce(o.ops_rows, 0)                            AS ops_rows,
        coalesce(o.ops_amount_cents, 0)                    AS ops_amount_cents,
        coalesce(b.settlement_count, 0)                    AS settlement_count,
        coalesce(b.settlement_total_cents, 0)              AS settlement_total_cents,
        coalesce(b.max_repeat, 0)                          AS max_repeat,
        b.statement_ids
    FROM ops_agg AS o
    FULL OUTER JOIN billing_agg AS b
        ON o.transaction_ref = b.transaction_ref
),
measured AS (
    SELECT
        *,
        settlement_total_cents - ops_amount_cents AS amount_difference_cents,
        coalesce(list_contains(getvariable('void_statuses'), status), false) AS is_void,
        abs(settlement_total_cents - ops_amount_cents) > getvariable('tolerance_cents') AS is_off
    FROM joined
)
SELECT
    transaction_ref,
    merchant,
    channel,
    status,
    CASE WHEN has_ops THEN
        CASE WHEN ops_currency_min = ops_currency_max THEN ops_currency_min
             ELSE ops_currency_min || '/' || ops_currency_max END
    END AS ops_currency,
    CASE WHEN has_billing THEN
        CASE WHEN settlement_currency_min = settlement_currency_max THEN settlement_currency_min
             ELSE settlement_currency_min || '/' || settlement_currency_max END
    END AS settlement_currency,
    has_ops,
    has_billing,
    ops_rows,
    ops_amount_cents,
    settlement_count,
    settlement_total_cents,
    amount_difference_cents,
    max_repeat,
    statement_ids,
    -- First matching branch wins; keep the order in sync with matching.classify.
    CASE
        WHEN NOT has_billing AND is_void THEN 'cancelled_not_settled'
        WHEN NOT has_billing THEN 'ops_only'
        WHEN NOT has_ops THEN 'billing_only'
        WHEN ops_currency_min <> ops_currency_max
          OR settlement_currency_min <> settlement_currency_max
          OR ops_currency_min <> settlement_currency_min THEN 'currency_mismatch'
        WHEN is_void AND abs(settlement_total_cents) > getvariable('tolerance_cents')
            THEN 'settled_but_cancelled'
        WHEN is_void THEN 'matched'            -- reversed in the settlement file: nets to zero
        WHEN is_off AND max_repeat > 1 THEN 'duplicate_settlement'
        WHEN is_off THEN 'amount_mismatch'
        ELSE 'matched'
    END AS recon_status
FROM measured;
