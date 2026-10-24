"""Genera insights/mapa_mty.html: mapa interactivo de la ZM de Monterrey
con el % de búsquedas de iPhone vs Samsung Galaxy por localidad.

Uso (después de scripts/build_db.py):
    python scripts/mapa_mty.py

Sólo librería estándar: el HTML usa Leaflet desde CDN y lleva los datos
embebidos, así que se abre con doble clic y se puede publicar tal cual.
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "db" / "iphone_vs_samsung.sqlite"
OUT = ROOT / "insights" / "mapa_mty.html"


def load_data(con):
    con.row_factory = sqlite3.Row
    localidades = {}
    for r in con.execute("SELECT * FROM v_localidad"):
        loc = localidades.setdefault((r["mun"], r["loc"]), {
            "nom_loc": r["nom_loc"], "nom_mun": r["nom_mun"],
            "lat": r["lat"], "lon": r["lon"], "pob": r["pobtot"],
            "internet": r["pct_viv_internet"],
            "s2020": None, "s2025": None, "delta": None,
        })
        loc["s" + r["periodo"]] = r["iphone_share_pct"]
    for loc in localidades.values():
        if loc["s2020"] is not None and loc["s2025"] is not None:
            loc["delta"] = round(loc["s2025"] - loc["s2020"], 1)

    resumen = {
        r["periodo"]: r["share"] for r in con.execute(
            "SELECT periodo, ROUND(SUM(iphone_share_pct * pobtot) / SUM(pobtot), 1)"
            " AS share FROM v_localidad GROUP BY periodo")
    }
    fuentes = [dict(r) for r in con.execute(
        "SELECT source, file_name, retrieved_at FROM meta ORDER BY id")]
    return {
        "localidades": [l for l in localidades.values() if l["lat"] is not None],
        "resumen": resumen,
        "fuentes": fuentes,
    }


def main():
    con = sqlite3.connect(DB)
    data = load_data(con)
    html = TEMPLATE.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"Mapa generado: {OUT.relative_to(ROOT)} "
          f"({len(data['localidades'])} localidades)")


TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>iPhone vs Galaxy en Monterrey</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  :root {
    --surface: #fcfcfb; --panel: #ffffff; --ink: #1d1d1b; --ink-2: #55554f;
    --muted: #85857e; --line: #e4e3df; --accent: #2a78d6; --mid: #f0efec;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --surface: #1a1a19; --panel: #232322; --ink: #f2f1ee; --ink-2: #c4c3bd;
      --muted: #8e8d87; --line: #3a3a37; --accent: #3987e5; --mid: #383835;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--surface); color: var(--ink);
         font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }
  h1 { font-size: 1.6rem; margin: 0 0 4px; }
  .sub { color: var(--ink-2); margin: 0 0 20px; max-width: 70ch; }
  .stats { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 16px; }
  .stat { background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
          padding: 10px 14px; min-width: 150px; }
  .stat b { display: block; font-size: 1.5rem; font-variant-numeric: tabular-nums; }
  .stat span { color: var(--muted); font-size: .85rem; }
  .toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
             justify-content: space-between; margin-bottom: 10px; }
  .seg { display: inline-flex; border: 1px solid var(--line); border-radius: 8px;
         overflow: hidden; background: var(--panel); }
  .seg button { border: 0; background: none; color: var(--ink-2); padding: 7px 14px;
                font: inherit; cursor: pointer; }
  .seg button[aria-pressed="true"] { background: var(--accent); color: #fff; }
  .legend { display: flex; align-items: center; gap: 8px; color: var(--ink-2);
            font-size: .85rem; font-variant-numeric: tabular-nums; }
  .legend .bar { width: 160px; height: 10px; border-radius: 5px; }
  #map { height: 560px; border-radius: 12px; border: 1px solid var(--line);
         background: var(--panel); }
  .leaflet-tooltip { font: 13px/1.4 system-ui, sans-serif; }
  .tt b { font-size: 14px; }
  .note { color: var(--muted); font-size: .85rem; margin-top: 8px; }
  details { margin-top: 24px; }
  summary { cursor: pointer; color: var(--ink-2); }
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; margin-top: 10px;
          font-variant-numeric: tabular-nums; font-size: .9rem; }
  th, td { text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--line); }
  th { color: var(--ink-2); font-weight: 600; }
  td.n, th.n { text-align: right; }
  @media (max-width: 600px) { #map { height: 420px; } h1 { font-size: 1.3rem; } }
</style>
</head>
<body>
<main>
  <h1>iPhone vs Samsung Galaxy en la ZM de Monterrey</h1>
  <p class="sub">Porcentaje de búsquedas de iPhone dentro del par iPhone + Galaxy
  (Google Trends, temas) por localidad, 2020 y 2025. Es <strong>interés de
  búsqueda</strong>, no número de usuarios. Cada círculo es una localidad del
  INEGI; su tamaño es la población (Censo 2020).</p>

  <div class="stats" id="stats"></div>

  <div class="toolbar">
    <div class="seg" role="group" aria-label="Vista del mapa">
      <button data-view="2020">2020</button>
      <button data-view="2025">2025</button>
      <button data-view="delta">Cambio 2020 → 2025</button>
    </div>
    <div class="legend" id="legend"></div>
  </div>
  <div id="map" role="img" aria-label="Mapa de la zona metropolitana de Monterrey"></div>
  <p class="note" id="note"></p>

  <details>
    <summary>Ver los datos en tabla</summary>
    <div class="table-wrap"><table id="tabla"></table></div>
  </details>
  <p class="note" id="fuentes"></p>
</main>
<script>
const DATA = /*__DATA__*/null;

const dark = matchMedia("(prefers-color-scheme: dark)").matches;
const SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"];
const MID = dark ? "#383835" : "#f0efec";
const DIV_POS = [MID, "#86b6ef", "#3987e5", "#1c5cab", "#104281"];   // iPhone ganó
const DIV_NEG = [MID, "#f2a3a2", "#e34948", "#b83534", "#8a2423"];   // Galaxy ganó
const fmt = (v, d = 1) => v == null ? "—" : v.toLocaleString("es-MX",
  { minimumFractionDigits: d, maximumFractionDigits: d });

function hex(c) { return [1, 3, 5].map(i => parseInt(c.slice(i, i + 2), 16)); }
function ramp(stops, t) {
  t = Math.max(0, Math.min(1, t));
  const x = t * (stops.length - 1), i = Math.min(Math.floor(x), stops.length - 2);
  const a = hex(stops[i]), b = hex(stops[i + 1]), f = x - i;
  return "rgb(" + a.map((v, k) => Math.round(v + (b[k] - v) * f)).join(",") + ")";
}

const locs = DATA.localidades;
const shares = locs.flatMap(l => [l.s2020, l.s2025]).filter(v => v != null);
// Mismo dominio para 2020 y 2025: el color de un valor no cambia de año a año
const lo = Math.floor(Math.min(...shares)), hi = Math.ceil(Math.max(...shares));
const dMax = Math.max(1, ...locs.map(l => Math.abs(l.delta ?? 0)));
const pobMax = Math.max(...locs.map(l => l.pob || 0));
const radius = p => 6 + 22 * Math.sqrt((p || 0) / pobMax);

function color(view, l) {
  if (view === "delta") {
    return l.delta >= 0 ? ramp(DIV_POS, l.delta / dMax) : ramp(DIV_NEG, -l.delta / dMax);
  }
  return ramp(SEQ, (l["s" + view] - lo) / (hi - lo));
}

// --- resumen ---
const r = DATA.resumen;
const statsHtml = [
  ["2020", r["2020"] != null ? fmt(r["2020"]) + "%" : "—", "iPhone, ZM (ponderado por población)"],
  ["2025", r["2025"] != null ? fmt(r["2025"]) + "%" : "—", "iPhone, ZM (ponderado por población)"],
  ["Cambio", r["2020"] != null && r["2025"] != null
      ? (r["2025"] - r["2020"] >= 0 ? "+" : "") + fmt(r["2025"] - r["2020"]) + " pp" : "—",
   "diferencia entre ambos promedios"],
  ["Localidades", locs.length, "con dato y coordenadas"],
];
document.getElementById("stats").innerHTML = statsHtml.map(([t, v, s]) =>
  `<div class="stat"><span>${t}</span><b>${v}</b><span>${s}</span></div>`).join("");

// --- mapa ---
const map = L.map("map", { scrollWheelZoom: false }).setView([25.69, -100.31], 11);
// Mapa base: satélite (Esri World Imagery) o gris (Esri Canvas), ninguno requiere API key
const canvas = dark ? "World_Dark_Gray_Base" : "World_Light_Gray_Base";
const grayTiles = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/"
  + canvas + "/MapServer/tile/{z}/{y}/{x}", {
  attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
  maxZoom: 16 });
const satTiles = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/"
  + "World_Imagery/MapServer/tile/{z}/{y}/{x}", {
  attribution: "Imágenes &copy; Esri &mdash; Esri, Maxar, Earthstar Geographics",
  maxZoom: 18 });
// Rótulos (nombres de municipios/ciudades) sobre la imagen satelital
const labelTiles = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/"
  + "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", { maxZoom: 18 });
let curView = "2025", baseName = null, baseLayer = null, labelLayer = null;

function setBase(name) {
  if (name === baseName) return;
  baseName = name;
  if (baseLayer) baseLayer.remove();
  if (labelLayer) { labelLayer.remove(); labelLayer = null; }
  if (name === "sat") { baseLayer = satTiles; labelLayer = labelTiles; }
  else { baseLayer = grayTiles; }
  baseLayer.addTo(map);
  if (labelLayer) labelLayer.addTo(map);
  document.querySelectorAll("[data-base]").forEach(b => {
    b.setAttribute("aria-pressed", String(b.dataset.base === name));
    Object.assign(b.style, b.getAttribute("aria-pressed") === "true"
      ? { background: "#4a79e8", color: "#fff" } : { background: dark ? "#33332f" : "#fff", color: dark ? "#ddd" : "#222" });
  });
  if (baseLayer === grayTiles) map.setMaxZoom(16); else map.setMaxZoom(18);
  draw(curView);
}

const BaseCtl = L.Control.extend({
  options: { position: "topright" },
  onAdd() {
    const d = L.DomUtil.create("div", "basectl");
    d.innerHTML = '<button type="button" data-base="sat">Satelital</button>'
      + '<button type="button" data-base="gray">Gris</button>';
    d.querySelectorAll("button").forEach(b => {
      Object.assign(b.style, { border: "0", cursor: "pointer", padding: "4px 10px",
        "border-radius": "6px", font: "12px system-ui, sans-serif" });
      L.DomEvent.on(b, "click", e => { L.DomEvent.stop(e); setBase(b.dataset.base); });
      L.DomEvent.disableClickPropagation(b);
    });
    return d;
  }
});
new BaseCtl().addTo(map);
// Encuadrar cuando el contenedor ya tiene tamaño: si la página carga en una
// pestaña oculta mide 0 px y Leaflet se iría al zoom máximo
let fitted = false;
const mapEl = document.getElementById("map");
new ResizeObserver(() => {
  if (fitted || !locs.length || mapEl.clientWidth === 0) return;
  map.invalidateSize();
  map.fitBounds(locs.map(l => [l.lat, l.lon]), { padding: [30, 30], maxZoom: 13 });
  fitted = true;
}).observe(mapEl);
const layer = L.layerGroup().addTo(map);

function tooltip(l) {
  const row = (k, v) => `<br>${k}: <b>${v}</b>`;
  return `<div class="tt"><b>${l.nom_loc}</b><br><span>${l.nom_mun}</span>` +
    row("2020", l.s2020 == null ? "sin dato"
      : `iPhone <b>${fmt(l.s2020)}%</b> · Galaxy <b>${fmt(100 - l.s2020)}%</b>`) +
    row("2025", l.s2025 == null ? "sin dato"
      : `iPhone <b>${fmt(l.s2025)}%</b> · Galaxy <b>${fmt(100 - l.s2025)}%</b>`) +
    (l.delta == null ? "" : row("Cambio", (l.delta >= 0 ? "+" : "") + fmt(l.delta) + " pp")) +
    row("Población", (l.pob ?? 0).toLocaleString("es-MX")) +
    row("Viviendas con internet", fmt(l.internet) + "%") + "</div>";
}

function draw(view) {
  curView = view;
  layer.clearLayers();
  const key = view === "delta" ? "delta" : "s" + view;
  // Las grandes primero para que las chicas queden encima y se puedan señalar
  const shown = locs.filter(l => l[key] != null).sort((a, b) => (b.pob || 0) - (a.pob || 0));
  for (const l of shown) {
    L.circleMarker([l.lat, l.lon], {
      radius: radius(l.pob), color: dark ? "#1a1a19" : "#ffffff", weight: 2,
      fillColor: color(view, l), fillOpacity: 0.9,
    }).bindTooltip(tooltip(l), { sticky: true }).addTo(layer);
  }
  document.querySelectorAll(".seg button").forEach(b =>
    b.setAttribute("aria-pressed", String(b.dataset.view === view)));

  const lg = document.getElementById("legend");
  if (view === "delta") {
    const g = [...DIV_NEG].reverse().concat(DIV_POS.slice(1));
    lg.innerHTML = `<span>Galaxy ganó −${fmt(dMax)}</span>` +
      `<span class="bar" style="background:linear-gradient(90deg,${g.join(",")})"></span>` +
      `<span>+${fmt(dMax)} iPhone ganó</span>`;
  } else {
    lg.innerHTML = `<span>${lo}%</span><span class="bar" style="background:linear-gradient(90deg,${SEQ.join(",")})"></span><span>${hi}% iPhone</span>`;
  }
  const missing = locs.length - shown.length;
  document.getElementById("note").textContent =
    `${shown.length} localidades en esta vista` +
    (missing ? `; ${missing} sólo tienen dato en uno de los dos años.` : ".") +
    (view === "delta" ? "" : ` Escala de ${lo}% a ${hi}%, igual para ambos años.`);
}
document.querySelectorAll(".seg button").forEach(b =>
  b.addEventListener("click", () => draw(b.dataset.view)));
draw("2025");

// Base satelital por defecto (necesita `layer`, ya declarado arriba)
setBase("sat");

// --- tabla ---
const rows = [...locs].sort((a, b) => (b.delta ?? -1e9) - (a.delta ?? -1e9));
document.getElementById("tabla").innerHTML =
  `<thead><tr><th>Localidad</th><th>Municipio</th><th class="n">iPhone 2020</th>` +
  `<th class="n">iPhone 2025</th><th class="n">Cambio (pp)</th><th class="n">Población</th></tr></thead><tbody>` +
  rows.map(l => `<tr><td>${l.nom_loc}</td><td>${l.nom_mun}</td>` +
    `<td class="n">${fmt(l.s2020)}</td><td class="n">${fmt(l.s2025)}</td>` +
    `<td class="n">${l.delta == null ? "—" : (l.delta >= 0 ? "+" : "") + fmt(l.delta)}</td>` +
    `<td class="n">${(l.pob ?? 0).toLocaleString("es-MX")}</td></tr>`).join("") + "</tbody>";

document.getElementById("fuentes").textContent = "Fuentes: " +
  DATA.fuentes.map(f => `${f.file_name} (captura ${f.retrieved_at})`).join(" · ");
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
