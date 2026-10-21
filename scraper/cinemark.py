"""Cinemark Perú: API pública que usa su propia web (bff.cinemark-peru.com).

Ojo: `sessionDateTime` viene con sufijo "Z" pero es HORA LOCAL de Lima, no UTC
(las funciones van de 10:00 a 00:xx). Por eso se usa el texto tal cual.
Las funciones de trasnoche (00:xx) traen `sessionDisplayDate` del día anterior.
"""
from __future__ import annotations

from .client import Client
from .model import Cinema, Movie, Session, SourceResult
from .normalize import display_title, guess_city, language_from, movie_key

API = "https://bff.cinemark-peru.com/api"
SITE = "https://www.cinemark-peru.com"
HEADERS = {"country": "PE", "Origin": SITE, "Referer": SITE + "/"}


def parse(theaters: list[dict], movies: list[dict], showtimes: list[dict]) -> SourceResult:
    result = SourceResult("cinemark")

    for t in theaters:
        result.cinemas.append(Cinema(
            id=f"cinemark-{t['id']}",
            chain="cinemark",
            name=t["name"].strip(),
            city=(t.get("city") or (t.get("location") or {}).get("name") or "").strip().title()
                 or guess_city(t.get("name", ""), t.get("address", "")),
            address=(t.get("address") or "").strip(),
            url=f"{SITE}/cartelera/{t['slug']}" if t.get("slug") else SITE,
        ))

    by_corporate: dict[str, Movie] = {}
    for m in movies:
        key = movie_key(m["title"])
        movie = Movie(
            key=key,
            title=display_title(m["title"]),
            poster=m.get("posterUrl") or "",
            duration=m.get("runTime") or None,
            rating=m.get("rating") or "",
            urls={"cinemark": f"{SITE}/pelicula/{m['slug']}"} if m.get("slug") else {},
        )
        by_corporate[str(m.get("corporateId"))] = movie
        result.movies.append(movie)

    for s in showtimes:
        movie = by_corporate.get(str(s.get("corporateId")))
        if movie is None:  # función de una película que no está en /movies
            movie = Movie(key=movie_key(s["movieName"]), title=display_title(s["movieName"]))
            by_corporate[str(s.get("corporateId"))] = movie
            result.movies.append(movie)
        local = s["sessionDateTime"]  # "2026-10-21T15:00:00.000Z" (hora local)
        language = (s.get("language") or {}).get("name") or ""
        formats = s.get("formats") or []
        result.sessions.append(Session(
            movie=movie.key,
            cinema=f"cinemark-{s['theaterId']}",
            date=s.get("sessionDisplayDate") or local[:10],
            time=local[11:16],
            format=s.get("sessionFormat") or (formats[0].get("shortName") if formats else ""),
            language=language_from(language) or language,
            room=f"Sala {s['theaterRoom']}" if s.get("theaterRoom") else "",
            url=movie.urls.get("cinemark", SITE),
            late=bool(s.get("isLateNightSession")),
        ))
    return result


def scrape(client: Client) -> SourceResult:
    theaters = client.json(f"{API}/cinema/theaters", params={"limit": 1000}, headers=HEADERS)["data"]
    movies = client.json(f"{API}/cinema/movies", headers=HEADERS)["data"]
    ids = ",".join(str(t["id"]) for t in theaters)
    showtimes = client.json(f"{API}/cinema/showtimes", params={"theater": ids}, headers=HEADERS)["data"]
    return parse(theaters, movies, showtimes)
