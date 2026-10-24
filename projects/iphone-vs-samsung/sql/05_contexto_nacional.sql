-- ============================================================
-- 05_CONTEXTO_NACIONAL.SQL
-- StatCounter sólo publica México completo (no baja a ciudad), así que
-- NO es "la realidad de Monterrey": es el marco nacional de uso real
-- contra el cual leer la conversación en la ZM.
-- ============================================================

-- Q0 · Uso real en México: cuota promedio anual de Apple y Samsung
-- (StatCounter mide tráfico web, no unidades vendidas)
SELECT substr(month, 1, 4)                                        AS anio,
       ROUND(AVG(CASE WHEN vendor = 'Apple'   THEN share END), 1) AS apple_pct,
       ROUND(AVG(CASE WHEN vendor = 'Samsung' THEN share END), 1) AS samsung_pct,
       COUNT(DISTINCT month)                                      AS meses
FROM statcounter_month
WHERE substr(month, 1, 4) IN ('2020', '2025')
GROUP BY anio
ORDER BY anio;

-- Q1 · Búsqueda en la ZM vs uso en México, mismo formato: % de iPhone
-- dentro del par iPhone + Samsung. Una brecha grande dice que se BUSCA
-- mucho más iPhone del que se USA (aspiración, comparación de precios,
-- soporte técnico...). Geografías distintas: leer como contexto.
WITH uso AS (
    SELECT substr(month, 1, 4) AS periodo,
           100.0 * SUM(CASE WHEN vendor = 'Apple' THEN share END)
                 / SUM(CASE WHEN vendor IN ('Apple', 'Samsung') THEN share END)
               AS iphone_uso_mx
    FROM statcounter_month
    WHERE substr(month, 1, 4) IN ('2020', '2025')
    GROUP BY periodo
), busqueda AS (
    SELECT periodo,
           SUM(iphone_share_pct * pobtot) / SUM(pobtot) AS iphone_busqueda_zm
    FROM v_localidad
    GROUP BY periodo
)
SELECT b.periodo,
       ROUND(b.iphone_busqueda_zm, 1)                    AS iphone_busqueda_zm,
       ROUND(u.iphone_uso_mx, 1)                         AS iphone_uso_mx,
       ROUND(b.iphone_busqueda_zm - u.iphone_uso_mx, 1)  AS brecha_pp
FROM busqueda b
LEFT JOIN uso u USING (periodo)
ORDER BY b.periodo;
