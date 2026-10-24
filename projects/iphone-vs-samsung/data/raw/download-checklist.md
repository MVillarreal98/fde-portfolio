# Checklist de descarga de datos

> Regla de oro: los archivos de `raw/` **nunca se editan**. El nombre incluye
> la fecha de captura (`AAAA-MM-DD`) porque Trends recalcula sus valores con
> cada captura: sin fecha, el dato no es reproducible. `build_db.py` usa la
> captura más reciente de cada archivo.

## 1. Google Trends — por localidad, 2020

1. Abrir este enlace (ya trae los **temas** y Nuevo León):
   <https://trends.google.com/trends/explore?date=2020-01-01%202020-12-31&geo=MX-NLE&q=%2Fm%2F027lnzs,%2Fm%2F0hnbsn3&hl=es>
   - `/m/027lnzs` = tema **iPhone** (Teléfono móvil)
   - `/m/0hnbsn3` = tema **Samsung Galaxy** (Gama)
   - Verifica que debajo de cada término diga *Teléfono móvil* / *Gama*,
     no *Término de búsqueda*.
2. Bajar hasta **"Desglose comparado por subregión"** → cambiar la
   resolución de *Subregión* a **Ciudad**.
3. Deja **desactivado** "Incluir regiones con poco volumen de búsqueda"
   (valor por omisión): con poco volumen los porcentajes son ruido.
4. Exportar CSV →
   `data/raw/trends_nl_localidad_2020_<AAAA-MM-DD>.csv`

## 2. Google Trends — por localidad, 2025

Mismo procedimiento, cambiando sólo las fechas:
<https://trends.google.com/trends/explore?date=2025-01-01%202025-12-31&geo=MX-NLE&q=%2Fm%2F027lnzs,%2Fm%2F0hnbsn3&hl=es>

→ `data/raw/trends_nl_localidad_2025_<AAAA-MM-DD>.csv`

> Si Trends responde "Error 429", espera unos minutos y recarga: limita las
> consultas seguidas. No uses scrapers (pytrends está archivado).

## 3. INEGI — Censo 2020, principales resultados por localidad (ITER)

1. Descargar el ZIP de Nuevo León (clave 19):
   <https://www.inegi.org.mx/contenidos/programas/ccpv/2020/datosabiertos/iter/iter_19_cpv2020_csv.zip>
   (página: <https://www.inegi.org.mx/programas/ccpv/2020/#datos_abiertos>)
2. **No lo descomprimas**: guárdalo tal cual como
   `data/raw/iter_19_cpv2020_csv_<AAAA-MM-DD>.zip`
3. Columnas que usa `build_db.py`: `MUN, NOM_MUN, LOC, NOM_LOC, LATITUD,
   LONGITUD, POBTOT, GRAPROES, TVIVPARHAB, VPH_INTER, VPH_AUTOM`.

## 4. StatCounter — contexto nacional

1. Ir a <https://gs.statcounter.com/vendor-market-share/mobile/mexico>
2. Editar periodo: `Ene 2020 – Dic 2025`, granularidad mensual
3. Botón **Download Data (.csv)** →
   `data/raw/statcounter_mx_vendors_<AAAA-MM-DD>.csv`
4. ⚠️ StatCounter mide **participación en tráfico web** en todo México, no
   unidades vendidas ni Monterrey. Es opcional: sin él sólo se queda vacío
   `05_contexto_nacional.sql`.

## 5. Zona Metropolitana de Monterrey

`data/reference/zm_monterrey_municipios.csv` trae los 18 municipios de la
delimitación *Metrópolis de México 2020* (SEDATU-CONAPO-INEGI). Si quieres
otro recorte (p. ej. sólo el área urbana), edita ese archivo; el CHECK 1 de
`02_sanity_checks.sql` valida que las claves coincidan con el ITER.

## Registro en la tabla `meta`

`build_db.py` registra cada archivo en `meta`:
`source, file_name, url, retrieved_at, timeframe, notes`.
Si `retrieved_at` difiere de la fecha del nombre de archivo → CHECK 10 falla.
