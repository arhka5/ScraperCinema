"""UVK Multicines: páginas HTML generadas en el servidor.

/peliculas lista las películas; la página de cada una tiene pestañas por
fecha y, en cada pestaña, los cines con sus funciones por idioma y sala.
"""
from __future__ import annotations

import re
from datetime import date
from urllib.parse import quote, unquote, urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from .client import Client
from .model import Cinema, Movie, Session, SourceResult, now_lima
from .normalize import display_title, guess_city, language_from, movie_key, parse_minutes, to_24h

SITE = "https://www.uvk.pe"
_MOVIE_LINK = re.compile(r"/peliculas/(\d+)/")


def movie_links(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        m = _MOVIE_LINK.search(a["href"])
        if m and m.group(1) not in links:
            href = urljoin(SITE + "/", a["href"])
            links[m.group(1)] = quote(href, safe=":/?=&%")
    return list(links.values())


def tab_date(label: str, today: date) -> str | None:
    """'Miércoles 21/10' → '2026-10-21' (el año se deduce de hoy)."""
    m = re.search(r"(\d{1,2})/(\d{1,2})", label)
    if not m:
        return None
    day, month = int(m.group(1)), int(m.group(2))
    year = today.year
    if month < today.month - 6:   # diciembre → enero
        year += 1
    elif month > today.month + 6:
        year -= 1
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_movie(html: str, url: str, today: date | None = None) -> SourceResult:
    today = today or now_lima().date()
    soup = BeautifulSoup(html, "html.parser")
    result = SourceResult("uvk")

    heading = soup.select_one(".book-section .featured-title") or soup.select_one("h3.featured-title")
    raw_title = heading.get_text(" ", strip=True) if heading else unquote(url.rstrip("/").rsplit("/", 1)[-1])
    tags = [t.get_text(strip=True) for t in soup.select(".book-section .language-tag")]
    poster = soup.select_one("img.movie-poster")
    duration = soup.select_one(".date-and-duration")
    ratings = [t for t in tags if re.fullmatch(r"(APT|PG-?\d*|G|R|NC-17|\+?\d{1,2}|M\d+)", t, re.I)]

    movie = Movie(
        key=movie_key(raw_title),
        title=display_title(raw_title),
        poster=urljoin(SITE + "/", poster["src"]) if poster and poster.get("src") else "",
        duration=parse_minutes(duration.get_text(" ", strip=True)) if duration else None,
        rating=ratings[0] if ratings else "",
        urls={"uvk": url},
    )
    result.movies.append(movie)

    tabs = soup.select(".show-search .tab-menu li")
    items = soup.select(".show-search .tab-area > .tab-item")
    cinemas: dict[str, Cinema] = {}
    for tab, item in zip(tabs, items):
        day = tab_date(tab.get_text(" ", strip=True), today)
        if not day:
            continue
        for block in item.select(".cinema-shows"):
            titles = block.select(".cinema-title")
            if not titles:
                continue
            name = titles[0].get_text(" ", strip=True)
            address = titles[1].get_text(" ", strip=True) if len(titles) > 1 else ""
            cid = f"uvk-{_slug(re.sub(r'^UVK\s+', '', name, flags=re.I))}"
            if cid not in cinemas:
                pretty = re.sub(r"^UVK\s+", "", name, flags=re.I).title()
                cinemas[cid] = Cinema(id=cid, chain="uvk", name=f"UVK {pretty}",
                                      city=guess_city(name, address), address=address,
                                      url=f"{SITE}/cines")
            for group in block.select(".show-types"):
                feature = group.select_one(".show-features")
                feature_text = feature.get_text(" ", strip=True) if feature else ""
                show_list = group.select_one(".show-list")
                if not show_list:
                    continue
                room = ""
                for node in show_list.children:
                    if isinstance(node, NavigableString):
                        m = re.search(r"Sala\s*\w+", str(node))
                        if m:
                            room = m.group(0)
                    elif isinstance(node, Tag) and node.name == "a":
                        time = to_24h(node.get_text(" ", strip=True))
                        if not time:
                            continue
                        result.sessions.append(Session(
                            movie=movie.key,
                            cinema=cid,
                            date=day,
                            time=time,
                            format="3D" if "3D" in feature_text.upper() else "2D",
                            language=language_from(feature_text),
                            room=room,
                            url=quote(urljoin(SITE + "/", node.get("href", "")), safe=":/?=&%") or url,
                            late=time < "05:00",
                        ))
    result.cinemas = list(cinemas.values())
    return result


def scrape(client: Client) -> SourceResult:
    result = SourceResult("uvk")
    seen: set[str] = set()
    for url in movie_links(client.text(f"{SITE}/peliculas")):
        part = parse_movie(client.text(url), url)
        result.movies += part.movies
        result.sessions += part.sessions
        for c in part.cinemas:
            if c.id not in seen:
                seen.add(c.id)
                result.cinemas.append(c)
    return result
