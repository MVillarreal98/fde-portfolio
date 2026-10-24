# notebooks: EDA opcional

El flujo principal no necesita notebooks (`scripts/` + `sql/`). Usa esta
carpeta para exploración visual extra sobre `db/iphone_vs_samsung.sqlite`,
por ejemplo:

1. Scatter de `iphone_share_pct` vs `pct_viv_internet` (vista `v_localidad`),
   un punto por localidad y año: acompaña al Pearson de `03_por_localidad.sql`.
2. Gráfico de pendiente 2020 → 2025 por municipio (`04_cambio_2020_2025.sql`, Q2).

No versiones outputs del notebook: exporta lo que publiques a `insights/`.
