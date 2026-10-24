"""Tests unitarios de la precedencia del match Trends → INEGI."""
import sqlite3
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import build_db  # noqa: E402


@pytest.fixture()
def con():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
        CREATE TABLE iter_localidad (
            mun TEXT, nom_mun TEXT, loc TEXT, nom_loc TEXT,
            lat REAL, lon REAL, pobtot REAL,
            graproes REAL, tvivparhab REAL, vph_inter REAL, vph_autom REAL);
        CREATE TABLE trends_localidad (
            id INTEGER, periodo TEXT, trends_name TEXT,
            iphone REAL, galaxy REAL);
        CREATE TABLE localidad_match (
            trends_id INTEGER, mun TEXT, loc TEXT, method TEXT,
            candidates INTEGER);
    """)
    yield conn
    conn.close()


def load(con, zm_rows, trends_rows):
    con.executemany(
        "INSERT INTO iter_localidad (mun, nom_mun, loc, nom_loc, pobtot)"
        " VALUES (?,?,?,?,?)",
        zm_rows,
    )
    con.executemany("INSERT INTO trends_localidad VALUES (?,?,?,?,?)", trends_rows)


def methods(con):
    return {t[0]: t[1] for t in con.execute(
        "SELECT t.trends_name, m.method FROM localidad_match m "
        "JOIN trends_localidad t ON t.id = m.trends_id")}


# --- a) override gana a todo ---

def test_override_wins_over_every_rule(con):
    load(con, [("021", "Monterrey", "0001", "Monterrey", 1000)],
         [(1, "2025", "Mitras Poniente", 90, 10)])
    overrides = {("2025", "mitras poniente", "90"): ("021", "0002")}
    build_db.match_localidades(con, {}, overrides)
    assert methods(con)["Mitras Poniente"] == "manual"


# --- b) precedencia nombre exacto > base ---

def test_exact_name_beats_base_and_header(con):
    zm = [
        ("006", "García", "0153", "Pueblo Nuevo (Tepehuaje)", 870),
        ("010", "Santiago", "0001", "Santiago", 43000),
    ]
    load(con, zm, [
        (1, "2020", "Santiago", 82, 18),
        (2, "2025", "Pueblo Nuevo", 86, 14),
    ])
    build_db.match_localidades(con, {})
    got = methods(con)
    assert got["Santiago"] == "nombre"
    # Trends dice 'Pueblo Nuevo'; el ITER trae 'Pueblo Nuevo (Tepehuaje)'
    assert got["Pueblo Nuevo"] == "nombre_base"


def test_header_fallback_when_no_named_locality_matches(con):
    load(con, [("006", "Juárez", "0001", "Ciudad Benito Juárez", 150000)],
         [(1, "2020", "Juárez", 75, 25)])
    build_db.match_localidades(con, {})
    assert methods(con)["Juárez"] == "cabecera"


# --- c) por población dentro del mismo nombre ---

def test_ties_resolve_to_the_most_populated(con):
    load(con, [
        ("021", "Monterrey", "0005", "Cumbres", 1200),
        ("019", "San Nicolás", "0003", "Cumbres", 50000),
    ], [(1, "2020", "Cumbres", 80, 20)])
    build_db.match_localidades(con, {})
    row = con.execute("SELECT mun, loc, candidates FROM localidad_match").fetchone()
    assert (row[0], row[1]) == ("019", "0003")
    assert row[2] == 2  # el sanity check la marcará como LOC_AMBIGUA


# --- d) homónimo fuera de la ZM gana por población → fuera_zm ---

def test_out_of_zm_homonym_discards_the_row(con):
    load(con, [("021", "Monterrey", "0007", "Galeana", 300)],
         [(1, "2020", "Galeana", 75, 25)])
    fuera_zm = {"galeana": 50000, "galeana": 50000, "ciudad galeana": 50000}
    build_db.match_localidades(con, fuera_zm)
    assert methods(con)["Galeana"] == "fuera_zm"


def test_base_alias_screen_finds_out_of_zm_twin_via_base_name(con):
    # El match dentro de la ZM vino por nombre_base; el homónimo fuera de la
    # ZM sólo es reconocible por su base ('san martin'). Antes del fix la
    # pantalla sólo comparaba el nombre completo y el alias se colaba.
    load(con, [("021", "Monterrey", "0009", "Real San Martín", 250)],
         [(1, "2025", "Real San Martín (Privada)", 88, 12)])
    fuera_zm = {"real san martin": 40000, "san martin": 40000}
    build_db.match_localidades(con, fuera_zm)
    assert methods(con)["Real San Martín (Privada)"] == "fuera_zm"


# --- e) duplicado y sin datos ---

def test_duplicate_and_missing_data(con):
    load(con, [("021", "Monterrey", "0001", "Monterrey", 1000)],
         [
             (1, "2020", "Guadalupe", 88, 12),
             (2, "2020", "Guadalupe", 91, 9),
             (3, "2025", "Alondras", None, None),
         ])
    build_db.match_localidades(con, {})
    got = methods(con)
    assert got["Alondras"] == "sin_datos"
    assert all(m == "duplicado" for name, m in got.items() if name == "Guadalupe")


def test_excluir_override(con):
    load(con, [("018", "Linares", "0099", "Guadalupe rural", 500)],
         [(1, "2025", "Guadalupe", 100, 0)])
    overrides = {("*", "guadalupe", "100"): ("018", "EXCLUIR")}
    build_db.match_localidades(con, {}, overrides)
    assert methods(con)["Guadalupe"] == "excluido"
