#!/usr/bin/env python3
"""
Download a GTFS feed and save it to disk.

This script fetches a GTFS ZIP from a provided URL, writes the file
into a destination directory and produces a corresponding SHA‑256
checksum file.  It is intended to be used as part of a scheduled
workflow (for example in GitHub Actions).  The URL and output
directory are provided via command‑line arguments.

Example:

```
python scripts/download_gtfs.py --url "https://example.com/feed.zip" --outdir data/gtfs
```

If authentication is required (for example an ODPT API token) it can
be passed via environment variables or added as an HTTP header.  This
prototype does not implement authentication.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from urllib.parse import urlparse

import requests


def download_file(url: str) -> bytes:
    """Fetch the content at ``url`` and return it as bytes.

    Raises a ``requests.HTTPError`` if the request fails.
    """
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def write_file(path: str, data: bytes) -> None:
    """Write binary data to a file, creating parent directories if needed."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def compute_sha256(data: bytes) -> str:
    """Compute the SHA‑256 digest of ``data`` and return it as a hex string."""
    digest = hashlib.sha256()
    digest.update(data)
    return digest.hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download a GTFS ZIP and compute its SHA‑256 hash.")
    parser.add_argument("--url", required=True, help="URL of the GTFS ZIP file")
    parser.add_argument(
        "--outdir", default="data/gtfs", help="Directory into which the file will be downloaded"
    )
    args = parser.parse_args(argv)

    url = args.url
    outdir = args.outdir
    # Determine a filename from the URL path
    filename = os.path.basename(urlparse(url).path) or "feed.zip"
    out_path = os.path.join(outdir, filename)
    sha_path = out_path + ".sha256"

    try:
        data = download_file(url)
    except requests.HTTPError as exc:
        print(f"Failed to download {url}: {exc}", file=sys.stderr)
        return 1

    write_file(out_path, data)
    checksum = compute_sha256(data)
    with open(sha_path, "w", encoding="utf-8") as fh:
        fh.write(checksum)
    print(f"Downloaded {url} to {out_path}")
    print(f"SHA-256: {checksum}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
