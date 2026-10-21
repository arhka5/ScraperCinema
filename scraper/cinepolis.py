"""Cinépolis Perú: los mismos endpoints que usa su página de cartelera.

- POST /manejadores/CiudadesComplejos.ashx → ciudades y cines
- POST /Cartelera.aspx/GetNowPlayingByCity → películas y funciones por ciudad

Ninguno está en las rutas prohibidas de su robots.txt (/_CARTELERA/,
/cartelera/aspx/…).

Ojo: `TimeFilter` NO es UTC real. Es la hora local del cine serializada como
si estuviera en UTC-6 (servidor en México): en todas las funciones vale
exactamente "hora publicada + 6 h". Por eso se le restan 6 horas.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .client import Client
from .model import LIMA, Cinema, Movie, Session, SourceResult
from .normalize import display_title, language_from, movie_key, parse_minutes

SITE = "https://cinepolis.com.pe"
JSON_POST = {"Content-Type": "application/json; charset=utf-8", "Origin": SITE}
_EPOCH = re.compile(r"/Date\((-?\d+)")
_SERVER_TZ = timezone(timedelta(hours=-6))


def local_datetime(time_filter: str) -> datetime | None:
    """Hora local del cine (fecha y hora de pared) a partir de `TimeFilter`."""
    m = _EPOCH.search(time_filter or "")
    if not m:
        return None
    wall = datetime.fromtimestamp(int(m.group(1)) / 1000, tz=_SERVER_TZ)
    return wall.replace(tzinfo=LIMA)


def parse_city(payload: dict) -> SourceResult:
    result = SourceResult("cinepolis")
    data = payload.get("d") or {}
    seen_movies: set[str] = set()
    for c in data.get("Cinemas") or []:
        city = (c.get("CityName") or "").split(",")[0].strip()
        cinema = Cinema(
            id=f"cinepolis-{c['Id']}",
            chain="cinepolis",
            name=(c.get("Name") or "").strip(),
            city=city or "Otras",
            url=f"{SITE}/cartelera/{c.get('CityKey', '')}/{c.get('Key', '')}".rstrip("/"),
        )
        result.cinemas.append(cinema)
        for day in c.get("Dates") or []:
            for m in day.get("Movies") or []:
                key = movie_key(m["Title"])
                url = f"{SITE}/pelicula/{m['Key']}" if m.get("Key") else cinema.url
                if key not in seen_movies:
                    seen_movies.add(key)
                    poster = (m.get("Poster") or "").replace("http://", "https://", 1)
                    result.movies.append(Movie(
                        key=key, title=display_title(m["Title"]), poster=poster,
                        duration=parse_minutes(m.get("RunTime") or ""),
                        rating=m.get("Rating") or "", urls={"cinepolis": url}))
                for f in m.get("Formats") or []:
                    name = (f.get("Name") or "").upper()
                    language = language_from(f.get("Language") or name)
                    if not language and "ESP" in name:
                        language = "Doblada"  # películas habladas en español
                    fmt = " ".join(t for t in name.split() if t not in {"DOB", "SUB", "ESP", "ORI"})
                    for s in f.get("Showtimes") or []:
                        when = local_datetime(s.get("TimeFilter"))
                        time = (s.get("Time") or (when.strftime("%H:%M") if when else ""))[:5]
                        if not when or not time:
                            continue
                        day_of = when.date()
                        if time < "05:00":  # trasnoche: cuenta para el día anterior
                            day_of -= timedelta(days=1)
                        result.sessions.append(Session(
                            movie=key, cinema=cinema.id, date=day_of.isoformat(), time=time,
                            format=fmt or "2D", language=language, url=url, late=time < "05:00"))
    return result


def scrape(client: Client) -> SourceResult:
    cities = client.json(f"{SITE}/manejadores/CiudadesComplejos.ashx", params={"EsVIP": "false"},
                         method="POST", json={}, headers=JSON_POST)
    result = SourceResult("cinepolis")
    for city in cities:
        payload = client.json(f"{SITE}/Cartelera.aspx/GetNowPlayingByCity", method="POST",
                              json={"claveCiudad": city["Clave"], "esVIP": False},
                              headers=JSON_POST)
        part = parse_city(payload)
        result.cinemas += part.cinemas
        result.movies += part.movies
        result.sessions += part.sessions
    return result
