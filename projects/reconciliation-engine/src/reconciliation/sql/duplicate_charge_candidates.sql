-- Repeated captures that look like one payment recorded twice (gaps-and-islands).
--
-- Captures with the same merchant, channel and amount form a group when each
-- one is recorded within window_minutes of the previous one. The group is
-- reported only if it has fewer settled captures than captures: a double
-- capture in the ledger settles once, two real payments settle twice.
-- Params : SET VARIABLE window_minutes = 10;
WITH captures AS (
    SELECT
        o.row_number,
        o.transaction_id,
        o.merchant,
        o.channel,
        o.amount_cents,
        o.recorded_at,
        o.transaction_id IN (SELECT transaction_ref FROM billing) AS settled
    FROM ops AS o
    WHERE o.recorded_at IS NOT NULL
),
gaps AS (
    SELECT
        *,
        CASE
            WHEN lag(recorded_at) OVER w IS NULL THEN 1
            WHEN recorded_at - lag(recorded_at) OVER w > to_minutes(getvariable('window_minutes'))
                THEN 1
            ELSE 0
        END AS starts_group
    FROM captures
    WINDOW w AS (PARTITION BY merchant, channel, amount_cents ORDER BY recorded_at, row_number)
),
grouped AS (
    SELECT
        *,
        sum(starts_group) OVER (
            PARTITION BY merchant, channel, amount_cents
            ORDER BY recorded_at, row_number
            ROWS UNBOUNDED PRECEDING
        ) AS group_no
    FROM gaps
)
SELECT
    merchant,
    channel,
    amount_cents,
    count(*)                                                          AS occurrences,
    sum(settled::INTEGER)::BIGINT                                     AS settled_count,
    string_agg(transaction_id, ', ' ORDER BY recorded_at, row_number) AS transaction_ids,
    min(recorded_at)                                                  AS first_recorded_at,
    max(recorded_at)                                                  AS last_recorded_at
FROM grouped
GROUP BY merchant, channel, amount_cents, group_no
HAVING count(*) >= 2 AND sum(settled::INTEGER) < count(*)
ORDER BY merchant, channel, amount_cents, first_recorded_at;
