#!/usr/bin/env python3
"""Parallel downloader for figshare file URLs with short-lived S3 redirects."""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import hashlib
import os
from pathlib import Path

import requests


def resolve_location(url: str) -> str:
    response = requests.get(url, allow_redirects=False, timeout=60)
    response.raise_for_status()
    location = response.headers.get("Location")
    if not location:
        return url
    return location


def download_part(url: str, part_path: Path, start: int, end: int) -> None:
    if part_path.exists() and part_path.stat().st_size == end - start + 1:
        return
    headers = {"Range": f"bytes={start}-{end}"}
    with requests.get(url, headers=headers, stream=True, timeout=120) as response:
        if response.status_code not in (200, 206):
            raise RuntimeError(f"range {start}-{end} failed with HTTP {response.status_code}")
        tmp = part_path.with_suffix(part_path.suffix + ".tmp")
        with tmp.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
        os.replace(tmp, part_path)
    size = part_path.stat().st_size
    expected = end - start + 1
    if size != expected:
        raise RuntimeError(f"{part_path} has {size} bytes, expected {expected}")


def md5sum(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024 * 16), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--size", required=True, type=int)
    parser.add_argument("--md5", default="")
    parser.add_argument("--parts", type=int, default=16)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    part_dir = args.output.with_name(args.output.name + ".parts")
    part_dir.mkdir(parents=True, exist_ok=True)

    signed_url = resolve_location(args.url)
    part_size = (args.size + args.parts - 1) // args.parts
    jobs = []
    for i in range(args.parts):
        start = i * part_size
        end = min(args.size - 1, start + part_size - 1)
        if start > end:
            continue
        jobs.append((i, start, end, part_dir / f"part_{i:03d}"))

    with futures.ThreadPoolExecutor(max_workers=args.parts) as pool:
        submitted = [
            pool.submit(download_part, signed_url, part_path, start, end)
            for _, start, end, part_path in jobs
        ]
        for fut in futures.as_completed(submitted):
            fut.result()

    tmp_out = args.output.with_suffix(args.output.suffix + ".tmp")
    with tmp_out.open("wb") as out:
        for _, _, _, part_path in jobs:
            with part_path.open("rb") as part:
                for chunk in iter(lambda: part.read(1024 * 1024 * 16), b""):
                    out.write(chunk)
    os.replace(tmp_out, args.output)

    actual_size = args.output.stat().st_size
    if actual_size != args.size:
        raise RuntimeError(f"assembled file has {actual_size} bytes, expected {args.size}")
    if args.md5:
        actual_md5 = md5sum(args.output)
        if actual_md5 != args.md5:
            raise RuntimeError(f"md5 mismatch: {actual_md5} != {args.md5}")
        print(f"md5 OK: {actual_md5}")
    print(f"downloaded: {args.output} ({actual_size} bytes)")


if __name__ == "__main__":
    main()
