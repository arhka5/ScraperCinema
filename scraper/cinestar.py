"""Cinestar: web en SvelteKit. Cada página expone sus datos en `__data.json`,
codificados con *devalue* (un arreglo plano con referencias por índice)."""
from __future__ import annotations

from datetime import date, timedelta

from .client import Client
from .model import Cinema, Movie, Session, SourceResult
from .normalize import display_title, guess_city, language_from, movie_key

SITE = "https://www.cinestar.com.pe"
# Las imágenes "/bucket/images/…" del sitio son las mismas del bucket público.
BUCKET = "https://bucket.tumi-soft.com/images.tumisoft/"


def devalue(flat: list):
    """Decodifica el formato devalue de SvelteKit a objetos de Python."""
    cache: dict[int, object] = {}

    def resolve(i: int):
        if i < 0:  # -1 undefined, -2 hueco, -3 NaN, -4 Inf, -5 -Inf, -6 -0
            return None
        if i in cache:
            return cache[i]
        value = flat[i]
        if isinstance(value, dict):
            obj: dict = {}
            cache[i] = obj
            for k, j in value.items():
                obj[k] = resolve(j)
            return obj
        if isinstance(value, list):
            if value and isinstance(value[0], str):  # ["Date", "…"], ["Set", …]…
                kind = value[0]
                if kind in ("Date", "BigInt", "RegExp", "URL"):
                    return value[1] if len(value) > 1 else None
                return [resolve(j) for j in value[1:]]
            arr: list = []
            cache[i] = arr
            arr.extend(resolve(j) for j in value)
            return arr
        return value

    return resolve(0)


def image_url(path: str | None) -> str:
    if not path:
        return ""
    if path.startswith("http"):
        return path
    if path.startswith("/bucket/images/"):
        return BUCKET + path[len("/bucket/images/"):]
    return SITE + path


def parse_branch(branch: dict, payload: dict) -> SourceResult:
    """`branch` viene de /cinemas; `payload` es el __data.json de su página."""
    result = SourceResult("cinestar")
    cinema = Cinema(
        id=f"cinestar-{branch['id']}",
        chain="cinestar",
        name=f"Cinestar {branch['name'].title()}",
        city=guess_city(branch.get("name", ""), branch.get("address", "")),
        address=(branch.get("address") or "").strip(),
        url=f"{SITE}/cinemas/{branch['slug']}",
    )
    result.cinemas.append(cinema)

    presentation = None
    for node in payload.get("nodes") or []:
        if node and node.get("type") == "data":
            data = devalue(node["data"])
            if isinstance(data, dict) and "presentation" in data:
                presentation = data["presentation"]
    if not presentation:
        return result

    for item in presentation.get("items") or []:
        shows = [s for s in item.get("showTimes") or [] if s.get("status", 1) == 1]
        if not shows:
            continue
        name = item["name"]
        movie = Movie(
            key=movie_key(name),
            title=display_title(name),
            poster=image_url(item.get("urlImage")),
            duration=item.get("duration") or None,
            rating=(item.get("rating") or {}).get("code") or "",
            urls={"cinestar": f"{SITE}/peliculas/{item['slug']}"} if item.get("slug") else {},
        )
        result.movies.append(movie)
        language = language_from(name)
        for s in shows:
            time = (s.get("time") or "")[:5]
            if not time:
                continue
            room = (s.get("layoutCode") or "").lstrip("0")
            # Cinestar usa la fecha del calendario; la trasnoche (00:00–04:59)
            # se asigna al día anterior, como hace Cinemark y como se anuncia.
            day = s["date"]
            if time < "05:00":
                day = (date.fromisoformat(day) - timedelta(days=1)).isoformat()
            result.sessions.append(Session(
                movie=movie.key,
                cinema=cinema.id,
                date=day,
                time=time,
                format="3D" if item.get("is3d") else "2D",
                language=language,
                room=f"Sala {room}" if room else "",
                url=movie.urls.get("cinestar", cinema.url),
                late=time < "05:00",
            ))
    return result


def scrape(client: Client) -> SourceResult:
    branches = client.json(f"{SITE}/cinemas")["branches"]
    result = SourceResult("cinestar")
    for branch in branches:
        part = parse_branch(branch, client.json(f"{SITE}/cinemas/{branch['slug']}/__data.json"))
        result.cinemas += part.cinemas
        result.movies += part.movies
        result.sessions += part.sessions
    return result
