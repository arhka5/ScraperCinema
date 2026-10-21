"""Ejecuta los scrapers y genera cartelera.json.

    python -m scraper --output out/cartelera.json [--previous anterior.json]

Si una cadena falla, se conservan sus datos de la ejecución anterior (marcados
como desactualizados) para que la web no se quede vacía.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path

from . import cinemark, cinepolis, cinerama, cinestar, uvk
from .client import Client
from .model import Movie, SourceResult, now_lima
from .normalize import similar_keys

SOURCES = {
    "cinemark": cinemark.scrape,
    "cinepolis": cinepolis.scrape,
    "cinestar": cinestar.scrape,
    "uvk": uvk.scrape,
    "cinerama": cinerama.scrape,
}
SCHEMA = 1
# Columnas de cada función en el JSON (formato compacto).
SESSION_FIELDS = ["movie", "cinema", "date", "time", "format", "language", "room", "url", "late"]


def unify_keys(results: list[SourceResult]) -> None:
    """Une claves casi iguales de cadenas distintas (errores de tipeo como
    'street-figther') si las duraciones son compatibles."""
    canonical: dict[str, tuple[str, int | None]] = {}  # clave -> (cadena, duración)
    mapping: dict[tuple[str, str], str] = {}
    for r in results:
        for m in r.movies:
            if m.key in canonical or (r.chain, m.key) in mapping:
                continue
            match = next((k for k, (chain, dur) in canonical.items()
                          if chain != r.chain and similar_keys(k, m.key)
                          and (not dur or not m.duration or abs(dur - m.duration) <= 20)), None)
            if match:
                mapping[(r.chain, m.key)] = match
            else:
                canonical[m.key] = (r.chain, m.duration)
    for r in results:
        for m in r.movies:
            m.key = mapping.get((r.chain, m.key), m.key)
        for s in r.sessions:
            s.movie = mapping.get((r.chain, s.movie), s.movie)


def merge(results: list[SourceResult], today: str) -> dict:
    unify_keys(results)
    cinemas = {c.id: c for r in results for c in r.cinemas}
    sessions = sorted(
        {(s.movie, s.cinema, s.date, s.time, s.room): s
         for r in results for s in r.sessions if s.date >= today and s.cinema in cinemas}.values(),
        key=lambda s: (s.date, s.late, s.time, s.cinema),
    )
    used = {s.movie for s in sessions}

    movies: dict[str, Movie] = {}
    for r in results:
        for m in r.movies:
            if m.key not in used:
                continue
            current = movies.get(m.key)
            if current is None:
                movies[m.key] = Movie(**{**asdict(m), "urls": dict(m.urls)})
                continue
            current.poster = current.poster or m.poster
            current.duration = current.duration or m.duration
            current.rating = current.rating or m.rating
            for chain, url in m.urls.items():
                current.urls.setdefault(chain, url)
            # Preferir el título con tildes y, a igualdad, el más corto.
            def score(title: str) -> tuple[int, int]:
                return sum(not c.isascii() for c in title), -len(title)
            if score(m.title) > score(current.title):
                current.title = m.title

    used_cinemas = {s.cinema for s in sessions}
    rows = []
    for s in sessions:
        row = asdict(s)
        # Si la función enlaza a la misma página que la película, se omite
        # (la web usa la de la película): reduce el JSON casi a la mitad.
        if row["url"] == movies[s.movie].urls.get(cinemas[s.cinema].chain):
            row["url"] = ""
        rows.append([row[f] for f in SESSION_FIELDS])
    return {
        "cinemas": [asdict(c) for c in sorted(cinemas.values(), key=lambda c: (c.chain, c.name))
                    if c.id in used_cinemas],
        "movies": [asdict(m) for m in sorted(movies.values(), key=lambda m: m.title)],
        "sessions": rows,
    }


def from_previous(previous: dict, chain: str) -> SourceResult:
    """Reconstruye los datos de una cadena a partir del JSON anterior."""
    from .model import Cinema, Session
    result = SourceResult(chain)
    ids = {c["id"] for c in previous.get("cinemas", []) if c["chain"] == chain}
    result.cinemas = [Cinema(**c) for c in previous.get("cinemas", []) if c["id"] in ids]
    fields = previous.get("sessionFields", SESSION_FIELDS)
    result.sessions = [Session(**dict(zip(fields, row))) for row in previous.get("sessions", [])
                       if dict(zip(fields, row))["cinema"] in ids]
    used = {s.movie for s in result.sessions}
    result.movies = [Movie(**m) for m in previous.get("movies", []) if m["key"] in used]
    for m in result.movies:  # solo el enlace de esta cadena
        m.urls = {k: v for k, v in m.urls.items() if k == chain}
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Genera la cartelera unificada.")
    parser.add_argument("--output", default="out/cartelera.json")
    parser.add_argument("--previous", help="cartelera.json de la ejecución anterior")
    parser.add_argument("--only", choices=list(SOURCES), action="append")
    args = parser.parse_args(argv)

    previous: dict = {}
    if args.previous and Path(args.previous).exists():
        try:
            previous = json.loads(Path(args.previous).read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            previous = {}

    now = now_lima()
    client = Client()
    results: list[SourceResult] = []
    status: dict[str, dict] = {}
    for chain, scrape in SOURCES.items():
        if args.only and chain not in args.only:
            continue
        started = time.monotonic()
        try:
            result = scrape(client)
            if not result.sessions:
                raise RuntimeError("no se encontraron funciones")
            results.append(result)
            status[chain] = {"ok": True, "updatedAt": now.isoformat(timespec="seconds"),
                             "cinemas": len(result.cinemas), "sessions": len(result.sessions),
                             "seconds": round(time.monotonic() - started, 1)}
            if result.note:
                status[chain]["note"] = result.note
        except Exception as exc:  # una cadena caída no detiene a las demás
            traceback.print_exc()
            old = (previous.get("sources") or {}).get(chain, {})
            fallback = from_previous(previous, chain) if previous else SourceResult(chain)
            results.append(fallback)
            status[chain] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300],
                             "updatedAt": old.get("updatedAt"),
                             "cinemas": len(fallback.cinemas), "sessions": len(fallback.sessions)}

    data = {
        "schema": SCHEMA,
        "generatedAt": now.isoformat(timespec="seconds"),
        "timezone": "America/Lima",
        "sources": status,
        "sessionFields": SESSION_FIELDS,
        **merge(results, now.date().isoformat()),
    }
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    lines = [f"| Cadena | Estado | Cines | Funciones |", "|---|---|---|---|"]
    for chain, s in status.items():
        state = "✅" if s["ok"] else f"⚠️ {s['error']}"
        lines.append(f"| {chain} | {state} | {s['cinemas']} | {s['sessions']} |")
    summary = "\n".join(lines) + (
        f"\n\nTotal: {len(data['movies'])} películas, {len(data['cinemas'])} cines, "
        f"{len(data['sessions'])} funciones · {client.requests} peticiones · "
        f"{out.stat().st_size / 1024:.0f} KB\n")
    print(summary)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(summary)
    # Falla solo si TODAS las cadenas fallaron y no hay nada que publicar.
    return 0 if any(s["ok"] for s in status.values()) or data["sessions"] else 1


if __name__ == "__main__":
    sys.exit(main())
