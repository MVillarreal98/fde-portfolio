-- ============================================================
-- 03_POR_LOCALIDAD.SQL
-- Foto de cada año: ¿dónde de la ZM de Monterrey se busca más iPhone
-- que Galaxy? Y ¿coincide con el nivel socioeconómico (Censo 2020)?
-- Base: v_localidad (una fila por localidad y año).
-- ============================================================

-- Q0 · Resumen ejecutivo por año. El promedio ponderado por población
-- evita que una colonia chica pese lo mismo que Monterrey
SELECT periodo,
       COUNT(*)                                            AS localidades,
       SUM(pobtot)                                         AS poblacion_cubierta,
       ROUND(SUM(iphone_share_pct * pobtot) / SUM(pobtot), 1) AS iphone_share_zm,
       ROUND(AVG(iphone_share_pct), 1)                     AS iphone_share_simple,
       MIN(iphone_share_pct)                               AS minimo,
       MAX(iphone_share_pct)                               AS maximo
FROM v_localidad
GROUP BY periodo
ORDER BY periodo;

-- Q1 · Ranking de localidades por año, con cuartil dentro de la ZM
-- (todas suelen pasar de 80%: el cuartil compara relativo, no absoluto)
SELECT periodo, nom_mun, nom_loc, iphone_share_pct, pobtot,
       NTILE(4) OVER (PARTITION BY periodo
                      ORDER BY iphone_share_pct DESC) AS cuartil
FROM v_localidad
ORDER BY periodo, iphone_share_pct DESC;

-- Q2 · Por municipio: share ponderado por población de sus localidades
SELECT periodo, nom_mun,
       COUNT(*)                                            AS localidades,
       ROUND(SUM(iphone_share_pct * pobtot) / SUM(pobtot), 1) AS iphone_share_pct
FROM v_localidad
GROUP BY periodo, mun
ORDER BY periodo, iphone_share_pct DESC;

-- Q3 · Cada localidad vs el promedio ponderado de la ZM en su año
WITH zm AS (
    SELECT periodo, SUM(iphone_share_pct * pobtot) / SUM(pobtot) AS media
    FROM v_localidad
    GROUP BY periodo
)
SELECT l.periodo, l.nom_mun, l.nom_loc, l.iphone_share_pct,
       ROUND(l.iphone_share_pct - zm.media, 1) AS delta_vs_zm_pp
FROM v_localidad l
JOIN zm USING (periodo)
ORDER BY l.periodo, delta_vs_zm_pp DESC;

-- Q4 ⭐ · ¿Se busca más iPhone donde hay más nivel socioeconómico?
-- Pearson en SQL puro entre el share de iPhone y tres indicadores del
-- Censo 2020. Con n ≈ 30-40 localidades, |r| por debajo de 2/√n
-- (umbral_aprox) es indistinguible de ruido.
WITH x AS (
    SELECT periodo, '% viviendas con internet' AS indicador,
           pct_viv_internet AS v, iphone_share_pct AS y FROM v_localidad
    UNION ALL
    SELECT periodo, '% viviendas con auto', pct_viv_auto, iphone_share_pct
    FROM v_localidad
    UNION ALL
    SELECT periodo, 'escolaridad promedio', graproes, iphone_share_pct
    FROM v_localidad
), agg AS (
    SELECT periodo, indicador, COUNT(*) AS n,
           SUM(v) AS sx, SUM(y) AS sy,
           SUM(v * v) AS sx2, SUM(y * y) AS sy2, SUM(v * y) AS sxy
    FROM x
    WHERE v IS NOT NULL
    GROUP BY periodo, indicador
)
SELECT periodo, indicador, n,
       ROUND((n * sxy - sx * sy) / SQRT(
             (n * sx2 - sx * sx) * (n * sy2 - sy * sy)), 3) AS pearson_r,
       ROUND(2.0 / SQRT(n), 2)                              AS umbral_aprox
FROM agg
ORDER BY indicador, periodo;

-- Q5 · Dispersión: ¿la ZM está polarizada o es homogénea?
-- (desviación estándar poblacional calculada a mano)
WITH stats AS (
    SELECT periodo,
           AVG(iphone_share_pct)                    AS media,
           AVG(iphone_share_pct * iphone_share_pct) AS media_cuadrada
    FROM v_localidad
    GROUP BY periodo
)
SELECT periodo,
       ROUND(media, 1)                                AS media_simple,
       ROUND(SQRT(media_cuadrada - media * media), 1) AS desviacion_std
FROM stats
ORDER BY periodo;
