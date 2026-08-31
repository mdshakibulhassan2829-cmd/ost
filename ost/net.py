from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Callable, Optional

try:
    import httpx
    HAS_HTTPX = True
except ImportError:  # pragma: no cover
    httpx = None
    HAS_HTTPX = False

ProgressCb = Callable[[int, Optional[int]], None]


async def fetch(url: str, timeout: float = 60, headers: Optional[dict] = None) -> str:
    if HAS_HTTPX:
        h = dict(headers or {})
        h.setdefault("User-Agent", "OST/0.1 (office suite toolkit)")
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            r = await client.get(url, headers=h)
            r.raise_for_status()
            return r.text
    return await asyncio.to_thread(_fetch_urllib, url, timeout, headers)


def _fetch_urllib(url: str, timeout: float, headers: Optional[dict]) -> str:
    import time
    import urllib.error
    import urllib.request

    h = dict(headers or {})
    h.setdefault("User-Agent", "OST/0.1 (office suite toolkit)")
    last: Exception | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            last = e
            time.sleep(0.5 * (attempt + 1))
    raise last


async def head(url: str, timeout: float = 45) -> Optional[dict]:
    try:
        if HAS_HTTPX:
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers={"User-Agent": "OST/0.1"}) as client:
                r = await client.head(url)
                r.raise_for_status()
                return {k.lower(): v for k, v in r.headers.items()}
        return await asyncio.to_thread(_head_urllib, url, timeout)
    except Exception:
        return None


def _head_urllib(url: str, timeout: float) -> Optional[dict]:
    import urllib.request

    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "OST/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return {k.lower(): v for k, v in resp.headers.items()}


async def head_size(url: str) -> int:
    info = await head(url)
    if not info:
        return 0
    try:
        return int(info.get("content-length", "0"))
    except ValueError:
        return 0


async def probe(url: str, timeout: float = 60) -> Optional[dict]:
    """Fetch the first bytes of a URL to decide whether it is a file or a page.

    Returns dict(final_url, first_bytes, content_length, content_disposition,
    content_type) or None when the request fails or the server answers HTML.
    """
    if HAS_HTTPX:
        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=timeout,
                headers={"User-Agent": _UA, "Range": "bytes=0-2047"},
            ) as client:
                async with client.stream("GET", url) as r:
                    if r.status_code >= 400:
                        return None
                    content_type = r.headers.get("content-type", "")
                    if content_type.startswith("text/html"):
                        return None
                    buf = b""
                    async for chunk in r.aiter_bytes(2048):
                        buf += chunk
                        if len(buf) >= 2048:
                            break
                    return {
                        "final_url": str(r.url),
                        "first_bytes": buf,
                        "content_length": _int_or(r.headers.get("content-length"), 0),
                        "content_disposition": r.headers.get("content-disposition", ""),
                        "content_type": content_type,
                    }
        except Exception:
            return None
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={"User-Agent": _UA, "Range": "bytes=0-2047"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content_type = resp.headers.get("Content-Type", "")
            if content_type.startswith("text/html"):
                return None
            buf = resp.read(2048)
            return {
                "final_url": resp.geturl(),
                "first_bytes": buf,
                "content_length": _int_or(resp.headers.get("Content-Length"), 0),
                "content_disposition": resp.headers.get("Content-Disposition", ""),
                "content_type": content_type,
            }
    except Exception:
        return None


_UA = "OST/0.1 (office suite toolkit)"


def _int_or(v: str | None, default: int) -> int:
    try:
        return int(str(v))
    except (ValueError, TypeError):
        return default


async def download(
    url: str,
    dest: Path,
    progress: Optional[ProgressCb] = None,
    resume: bool = False,
    timeout: float = 120,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    size = await head_size(url)
    if HAS_HTTPX:
        await _download_httpx(url, dest, size, progress, resume, timeout)
    else:
        await asyncio.to_thread(_download_urllib, url, dest, size, progress, resume, timeout)
    return dest


async def _download_httpx(
    url: str,
    dest: Path,
    size: int,
    progress: Optional[ProgressCb],
    resume: bool,
    timeout: float,
) -> None:
    headers = {"User-Agent": "OST/0.1 (office suite toolkit)"}
    mode = "ab" if (resume and dest.exists()) else "wb"
    if mode == "ab":
        headers["Range"] = f"bytes={dest.stat().st_size}-"
    done = dest.stat().st_size if mode == "ab" else 0
    if progress:
        progress(done, size)
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        async with client.stream("GET", url, headers=headers) as r:
            r.raise_for_status()
            with open(dest, mode) as fh:
                async for chunk in r.aiter_bytes(65536):
                    fh.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, size)


def _download_urllib(
    url: str,
    dest: Path,
    size: int,
    progress: Optional[ProgressCb],
    resume: bool,
    timeout: float,
) -> None:
    import urllib.request

    headers = {"User-Agent": "OST/0.1 (office suite toolkit)"}
    mode = "ab" if (resume and dest.exists()) else "wb"
    src = dest.stat().st_size if mode == "ab" else 0
    if mode == "ab":
        headers["Range"] = f"bytes={src}-"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, mode) as fh:
        done = src
        if progress:
            progress(done, size)
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, size)