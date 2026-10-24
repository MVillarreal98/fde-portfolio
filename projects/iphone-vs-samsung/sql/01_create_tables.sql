-- ============================================================
-- 01_CREATE_TABLES.SQL
-- DDL + vista base del mapa + tabla de trazabilidad `meta`.
-- No se corre a mano: lo ejecuta scripts/build_db.py antes de cargar
-- los CSV (la carga necesita Python para leer el zip del INEGI,
-- convertir coordenadas y empatar nombres de localidad).
-- ============================================================

PRAGMA foreign_keys = ON;

-- ------------------------------------------------------------
-- META: trazabilidad de cada fuente. Un repo de analítica sin
-- esta tabla no sabe de dónde salió cada número.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS meta;
CREATE TABLE meta (
    id            INTEGER PRIMARY KEY,
    source        TEXT NOT NULL,        -- 'google_trends' | 'inegi_iter' | 'statcounter'
    file_name     TEXT NOT NULL,        -- archivo de data/raw/ (lleva la fecha de captura)
    url           TEXT NOT NULL,
    retrieved_at  TEXT NOT NULL,        -- fecha de captura (formato ISO 8601)
    timeframe     TEXT,                 -- '2020', '2025', 'Censo 2020', ...
    notes         TEXT
);

-- ------------------------------------------------------------
-- ZM_MUNICIPIO: municipios de la Zona Metropolitana de Monterrey
-- (data/reference/zm_monterrey_municipios.csv). Define qué cuenta
-- como "Monterrey" en todo el análisis.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS zm_municipio;
CREATE TABLE zm_municipio (
    mun      TEXT NOT NULL PRIMARY KEY,     -- clave INEGI de 3 dígitos ('039')
    nom_mun  TEXT NOT NULL
);

-- ------------------------------------------------------------
-- TRENDS_LOCALIDAD: 'desglose por subregión' de Nuevo León con
-- resolución Ciudad, una descarga por año (2020 y 2025).
-- Temas: iPhone (/m/027lnzs) vs Samsung Galaxy (/m/0hnbsn3).
-- Al comparar 2 temas, cada fila es el reparto iPhone / Galaxy dentro
-- de esa localidad (suma ≈ 100%). Al ser un reparto y no un índice,
-- 2020 y 2025 sí son comparables aunque vengan de descargas distintas.
-- id conserva el orden del CSV: Trends puede repetir un nombre
-- (hay dos 'Guadalupe' en N.L.) y el nombre solo no basta de llave.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS trends_localidad;
CREATE TABLE trends_localidad (
    id          INTEGER PRIMARY KEY,
    periodo     TEXT NOT NULL CHECK (periodo IN ('2020', '2025')),
    trends_name TEXT NOT NULL,
    iphone      INTEGER CHECK (iphone BETWEEN 0 AND 100),   -- NULL = sin datos
    galaxy      INTEGER CHECK (galaxy BETWEEN 0 AND 100)
);

-- ------------------------------------------------------------
-- ITER_LOCALIDAD: Censo 2020, principales resultados por localidad
-- (ITER), sólo municipios de la ZM. Aporta coordenadas y los
-- indicadores socioeconómicos para el cruce.
-- ------------------------------------------------------------
DROP TABLE IF EXISTS iter_localidad;
CREATE TABLE iter_localidad (
    mun         TEXT NOT NULL REFERENCES zm_municipio (mun),
    nom_mun     TEXT NOT NULL,
    loc         TEXT NOT NULL,              -- clave de 4 dígitos ('0001' = cabecera)
    nom_loc     TEXT NOT NULL,
    lat         REAL,                       -- grados decimales
    lon         REAL,
    pobtot      INTEGER,                    -- población total
    graproes    REAL,                       -- grado promedio de escolaridad
    tvivparhab  INTEGER,                    -- viviendas particulares habitadas
    vph_inter   INTEGER,                    -- … con internet
    vph_autom   INTEGER,                    -- … con automóvil
    PRIMARY KEY (mun, loc)
);

-- ------------------------------------------------------------
-- LOCALIDAD_MATCH: resultado del empate Trends → INEGI que hace
-- build_db.py. mun/loc quedan NULL cuando la fila no entra al mapa.
--   method: 'manual' | 'nombre' | 'nombre_sin_ciudad' | 'nombre_base'
--           | 'cabecera'
--           | 'sin_datos' | 'duplicado' | 'excluido' | 'fuera_zm' | 'sin_match'
--   candidates: localidades INEGI con ese nombre (>1 = revisar)
-- ------------------------------------------------------------
DROP TABLE IF EXISTS localidad_match;
CREATE TABLE localidad_match (
    trends_id   INTEGER NOT NULL PRIMARY KEY REFERENCES trends_localidad (id),
    mun         TEXT,
    loc         TEXT,
    method      TEXT NOT NULL,
    candidates  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (mun, loc) REFERENCES iter_localidad (mun, loc)
);

-- ------------------------------------------------------------
-- STATCOUNTER_MONTH: cuota mensual de uso por fabricante en MÉXICO
-- (StatCounter no baja a ciudad: sólo es contexto nacional).
-- month: 'YYYY-MM-01'
-- ------------------------------------------------------------
DROP TABLE IF EXISTS statcounter_month;
CREATE TABLE statcounter_month (
    month   TEXT NOT NULL,                  -- primer día del mes
    vendor  TEXT NOT NULL,                  -- 'Apple', 'Samsung', 'Motorola', ...
    share   REAL CHECK (share BETWEEN 0 AND 100),
    role    TEXT NOT NULL DEFAULT 'measured'
            CHECK (role IN ('measured', 'derived')),
            -- 'derived' = share recalculado, p. ej. Apple/Native+
    PRIMARY KEY (month, vendor)
);

-- ------------------------------------------------------------
-- V_LOCALIDAD: una fila por localidad de la ZM que entra al mapa,
-- con su share de iPhone, coordenadas e indicadores del Censo.
-- La usan los SQL 03-05 y scripts/mapa_mty.py.
-- ------------------------------------------------------------
DROP VIEW IF EXISTS v_localidad;
CREATE VIEW v_localidad AS
SELECT t.id                                           AS trends_id,
       t.periodo,
       t.trends_name,
       t.iphone,
       t.galaxy,
       ROUND(100.0 * t.iphone / (t.iphone + t.galaxy), 1) AS iphone_share_pct,
       m.method,
       i.mun, i.nom_mun, i.loc, i.nom_loc,
       i.lat, i.lon,
       i.pobtot,
       i.graproes,
       ROUND(100.0 * i.vph_inter / NULLIF(i.tvivparhab, 0), 1) AS pct_viv_internet,
       ROUND(100.0 * i.vph_autom / NULLIF(i.tvivparhab, 0), 1) AS pct_viv_auto
FROM trends_localidad t
JOIN localidad_match  m ON m.trends_id = t.id
JOIN iter_localidad   i ON i.mun = m.mun AND i.loc = m.loc
WHERE t.iphone + t.galaxy > 0;

-- ------------------------------------------------------------
-- V_LOCALIDAD_CAMBIO: una fila por localidad con dato en 2020 Y 2025.
-- delta_pp > 0 = iPhone ganó terreno frente a Galaxy en esa localidad.
-- ------------------------------------------------------------
DROP VIEW IF EXISTS v_localidad_cambio;
CREATE VIEW v_localidad_cambio AS
SELECT a.mun, a.nom_mun, a.loc, a.nom_loc,
       a.lat, a.lon, a.pobtot, a.graproes, a.pct_viv_internet, a.pct_viv_auto,
       a.iphone_share_pct                          AS share_2020,
       b.iphone_share_pct                          AS share_2025,
       ROUND(b.iphone_share_pct - a.iphone_share_pct, 1) AS delta_pp
FROM v_localidad a
JOIN v_localidad b ON b.mun = a.mun AND b.loc = a.loc
WHERE a.periodo = '2020' AND b.periodo = '2025';
