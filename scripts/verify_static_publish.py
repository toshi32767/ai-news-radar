#!/usr/bin/env python3
"""Verify the static site without depending on the GitHub API."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CATALYST_JSON = "data/ai-catalyst-stories.json"
INDEX_NEEDLES = ("AI产业催化", "aiCatalystTracks", "aiCatalystList")


@dataclass
class Payload:
    source: str
    text: str


def joined_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def fetch_text(url: str, timeout: float, retries: int) -> Payload:
    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        try:
            request = Request(url, headers={"User-Agent": "ai-news-radar-publish-check/1.0"})
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return Payload(url, response.read().decode(charset, errors="replace"))
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.8 * (attempt + 1))
    raise RuntimeError(f"{url} unavailable: {last_error}") from last_error


def read_local(root: Path, path: str) -> Payload:
    file_path = root / path
    return Payload(str(file_path), file_path.read_text(encoding="utf-8"))


def first_available(candidates: list[tuple[str, Any]]) -> tuple[Payload, list[str]]:
    errors: list[str] = []
    for label, loader in candidates:
        try:
            return loader(), errors
        except Exception as exc:  # noqa: BLE001 - this is a fallback probe.
            errors.append(f"{label}: {exc}")
    raise RuntimeError("; ".join(errors))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://toshi32767.github.io/ai-news-radar/")
    parser.add_argument("--raw-base-url", default="https://raw.githubusercontent.com/toshi32767/ai-news-radar/master/")
    parser.add_argument("--local-root", default=".")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--require-pages", action="store_true", help="Fail if GitHub Pages itself is unavailable.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    local_root = Path(args.local_root)

    index_candidates = [
        ("pages index", lambda: fetch_text(joined_url(args.base_url, "index.html"), args.timeout, args.retries)),
        ("pages root", lambda: fetch_text(args.base_url, args.timeout, args.retries)),
        ("local index", lambda: read_local(local_root, "index.html")),
    ]
    json_candidates = [
        ("pages catalyst json", lambda: fetch_text(joined_url(args.base_url, CATALYST_JSON), args.timeout, args.retries)),
        ("raw catalyst json", lambda: fetch_text(joined_url(args.raw_base_url, CATALYST_JSON), args.timeout, args.retries)),
        ("local catalyst json", lambda: read_local(local_root, CATALYST_JSON)),
    ]

    index_payload, index_errors = first_available(index_candidates)
    json_payload, json_errors = first_available(json_candidates)

    missing = [needle for needle in INDEX_NEEDLES if needle not in index_payload.text]
    if missing:
        raise RuntimeError(f"index missing required markers from {index_payload.source}: {missing}")

    catalyst = json.loads(json_payload.text)
    total = int(catalyst.get("total_catalyst_stories") or 0)
    items = catalyst.get("items") or []
    if total <= 0 or not items:
        raise RuntimeError(f"catalyst json has no mapped stories from {json_payload.source}")

    if args.require_pages and not index_payload.source.startswith(args.base_url.rstrip("/")):
        raise RuntimeError("GitHub Pages index is required but was not available")
    if args.require_pages and not json_payload.source.startswith(args.base_url.rstrip("/")):
        raise RuntimeError("GitHub Pages catalyst json is required but was not available")

    result = {
        "ok": True,
        "index_source": index_payload.source,
        "catalyst_source": json_payload.source,
        "generated_at": catalyst.get("generated_at"),
        "total_catalyst_stories": total,
        "track_counts": catalyst.get("track_counts") or {},
        "fallback_warnings": index_errors + json_errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001 - command-line validation should explain all failures.
        print(f"verify_static_publish failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
