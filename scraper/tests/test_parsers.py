"""Parsers contra respuestas reales guardadas (tests/fixtures)."""
import json
import re
from datetime import date
from pathlib import Path

from scraper import cinemark, cinepolis, cinerama, cinestar, uvk

FIX = Path(__file__).parent / "fixtures"
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def check(result, chain):
    assert result.sessions, "sin funciones"
    cinema_ids = {c.id for c in result.cinemas}
    movie_keys = {m.key for m in result.movies}
    for s in result.sessions:
        assert DATE.match(s.date) and TIME.match(s.time), s
        assert s.cinema in cinema_ids and s.movie in movie_keys, s
        assert s.cinema.startswith(chain + "-")
        assert s.late == (s.time < "05:00")
    for c in result.cinemas:
        assert c.chain == chain and c.name and c.city


def test_cinemark():
    d = load("cinemark.json")
    r = cinemark.parse(d["theaters"], d["movies"], d["showtimes"])
    check(r, "cinemark")
    # La hora "…Z" es hora local: se usa tal cual, sin restar 5 horas.
    raw = d["showtimes"][-1]
    s = next(x for x in r.sessions if x.time == raw["sessionDateTime"][11:16]
             and x.cinema == f"cinemark-{raw['theaterId']}")
    assert s.date == raw["sessionDisplayDate"]
    # La trasnoche queda en el día anterior (fecha "de cartelera").
    late = [x for x in r.sessions if x.late]
    assert late and all(x.date < f"{x.date[:8]}99" for x in late)
    raw_late = next(x for x in d["showtimes"] if x["isLateNightSession"])
    assert raw_late["sessionDateTime"][:10] > raw_late["sessionDisplayDate"]
    assert any(x.date == raw_late["sessionDisplayDate"] for x in late)


def test_cinestar():
    r = cinestar.parse_branch(load("cinestar_branch.json"), load("cinestar_sur_data.json"))
    check(r, "cinestar")
    assert r.cinemas[0].city == "Lima"
    assert all(m.poster.startswith("https://bucket.tumi-soft.com/") for m in r.movies)
    assert all(s.room.startswith("Sala ") for s in r.sessions)


def test_cinestar_devalue():
    flat = [{"a": 1, "b": 2}, [3, 3], "x", {"c": -1}]
    assert cinestar.devalue(flat) == {"a": [{"c": None}, {"c": None}], "b": "x"}


def test_uvk():
    r = uvk.parse_movie((FIX / "uvk_pelicula.html").read_text(encoding="utf-8"),
                        "https://www.uvk.pe/peliculas/1113/ENTREGA%20AL%20LIMITE",
                        today=date(2026, 10, 20))
    check(r, "uvk")
    assert r.movies[0].title == "Entrega al Limite"
    assert r.movies[0].duration == 98
    names = {c.name for c in r.cinemas}
    assert "UVK El Agustino" in names
    s = next(x for x in r.sessions if x.cinema == "uvk-el-agustino")
    assert (s.date, s.time, s.room, s.language) == ("2026-10-21", "21:30", "Sala 3", "Doblada")
    assert s.url.startswith("https://www.uvk.pe/butacas/")


def test_uvk_cambio_de_anio():
    assert uvk.tab_date("Jueves 01/01", date(2026, 12, 30)) == "2027-01-01"
    assert uvk.tab_date("Miércoles 31/12", date(2027, 1, 2)) == "2026-12-31"


def test_cinepolis():
    r = cinepolis.parse_city(load("cinepolis_arequipa.json"))
    check(r, "cinepolis")
    assert r.cinemas[0].city == "Arequipa"
    assert all(m.poster.startswith("https://") for m in r.movies if m.poster)
    # TimeFilter (serializado en UTC-6) coincide con la hora publicada en
    # TODAS las funciones, y la fecha con la del grupo del día.
    days = load("cinepolis_arequipa.json")["d"]["Cinemas"][0]["Dates"]
    for day in days:
        group_date = cinepolis.local_datetime(day["FilterDate"]).date()
        for m in day["Movies"]:
            for f in m["Formats"]:
                for st in f["Showtimes"]:
                    when = cinepolis.local_datetime(st["TimeFilter"])
                    assert when.strftime("%H:%M") == st["Time"]
                    assert when.date() == group_date


def test_cinerama():
    d = load("cinerama.json")
    cinemas = cinerama.parse_cinemas(d["cinemas"])
    r = cinerama.parse_movie((FIX / "cinerama_pelicula.html").read_text(encoding="utf-8"),
                             d["movie"], cinemas, "2026-10-20")
    check(r, "cinerama")
    assert r.movies[0].title == "Street Fighter"
    assert {s.time for s in r.sessions} >= {"15:00", "21:45"}
    assert any(c.name == "Cinerama Pacifico" and c.city == "Lima" for c in r.cinemas)
    assert {s.date for s in r.sessions} == {"2026-10-20"}  # en cartelera: hoy


def test_cinerama_preventa():
    # Preventa: el día del estreno; la función de medianoche, la noche anterior.
    assert cinerama.session_date("19:00", "2026-10-20", "2026-12-16") == "2026-12-16"
    assert cinerama.session_date("00:01", "2026-10-20", "2026-12-16") == "2026-12-15"
    assert cinerama.session_date("19:00", "2026-10-20", "2026-10-15") == "2026-10-20"
    assert cinerama.session_date("19:00", "2026-10-20", None) == "2026-10-20"
