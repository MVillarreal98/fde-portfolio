"""Construye db/iphone_vs_samsung.sqlite a partir de data/raw/.

Uso (desde la raíz del proyecto; sólo librería estándar de Python):
    python scripts/build_db.py

Pasos:
  1. Corre sql/01_create_tables.sql (tablas vacías).
  2. Carga la ZM de Monterrey, el Censo 2020 por localidad (ITER),
     Trends por localidad 2020 y 2025, y StatCounter (contexto nacional).
  3. Empata cada nombre de Trends con una localidad del INEGI y guarda
     el resultado en localidad_match (ver sql/02_sanity_checks.sql).

Si hay varias capturas del mismo archivo, usa la de fecha más reciente.
"""
import csv
import io
import re
import sqlite3
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
REF = ROOT / "data" / "reference"
DB = ROOT / "db" / "iphone_vs_samsung.sqlite"

PERIODOS = ("2020", "2025")
TRENDS_URL = (
    "https://trends.google.com/trends/explore?geo=MX-NLE"
    "&q=%2Fm%2F027lnzs,%2Fm%2F0hnbsn3&date={inicio}%20{fin}"
)
ITER_URL = (
    "https://www.inegi.org.mx/contenidos/programas/ccpv/2020/"
    "datosabiertos/iter/iter_19_cpv2020_csv.zip"
)
STATCOUNTER_URL = "https://gs.statcounter.com/vendor-market-share/mobile/mexico"

# LOC especiales del ITER: 0000 = total municipal, 9998/9999 = localidades
# de una y dos viviendas agrupadas. No son puntos en el mapa.
LOC_AGREGADAS = {"0000", "9998", "9999"}


# ------------------------------------------------------------------
# Utilidades
# ------------------------------------------------------------------
def latest(pattern):
    """Archivo más reciente según la fecha AAAA-MM-DD de su nombre."""
    found = []
    for path in RAW.glob(pattern):
        m = re.search(r"(\d{4}-\d{2}-\d{2})\.\w+$", path.name)
        if m:
            found.append((m.group(1), path))
    return max(found) if found else (None, None)


def decode(raw_bytes):
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return raw_bytes.decode(enc)
        except UnicodeDecodeError:
            continue


def norm(name):
    """'Ciudad Apodaca ' → 'ciudad apodaca' (sin acentos ni signos)."""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split())


def sin_ciudad(n):
    return re.sub(r"^(ciudad|cd) (de )?", "", n)


def nombre_base(name):
    """El INEGI agrega alias y tipo de asentamiento que Trends no usa:
    'Ladrillera (Entronque Pesquería)' → 'ladrillera',
    'Fraccionamiento Real Palmas' → 'real palmas'."""
    n = norm(re.sub(r"[(\[].*?[)\]]", " ", name))
    return re.sub(r"^(fraccionamiento|fracc|colonia|col) ", "", sin_ciudad(n))


def trends_value(text):
    """'85 %', '85%', '<1', '' → 85, 85, 0, None.

    '<1' es un share censurado: Google sólo entrega enteros, así que un
    share minúsculo de localidad chica se lee como 0 (caveat en el README;
    entra al mapa con share de borde en vez de inflar el rango)."""
    text = text.replace(" ", "").replace("%", "").strip()
    if not text:
        return None
    if text.startswith("<"):
        return 0
    return int(float(text))


def number(text):
    """El ITER usa '*' (confidencial) y 'N/D' para datos no disponibles."""
    text = (text or "").strip()
    if text in ("", "*", "N/D"):
        return None
    return float(text)


def coord(text, is_lon):
    """Acepta grados decimales o DMS tipo 100°18'58.009" W."""
    text = (text or "").strip()
    m = re.match(r"(\d+)°\s*(\d+)'\s*([\d.]+)\"?\s*([NSEW])?", text)
    if m:
        value = int(m.group(1)) + int(m.group(2)) / 60 + float(m.group(3)) / 3600
    else:
        try:
            value = float(text)
        except ValueError:
            return None
    # México está al oeste de Greenwich: la longitud siempre es negativa
    return -abs(value) if is_lon else value


# ------------------------------------------------------------------
# Cargas
# ------------------------------------------------------------------
def load_meta(con, source, path, url, timeframe, notes):
    retrieved = re.search(r"(\d{4}-\d{2}-\d{2})", path.name).group(1)
    con.execute(
        "INSERT INTO meta (source, file_name, url, retrieved_at, timeframe, notes)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (source, path.name, url, retrieved, timeframe, notes),
    )


def load_zm(con):
    with open(REF / "zm_monterrey_municipios.csv", encoding="utf-8") as f:
        rows = [(r["mun"].zfill(3), r["nom_mun"]) for r in csv.DictReader(f)]
    con.executemany("INSERT INTO zm_municipio VALUES (?, ?)", rows)
    return {mun for mun, _ in rows}


def load_iter(con, path, zm):
    """Carga las localidades de la ZM; devuelve {nombre: población máxima}
    del resto de N.L. para reconocer después las localidades de Trends
    que están fuera de la ZM."""
    with zipfile.ZipFile(path) as z:
        member = max(
            (i for i in z.infolist() if i.filename.lower().endswith(".csv")),
            key=lambda i: i.file_size,
        )
        reader = csv.DictReader(io.StringIO(decode(z.read(member))))
        rows, fuera_zm = [], {}
        for r in reader:
            mun, loc = r["MUN"].zfill(3), r["LOC"].zfill(4)
            if mun == "000" or loc in LOC_AGREGADAS:
                continue
            if mun not in zm:
                pob = number(r["POBTOT"]) or 0
                n = norm(r["NOM_LOC"])
                for key in {n, sin_ciudad(n), nombre_base(r["NOM_LOC"])}:
                    fuera_zm[key] = max(fuera_zm.get(key, 0), pob)
                continue
            rows.append((
                mun, r["NOM_MUN"], loc, r["NOM_LOC"],
                coord(r["LATITUD"], is_lon=False),
                coord(r["LONGITUD"], is_lon=True),
                number(r["POBTOT"]), number(r["GRAPROES"]),
                number(r["TVIVPARHAB"]), number(r["VPH_INTER"]),
                number(r["VPH_AUTOM"]),
            ))
    con.executemany(
        "INSERT INTO iter_localidad VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
    )
    load_meta(con, "inegi_iter", path, ITER_URL, "Censo 2020",
              "Principales resultados por localidad, N.L.; sólo ZM en la tabla")
    return fuera_zm


def load_trends(con, path, periodo):
    lines = decode(path.read_bytes()).splitlines()
    # Antes de los datos vienen 'Categoría: …' y una línea vacía; el
    # encabezado es la primera línea con columnas separadas por coma.
    try:
        start = next(i for i, line in enumerate(lines) if line.count(",") >= 2)
    except StopIteration:
        sys.exit(
            f"Formato de Trends inesperado en {path.name}: ninguna línea "
            "parece un encabezado CSV (>= 2 comas). Re-desde Trends y "
            "verificar data/raw/download-checklist.md"
        )
    rows = []
    for r in csv.reader(lines[start + 1:]):
        if len(r) >= 3 and r[0].strip():
            rows.append((periodo, r[0].strip(),
                         trends_value(r[1]), trends_value(r[2])))
    if len(rows) < 10:
        sys.exit(
            f"Sospechoso: {path.name} trae {len(rows)} localidades "
            "(una descarga sana trae 50+). Posible CSV truncado o página "
            "sin datos; verificar la descarga."
        )
    con.executemany(
        "INSERT INTO trends_localidad (periodo, trends_name, iphone, galaxy)"
        " VALUES (?, ?, ?, ?)", rows,
    )
    load_meta(con, "google_trends", path,
              TRENDS_URL.format(inicio=f"{periodo}-01-01", fin=f"{periodo}-12-31"),
              periodo,
              "Temas iPhone vs Samsung Galaxy, N.L., resolución Ciudad; "
              "reparto % dentro de cada localidad")


def load_statcounter(con, path):
    reader = csv.DictReader(io.StringIO(decode(path.read_bytes())))
    rows = []
    for r in reader:
        month = r["Date"].strip()[:7] + "-01"
        for vendor, share in r.items():
            if not vendor:  # columna de alias implícita (restkey) o vacía
                continue
            if vendor != "Date" and number(share) is not None:
                rows.append((month, vendor.strip(), number(share)))
    con.executemany(
        "INSERT INTO statcounter_month (month, vendor, share) VALUES (?, ?, ?)",
        rows,
    )
    load_meta(con, "statcounter", path, STATCOUNTER_URL, "2020 - 2025",
              "Proxy de uso real en México (tráfico web), no unidades vendidas")


# ------------------------------------------------------------------
# Empate Trends → INEGI
# ------------------------------------------------------------------
def ip_key(value):
    """Normaliza el share de iphone para las llaves de override sin
    importar la afinidad de columna: 83.0, '83' y b'83' → '83'."""
    text = str(value).strip()
    try:
        number = float(text)
    except ValueError:
        return text.upper()
    return str(int(number)) if number.is_integer() else str(number)


def load_overrides():
    """trends_overrides.csv: periodo e iphone vacíos = aplica a cualquiera;
    loc = EXCLUIR para sacar la fila del mapa."""
    with open(REF / "trends_overrides.csv", encoding="utf-8") as f:
        return {
            (r["periodo"].strip() or "*",
             norm(r["trends_name"]),
             ip_key(r["iphone"]) if r["iphone"].strip() else "*"): (
                r["mun"].zfill(3), r["loc"].strip())
            for r in csv.DictReader(f)
        }


def match_localidades(con, fuera_zm, overrides=None):
    if overrides is None:
        overrides = load_overrides()
    by_name, by_name_sc, by_base, cabeceras = (defaultdict(list) for _ in range(4))
    for mun, nom_mun, loc, nom_loc, pob in con.execute(
        "SELECT mun, nom_mun, loc, nom_loc, COALESCE(pobtot, 0) FROM iter_localidad"
    ):
        by_name[norm(nom_loc)].append((pob, mun, loc))
        by_name_sc[sin_ciudad(norm(nom_loc))].append((pob, mun, loc))
        by_base[nombre_base(nom_loc)].append((pob, mun, loc))
        if loc == "0001":
            cabeceras[norm(nom_mun)].append((pob, mun, loc))

    trends = con.execute(
        "SELECT id, periodo, trends_name, iphone, galaxy FROM trends_localidad"
    ).fetchall()
    con_datos = Counter(
        (periodo, norm(name)) for _, periodo, name, ip, ga in trends
        if ip is not None and ga is not None
    )

    results = []
    for tid, periodo, name, iphone, galaxy in trends:
        n = norm(name)
        override = next(
            (overrides[k] for k in [(p, n, i) for p in (periodo, "*")
                                    for i in (ip_key(iphone), "*")]
             if k in overrides),
            None,
        )
        if iphone is None or galaxy is None:
            results.append((tid, None, None, "sin_datos", 0))
        elif override and override[1].upper() == "EXCLUIR":
            results.append((tid, None, None, "excluido", 0))
        elif override:
            results.append((tid, *override, "manual", 1))
        elif con_datos[(periodo, n)] > 1:
            results.append((tid, None, None, "duplicado", 0))
        else:
            for method, candidates in (
                ("nombre", by_name.get(n)),
                ("nombre_sin_ciudad", by_name_sc.get(sin_ciudad(n))),
                ("nombre_base", by_base.get(nombre_base(name))),
                ("cabecera", cabeceras.get(sin_ciudad(n))),
            ):
                if candidates:
                    # Si el nombre se repite, la localidad más poblada es la
                    # que tiene volumen de búsqueda en Trends. Si esa está
                    # fuera de la ZM (p. ej. un rancho 'Galeana' en la ZM vs
                    # el pueblo de Galeana), la fila no es de Monterrey.
                    pob, mun, loc = max(candidates)
                    # El screening usa las MISMAS claves que poblaron
                    # fuera_zm (nombre, sin Ciudad, base) para que un
                    # homónimo fuera de la ZM no se cuele por el alias con
                    # el que su gemela dentro de la ZM se empató.
                    screen_keys = (n, sin_ciudad(n), nombre_base(name))
                    if max(fuera_zm.get(k, -1) for k in screen_keys) > pob:
                        results.append((tid, None, None, "fuera_zm", len(candidates)))
                    else:
                        results.append((tid, mun, loc, method, len(candidates)))
                    break
            else:
                method = ("fuera_zm" if {n, sin_ciudad(n)} & fuera_zm.keys()
                          else "sin_match")
                results.append((tid, None, None, method, 0))

    con.executemany("INSERT INTO localidad_match VALUES (?, ?, ?, ?, ?)", results)
    return Counter((periodo, r[3]) for (_, periodo, *_), r in zip(trends, results))


# ------------------------------------------------------------------
def main():
    files = {f"trends_{p}": latest(f"trends_nl_localidad_{p}_*.csv") for p in PERIODOS}
    files["iter"] = latest("iter_19_cpv2020_csv_*.zip")
    files["statcounter"] = latest("statcounter_mx_vendors_*.csv")
    missing = [k for k, (_, path) in files.items() if path is None and k != "statcounter"]
    if missing:
        sys.exit(f"Faltan archivos en data/raw/: {', '.join(missing)}. "
                 "Ver data/raw/download-checklist.md")

    DB.parent.mkdir(exist_ok=True)
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)
    con.executescript((ROOT / "sql" / "01_create_tables.sql").read_text(encoding="utf-8"))

    zm = load_zm(con)
    fuera_zm = load_iter(con, files["iter"][1], zm)
    for p in PERIODOS:
        load_trends(con, files[f"trends_{p}"][1], p)
    if files["statcounter"][1]:
        load_statcounter(con, files["statcounter"][1])
    else:
        print("Aviso: sin CSV de StatCounter; 05_contexto_nacional.sql saldrá vacío")
    summary = match_localidades(con, fuera_zm)
    con.commit()

    print(f"Base creada: {DB.relative_to(ROOT)}")
    for (periodo, method), n in sorted(summary.items()):
        print(f"  {periodo}  {method:<18} {n:>4}")
    en_mapa = con.execute(
        "SELECT periodo, COUNT(*) FROM v_localidad GROUP BY periodo"
    ).fetchall()
    print("  Localidades en el mapa:", ", ".join(f"{p}: {n}" for p, n in en_mapa))
    print("Siguiente paso: sqlite3 db/iphone_vs_samsung.sqlite < sql/02_sanity_checks.sql")


if __name__ == "__main__":
    main()
