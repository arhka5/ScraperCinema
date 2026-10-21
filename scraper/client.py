"""Cliente HTTP "educado": se identifica, espera entre peticiones al mismo
sitio y reintenta con calma ante errores temporales."""
from __future__ import annotations

import json as jsonlib
import time
from urllib.parse import urlparse

import requests

USER_AGENT = "CarteleraPeruBot/1.0 (+https://github.com/arhka5/ScraperCinema)"
TIMEOUT = 30
RETRY_STATUS = {429, 500, 502, 503, 504}


class Client:
    def __init__(self, delay: float = 1.0, retries: int = 2):
        self.delay = delay
        self.retries = retries
        self._last: dict[str, float] = {}
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": USER_AGENT,
            "Accept-Language": "es-PE,es;q=0.9",
        })
        self.requests = 0

    def _wait(self, host: str) -> None:
        elapsed = time.monotonic() - self._last.get(host, 0)
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last[host] = time.monotonic()

    def get(self, url: str, *, params=None, headers=None, method: str = "GET",
            json=None) -> requests.Response:
        host = urlparse(url).netloc
        for attempt in range(self.retries + 1):
            self._wait(host)
            self.requests += 1
            try:
                response = self.session.request(method, url, params=params, headers=headers,
                                                json=json, timeout=TIMEOUT)
            except (requests.ConnectionError, requests.Timeout):
                if attempt == self.retries:
                    raise
                time.sleep(5 * (attempt + 1))
                continue
            if response.status_code in RETRY_STATUS and attempt < self.retries:
                retry_after = response.headers.get("Retry-After", "")
                time.sleep(int(retry_after) if retry_after.isdigit() else 5 * (attempt + 1))
                continue
            response.raise_for_status()
            return response
        raise RuntimeError("inalcanzable")

    def json(self, url: str, **kwargs):
        headers = {"Accept": "application/json", **(kwargs.pop("headers", None) or {})}
        # utf-8-sig: algunos sitios anteponen un BOM que rompe el parser.
        return jsonlib.loads(self.get(url, headers=headers, **kwargs).content.decode("utf-8-sig"))

    def text(self, url: str, **kwargs) -> str:
        headers = {"Accept": "text/html,application/xhtml+xml", **(kwargs.pop("headers", None) or {})}
        response = self.get(url, headers=headers, **kwargs)
        response.encoding = response.encoding or "utf-8"
        if response.encoding.lower() in {"iso-8859-1", "latin-1"}:
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text
