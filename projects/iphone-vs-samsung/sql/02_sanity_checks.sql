-- ============================================================
-- 02_SANITY_CHECKS.SQL
-- "¿Puedo confiar en este dato?" — es lo PRIMERO que corre un analista,
-- antes de analizar nada. Cada check devuelve filas SOLO si hay problema:
-- salida vacía = dato sano.
-- ============================================================

-- CHECK 1 · ZM: cada municipio de la referencia debe existir en el ITER
-- con el mismo nombre (detecta claves INEGI mal capturadas)
SELECT 'ZM_SIN_ITER' AS check_id, z.mun || ' ' || z.nom_mun AS offending,
       MAX(i.nom_mun) AS nombre_en_iter
FROM zm_municipio z
LEFT JOIN iter_localidad i ON i.mun = z.mun
GROUP BY z.mun
HAVING COUNT(i.loc) = 0 OR MAX(i.nom_mun) <> z.nom_mun;

-- CHECK 2 · Cada año debe traer localidades de Trends
SELECT 'TRENDS_VACIO' AS check_id, p.periodo AS offending
FROM (SELECT '2020' AS periodo UNION ALL SELECT '2025') p
LEFT JOIN trends_localidad t ON t.periodo = p.periodo
GROUP BY p.periodo
HAVING COUNT(t.id) = 0;

-- CHECK 3 · Reparto iPhone + Galaxy ≈ 100% (Trends redondea a enteros).
-- Si no suma, el CSV no es el 'desglose comparado' de 2 temas
SELECT 'REPARTO_NO_100' AS check_id, periodo || ' ' || trends_name AS offending,
       iphone + galaxy AS suma
FROM trends_localidad
WHERE iphone + galaxy NOT BETWEEN 98 AND 102;

-- CHECK 4 · Nombres de Trends que no se pudieron empatar con el INEGI.
-- Si la localidad es de la ZM, agrégala a data/reference/trends_overrides.csv
SELECT 'LOC_SIN_MATCH' AS check_id, t.periodo || ' ' || t.trends_name AS offending,
       t.iphone, t.galaxy
FROM localidad_match m
JOIN trends_localidad t ON t.id = m.trends_id
WHERE m.method = 'sin_match';

-- CHECK 5 · Nombres repetidos en un mismo año (p. ej. dos 'Guadalupe').
-- Quedan fuera del mapa hasta resolverlos en trends_overrides.csv usando
-- el valor de iphone para distinguirlos (verlo en el mapa de Trends)
SELECT 'LOC_DUPLICADA' AS check_id, t.periodo || ' ' || t.trends_name AS offending,
       t.iphone, t.galaxy
FROM localidad_match m
JOIN trends_localidad t ON t.id = m.trends_id
WHERE m.method = 'duplicado';

-- CHECK 6 · Empates ambiguos: el nombre existe en varias localidades de la
-- ZM y se tomó la más poblada. Revisar que sea la correcta
SELECT 'LOC_AMBIGUA' AS check_id, t.periodo || ' ' || t.trends_name AS offending,
       m.candidates, i.nom_mun || ' / ' || i.nom_loc AS elegida, i.pobtot
FROM localidad_match m
JOIN trends_localidad t ON t.id = m.trends_id
JOIN iter_localidad   i ON i.mun = m.mun AND i.loc = m.loc
WHERE m.candidates > 1;

-- CHECK 7 · Overrides que apuntan a una localidad que no existe en el ITER
SELECT 'OVERRIDE_INVALIDO' AS check_id, t.periodo || ' ' || t.trends_name AS offending,
       m.mun, m.loc
FROM localidad_match m
JOIN trends_localidad t ON t.id = m.trends_id
LEFT JOIN iter_localidad i ON i.mun = m.mun AND i.loc = m.loc
WHERE m.method = 'manual' AND i.loc IS NULL;

-- CHECK 8 · Localidades del mapa sin coordenadas o con coordenadas fuera
-- de la ZM (caja amplia alrededor de Monterrey)
SELECT 'COORD_MALA' AS check_id, periodo || ' ' || nom_loc AS offending, lat, lon
FROM v_localidad
WHERE lat IS NULL OR lon IS NULL
   OR lat NOT BETWEEN 25.0 AND 26.5
   OR lon NOT BETWEEN -101.0 AND -99.5;

-- CHECK 9 · StatCounter: con todos los fabricantes cargados (incl. 'Other')
-- la suma mensual debe dar 100% ± 1 (redondeo de StatCounter)
SELECT 'SC_SUM_BAD' AS check_id, month AS offending, SUM(share) AS total_pct
FROM statcounter_month
WHERE role = 'measured'
GROUP BY month
HAVING SUM(share) < 99 OR SUM(share) > 101;

-- CHECK 10 · Trazabilidad: la fecha de captura registrada en meta debe ser
-- la misma que lleva el nombre del archivo (convención de download-checklist)
SELECT 'META_DATE_MISMATCH' AS check_id, file_name AS offending, retrieved_at
FROM meta
WHERE file_name NOT LIKE '%\_' || retrieved_at || '.%' ESCAPE '\';
