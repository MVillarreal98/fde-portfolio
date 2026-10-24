-- ============================================================
-- 04_CAMBIO_2020_2025.SQL
-- ¿Qué cambió en 5 años? Sólo localidades con dato en ambos años
-- (v_localidad_cambio). delta_pp > 0 = iPhone ganó terreno a Galaxy.
-- ============================================================

-- Q0 · Resumen: ¿la ZM se movió hacia iPhone o hacia Galaxy?
SELECT COUNT(*)                                             AS localidades,
       ROUND(SUM(share_2020 * pobtot) / SUM(pobtot), 1)     AS share_2020_zm,
       ROUND(SUM(share_2025 * pobtot) / SUM(pobtot), 1)     AS share_2025_zm,
       ROUND(SUM(delta_pp * pobtot) / SUM(pobtot), 1)       AS delta_zm_pp,
       SUM(delta_pp > 0)                                    AS subieron,
       SUM(delta_pp < 0)                                    AS bajaron,
       SUM(delta_pp = 0)                                    AS igual
FROM v_localidad_cambio;

-- Q1 · Localidades que más se movieron (en ambos sentidos)
SELECT nom_mun, nom_loc, share_2020, share_2025, delta_pp,
       RANK() OVER (ORDER BY delta_pp DESC) AS rank_hacia_iphone
FROM v_localidad_cambio
ORDER BY delta_pp DESC;

-- Q2 · Cambio por municipio, ponderado por población
SELECT nom_mun,
       COUNT(*)                                          AS localidades,
       ROUND(SUM(share_2020 * pobtot) / SUM(pobtot), 1)  AS share_2020,
       ROUND(SUM(share_2025 * pobtot) / SUM(pobtot), 1)  AS share_2025,
       ROUND(SUM(delta_pp * pobtot) / SUM(pobtot), 1)    AS delta_pp
FROM v_localidad_cambio
GROUP BY mun
ORDER BY delta_pp DESC;

-- Q3 ⭐ · ¿La brecha socioeconómica se abrió o se cerró?
-- Se parten las localidades en tercios por % de viviendas con internet
-- (Censo 2020) y se compara el cambio de cada tercio. Si el tercio bajo
-- sube más que el alto, el iPhone se está "popularizando".
WITH t AS (
    SELECT *, NTILE(3) OVER (ORDER BY pct_viv_internet) AS tercio
    FROM v_localidad_cambio
    WHERE pct_viv_internet IS NOT NULL
)
SELECT CASE tercio WHEN 1 THEN '1 · menos internet'
                   WHEN 2 THEN '2 · medio'
                   ELSE        '3 · más internet' END   AS tercio_internet,
       COUNT(*)                                       AS localidades,
       ROUND(MIN(pct_viv_internet), 1) || ' - '
         || ROUND(MAX(pct_viv_internet), 1)           AS rango_pct_internet,
       ROUND(AVG(share_2020), 1)                      AS share_2020,
       ROUND(AVG(share_2025), 1)                      AS share_2025,
       ROUND(AVG(delta_pp), 1)                        AS delta_pp
FROM t
GROUP BY tercio
ORDER BY tercio;

-- Q4 · Cobertura: localidades que Trends sólo reporta en uno de los dos
-- años (volumen insuficiente en el otro). No entran a Q0-Q3: documentarlo
SELECT l.periodo AS solo_en, l.nom_mun, l.nom_loc, l.iphone_share_pct
FROM v_localidad l
WHERE NOT EXISTS (
    SELECT 1 FROM v_localidad o
    WHERE o.mun = l.mun AND o.loc = l.loc AND o.periodo <> l.periodo
)
ORDER BY l.periodo, l.nom_mun, l.nom_loc;
