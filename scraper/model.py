"""Estructuras comunes a todas las cadenas."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

LIMA = timezone(timedelta(hours=-5))  # Perú no usa horario de verano


def now_lima() -> datetime:
    return datetime.now(LIMA)


@dataclass
class Cinema:
    id: str            # "<cadena>-<id original>"
    chain: str         # cinemark | cinestar | uvk
    name: str
    city: str
    address: str = ""
    url: str = ""


@dataclass
class Movie:
    key: str           # clave normalizada para unir cadenas
    title: str
    poster: str = ""
    duration: int | None = None   # minutos
    rating: str = ""
    urls: dict[str, str] = field(default_factory=dict)  # cadena -> página


@dataclass
class Session:
    movie: str         # Movie.key
    cinema: str        # Cinema.id
    date: str          # AAAA-MM-DD (día de cartelera; la trasnoche cuenta para el día anterior)
    time: str          # HH:MM
    format: str = ""   # 2D, 3D, XD…
    language: str = "" # Doblada | Subtitulada | ""
    room: str = ""
    url: str = ""      # compra o página de la función
    late: bool = False # trasnoche (después de medianoche)


@dataclass
class SourceResult:
    chain: str
    note: str = ""     # advertencia para mostrar en la web
    cinemas: list[Cinema] = field(default_factory=list)
    movies: list[Movie] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)
