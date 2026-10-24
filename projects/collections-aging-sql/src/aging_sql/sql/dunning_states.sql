-- dunning_states.sql — one row per open invoice (outstanding > 0) with the
-- dunning stage the collection policy requires and the date of the next
-- action. Stages only escalate with days past due; nothing can lower a stage.
-- A D60_collections invoice has passed every stage, so there is no next one
-- (next_action_date is empty).

WITH balances AS (
    SELECT
        i.invoice_id,
        i.customer_id,
        i.due_date,
        i.amount_cents,
        COALESCE(SUM(a.applied_cents), 0) AS paid_cents
    FROM t_invoices i
    LEFT JOIN t_applied a USING (invoice_id)
    GROUP BY ALL
),
aged AS (
    SELECT
        *,
        amount_cents - paid_cents AS outstanding_cents,
        GREATEST(0, date_diff('day', due_date, getvariable('as_of'))) AS days_past_due
    FROM balances
)
SELECT
    invoice_id,
    customer_id,
    days_past_due,
    outstanding_cents,
    CASE
        WHEN days_past_due >= 60 THEN 'D60_collections'
        WHEN days_past_due >= 35 THEN 'D35_final_notice'
        WHEN days_past_due >= 15 THEN 'D15_second_notice'
        WHEN days_past_due >= 3 THEN 'D3_reminder'
        ELSE 'pre_dunning'
    END AS stage,
    CASE
        WHEN days_past_due >= 60 THEN NULL
        WHEN days_past_due >= 35 THEN due_date + 60
        WHEN days_past_due >= 15 THEN due_date + 35
        WHEN days_past_due >= 3 THEN due_date + 15
        ELSE due_date + 3
    END AS next_action_date
FROM aged
WHERE outstanding_cents > 0
ORDER BY days_past_due DESC, invoice_id;
