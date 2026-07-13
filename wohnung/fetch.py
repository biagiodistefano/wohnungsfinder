from __future__ import annotations

import time

import httpx

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


class BlockedError(RuntimeError):
    """Raised when a source responds with a bot-block status (403/429)."""


class Fetcher:
    def __init__(self, transport=None, timeout=25.0, retries=2):
        self._client = httpx.Client(
            headers={"User-Agent": UA, "Accept-Language": "de-AT,de;q=0.9"},
            follow_redirects=True,
            timeout=timeout,
            transport=transport,
        )
        self.retries = retries

    def get(self, url: str, params: dict | None = None) -> str:
        last: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                r = self._client.get(url, params=params)
                if r.status_code in (403, 429):
                    raise BlockedError(f"{r.status_code} for {url}")
                r.raise_for_status()
                return r.text
            except BlockedError:
                raise
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                last = e
                time.sleep(0.5 * (attempt + 1))
        raise last if last else RuntimeError("unreachable")

    def get_bytes(self, url: str) -> bytes:
        r = self._client.get(url)
        r.raise_for_status()
        return r.content

    def close(self):
        self._client.close()
