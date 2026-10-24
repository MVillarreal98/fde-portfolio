# iPhone vs Samsung Galaxy en Monterrey 📍 2020 vs 2025

Proyecto de análisis de datos con **SQLite + Python (sólo librería estándar)**.
Mapea, localidad por localidad, en qué parte de la **Zona Metropolitana de
Monterrey** se busca más iPhone que Samsung Galaxy, cómo cambió entre
**2020 y 2025** y si coincide con el nivel socioeconómico de cada zona.

> **Por qué este proyecto:** cruza tres fuentes públicas independientes
> (Google Trends, Censo 2020 del INEGI y StatCounter) a nivel de colonia/
> localidad, con trazabilidad y checks de calidad: el tipo de trabajo que
> separa un análisis real de un tutorial.

## Preguntas de negocio

1. **¿Dónde de la ZM de Monterrey domina la conversación de iPhone y dónde
   la de Galaxy?** (mapa por localidad)
2. **¿Qué cambió de 2020 a 2025?** ¿El iPhone ganó terreno parejo o sólo en
   ciertas zonas?
3. **¿Se busca más iPhone donde hay más nivel socioeconómico?** (cruce con
   % de viviendas con internet / auto y escolaridad, Censo 2020)
4. **Contexto:** ¿cuánto se *busca* iPhone en Monterrey frente a cuánto se
   *usa* en México?

## Hallazgos (captura del 2026-10-23)

Mapa interactivo: [`insights/mapa_mty.html`](insights/mapa_mty.html) ·
22 localidades con dato en 2020 y 32 en 2025 (4.6–4.7 M habitantes cubiertos).

1. **El iPhone domina la conversación en toda la ZM y creció:** pasó de
   **81.2% a 87.1%** de las búsquedas iPhone + Galaxy (ponderado por
   población). Subió en las 22 localidades con dato en ambos años; ninguna bajó.
2. **El mayor salto fue en la periferia, no en el centro:** El Carmen
   (+15 pp), Salinas Victoria, General Zuazua, Ciénega de Flores y García
   (+13 pp). El centro ya estaba alto y se movió menos: San Nicolás +2,
   Monterrey +4, San Pedro +5 (que sigue arriba con 91%).
3. **La brecha socioeconómica se está cerrando:** las localidades con menos
   viviendas con internet subieron +9.4 pp contra +4.9 pp de las que tienen
   más, y la dispersión entre localidades bajó de 5.3 a 2.8 pp. Aun así, el
   share de iPhone sigue correlacionado con el % de viviendas con auto
   (r = 0.72 en 2020 → 0.57 en 2025, ambos por encima del umbral de ruido).
4. **Se busca mucho más iPhone del que se usa:** en México, Apple tiene ~39%
   del par Apple + Samsung en uso real (StatCounter 2025), pero en la ZM se
   lleva 87% de las búsquedas: una brecha de ~48 pp. La conversación no es
   el mercado.

> Valores de Trends redondeados a enteros por Google; interés de búsqueda,
> no usuarios. Detalle en `sql/03`–`sql/05`.

## Fuentes de datos (públicas)

| Fuente | Qué aporta | Nivel |
|--------|-----------|-------|
| [Google Trends](https://trends.google.com/trends/explore?geo=MX-NLE&q=%2Fm%2F027lnzs,%2Fm%2F0hnbsn3) — temas *iPhone* vs *Samsung Galaxy* | Reparto % de búsquedas en cada localidad, 2020 y 2025 | Localidad (N.L.) |
| [INEGI — Censo 2020, ITER](https://www.inegi.org.mx/programas/ccpv/2020/#datos_abiertos) | Coordenadas, población e indicadores socioeconómicos por localidad | Localidad |
| [StatCounter México](https://gs.statcounter.com/vendor-market-share/mobile/mexico) | Cuota de uso real por fabricante | **Sólo país** |

**Caveats documentados (importantes):**

- Trends mide **interés de búsqueda, no usuarios**. No existe un dato público
  de cuántas personas usan iPhone o Android por ciudad.
- Se usan **temas** de Trends, no palabras: la búsqueda "samsung" incluye
  televisores y electrodomésticos; el tema *Samsung Galaxy* no.
- Al comparar dos temas, Trends entrega el **reparto dentro de cada
  localidad** (iPhone + Galaxy ≈ 100%). Por eso 2020 y 2025 sí son
  comparables aunque sean descargas distintas.
- Trends sólo reporta localidades con volumen suficiente; las chicas pueden
  aparecer en un año y no en el otro (ver `sql/04_cambio_2020_2025.sql`, Q4).
- Un share de Trends menor a 1% (`<1`) se guarda como 0: Google sólo entrega
  enteros, así que el share de una localidad mínima es un *censor* del dato,
  no una medición de 0%.
- StatCounter es contexto **nacional** (tráfico web, no unidades vendidas).

## Cómo está probado

- **Unit tests** de la precedencia del match (`tests/test_matching.py`,
  8 fixtures): override por año y valor de `iphone` gana a todo, nombre
  exacto > base > cabecera, empates por nombre más poblado, homónimo fuera
  de la ZM por población *y por alias base*, duplicados y `EXCLUIR`.
- **Pipeline como smoke**: `build_db.py` + `02_sanity_checks.sql` (cero
  filas) + generación del mapa. Se corre en CI en cada push.

## Estructura

```
iphone-vs-samsung/
├── README.md
├── data/
│   ├── raw/                          # descargas, NO se modifican (fecha en el nombre)
│   │   └── download-checklist.md     # qué bajar, de dónde y cómo nombrarlo
│   └── reference/
│       ├── zm_monterrey_municipios.csv   # qué municipios cuentan como "Monterrey"
│       └── trends_overrides.csv          # correcciones manuales del empate de nombres
├── scripts/
│   ├── build_db.py                   # CSV/ZIP → SQLite + empate Trends ↔ INEGI
│   └── mapa_mty.py                   # genera insights/mapa_mty.html
├── sql/
│   ├── 01_create_tables.sql          # DDL, vistas base y tabla `meta`
│   ├── 02_sanity_checks.sql          # ¿puedo confiar en este dato?
│   ├── 03_por_localidad.sql          # foto por año + cruce socioeconómico ⭐
│   ├── 04_cambio_2020_2025.sql       # qué cambió y dónde ⭐
│   └── 05_contexto_nacional.sql      # búsqueda en MTY vs uso en México
├── db/                               # base generada (no se versiona)
└── insights/                         # mapa y gráficos para publicar
```

## Cómo correrlo

```bash
# 1. Descargar los archivos siguiendo data/raw/download-checklist.md
# 2. Construir la base (Python 3.9+, sin instalar nada):
python scripts/build_db.py
# 3. Revisar la calidad del dato (salida vacía = sano):
sqlite3 db/iphone_vs_samsung.sqlite < sql/02_sanity_checks.sql
# 4. Análisis:
sqlite3 -header db/iphone_vs_samsung.sqlite < sql/03_por_localidad.sql
sqlite3 -header db/iphone_vs_samsung.sqlite < sql/04_cambio_2020_2025.sql
sqlite3 -header db/iphone_vs_samsung.sqlite < sql/05_contexto_nacional.sql
# 5. Mapa interactivo (se abre con doble clic):
python scripts/mapa_mty.py
```

### Empate de nombres Trends ↔ INEGI

Trends da el nombre de la localidad sin clave ni coordenadas, así que
`build_db.py` lo empata con el ITER del INEGI, en este orden:

1. `trends_overrides.csv` (correcciones manuales)
2. nombre exacto (sin acentos) dentro de la ZM — si se repite, la más poblada
3. nombre sin "Ciudad (de)" — "Ciudad Apodaca" ↔ "Apodaca"
4. nombre sin alias ni "Fraccionamiento" — "Ladrillera" ↔ "Ladrillera (Entronque Pesquería)"
5. nombre del municipio → su cabecera — "Juárez" ↔ "Ciudad Benito Juárez"

Si una localidad fuera de la ZM con ese nombre es más poblada, la fila se
descarta como `fuera_zm`. Lo que no se resuelve aparece en
`02_sanity_checks.sql` (`LOC_SIN_MATCH`, `LOC_DUPLICADA`, `LOC_AMBIGUA`)
para corregirlo en `trends_overrides.csv` (ejemplo ilustrativo; las claves
`loc` reales se buscan en el ITER):

```csv
periodo,trends_name,iphone,mun,loc,nota
,Parque Industrial Ciudad Mitras,,018,0045,García (verificado en mapa de Trends)
2025,Guadalupe,100,,EXCLUIR,Guadalupe rural de Linares
```

`periodo` e `iphone` vacíos = aplica a cualquiera; `iphone` sirve para
distinguir dos filas con el mismo nombre. `loc = EXCLUIR` saca la fila.

## Roadmap (metodología CRISP-DM)

- [x] F0 — Preguntas de negocio, alcance (ZM Monterrey, 2020 vs 2025) y fuentes verificadas
- [x] F1 — Ingesta, empate de localidades y trazabilidad (`meta`)
- [x] F2 — Sanity checks en SQL
- [x] F3 — Descargar datos reales y resolver empates pendientes
- [x] F4 — Análisis por localidad y cambio 2020 → 2025
- [x] F5 — Mapa final + README con hallazgos
- [ ] F6 — Publicar (GitHub + mapa en GitHub Pages)
