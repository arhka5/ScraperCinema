"""Cinerama: los JSON que usa su propia web y la página de cada película.

- /assets/ajax/obtener_cartelera.php → películas
- /assets/ajax/obtener_cines.php     → cines
- /pelicula_cine/<codigo>            → horarios por cine e idioma (HTML)

Su web NO indica la fecha de los horarios: se publican como los de hoy (o los
del día de estreno si es una preventa) y la web lo advierte (ver `NOTE`).
"""
from __future__ import annotations

import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from .client import Client
from .model import Cinema, Movie, Session, SourceResult, now_lima
from .normalize import display_title, guess_city, language_from, movie_key, to_24h

SITE = "https://www.cinerama.com.pe"
NOTE = "Cinerama no indica la fecha de sus horarios; se muestran como los de hoy."


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", name or "").strip().upper()


def _minutes(hhmmss: str) -> int | None:
    m = re.match(r"(\d+):(\d+)", hhmmss or "")
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def parse_cinemas(raw: list[dict]) -> dict[str, Cinema]:
    cinemas: dict[str, Cinema] = {}
    for c in raw:
        if str(c.get("estado", "1")) != "1":
            continue
        name = _norm(c.get("nombre"))
        pretty = re.sub(r"^CINERAMA\s+", "", name).title()
        cinemas[name] = Cinema(
            id=f"cinerama-{c['id']}", chain="cinerama", name=f"Cinerama {pretty}",
            city=guess_city(name, c.get("direccion", "")),
            address=(c.get("direccion") or "").strip().title(), url=f"{SITE}/cines")
    return cinemas


def session_date(time: str, today: str, release: str | None) -> str:
    """Fecha de cartelera de un horario sin fecha.

    En cartelera: hoy. En preventa (estreno futuro): el día del estreno; si es
    de madrugada ("pre estreno de medianoche"), la noche anterior."""
    if release and release > today:
        if time < "05:00":
            return (date.fromisoformat(release) - timedelta(days=1)).isoformat()
        return release
    return today


def parse_movie(html: str, info: dict, cinemas: dict[str, Cinema], today: str) -> SourceResult:
    result = SourceResult("cinerama")
    release = info.get("fecha_estreno") if re.match(r"\d{4}-\d{2}-\d{2}$", info.get("fecha_estreno") or "") else None
    soup = BeautifulSoup(html, "html.parser")
    url = f"{SITE}/pelicula_cine/{info['codigo']}"
    movie = Movie(
        key=movie_key(info["nombre"]), title=display_title(info["nombre"]),
        poster=f"{SITE}/_admin/assets/images/peliculas/{info['imagen']}" if info.get("imagen") else "",
        duration=_minutes(info.get("duracion", "")), rating=info.get("censura") or "",
        urls={"cinerama": url})
    for block in soup.select(".cinema-block"):
        name_tag = block.select_one(".cinema-name")
        if not name_tag:
            continue
        name = _norm(name_tag.get_text(" ", strip=True))
        cinema = cinemas.get(name)
        if cinema is None:  # cine que no está en la lista: se agrega igual
            pretty = re.sub(r"^CINERAMA\s+", "", name).title()
            cinema = Cinema(id=f"cinerama-{re.sub(r'[^a-z0-9]+', '-', pretty.lower())}",
                            chain="cinerama", name=f"Cinerama {pretty}",
                            city=guess_city(name), url=f"{SITE}/cines")
            cinemas[name] = cinema
        for group in block.select(".mb-3"):
            label = group.find(["h4", "h5", "h6"])
            label_text = label.get_text(" ", strip=True) if label else ""
            for a in group.select(".horario-btn"):
                time = to_24h(a.get_text(" ", strip=True))
                if time:
                    result.sessions.append(Session(
                        movie=movie.key, cinema=cinema.id, date=session_date(time, today, release),
                        time=time,
                        format="3D" if "3D" in label_text.upper() else "2D",
                        language=language_from(label_text), url=url, late=time < "05:00"))
    if result.sessions:
        result.movies.append(movie)
        used = {s.cinema for s in result.sessions}
        result.cinemas = [c for c in cinemas.values() if c.id in used]
    return result


def scrape(client: Client) -> SourceResult:
    cinemas = parse_cinemas(client.json(f"{SITE}/assets/ajax/obtener_cines.php"))
    movies = client.json(f"{SITE}/assets/ajax/obtener_cartelera.php")
    today = now_lima().date().isoformat()
    result = SourceResult("cinerama", note=NOTE)
    seen: set[str] = set()
    for info in movies:
        if str(info.get("estado", "1")) != "1":
            continue
        part = parse_movie(client.text(f"{SITE}/pelicula_cine/{info['codigo']}"), info, cinemas, today)
        result.movies += part.movies
        result.sessions += part.sessions
        for c in part.cinemas:
            if c.id not in seen:
                seen.add(c.id)
                result.cinemas.append(c)
    return result
