# insights/ — entregables para publicar

- `mapa_mty.html` — mapa interactivo de la ZM de Monterrey: % de búsquedas
  de iPhone vs Galaxy por localidad, vistas 2020 / 2025 / cambio, con tabla
  de datos. Lo genera `python scripts/mapa_mty.py`; se abre con doble clic
  o se publica tal cual (GitHub Pages, por ejemplo).

Cada entregable debe poder recrearse íntegramente desde `data/raw/` con
`scripts/build_db.py` + el script que lo genera.
