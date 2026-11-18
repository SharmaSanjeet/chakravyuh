"""Simulates an AI agent walking the maze (follows links, descends in depth,
reads the README and then the .env, downloads binaries). Uses a bot UA to fire
behavioral rules. Not part of the product: it is the e2e test harness.
"""
import os
import re
import time

import httpx

BASE = os.environ.get("CHAKRAVYUH_BASE", "http://localhost:8080")
UA = os.environ.get("CHAKRAVYUH_UA", "python-requests/2.31 (langchain; AutoGPT)")

LINK_RE = re.compile(r'href="([^"]+)"')


def links(html: str, base_path: str) -> list[str]:
    out = []
    for href in LINK_RE.findall(html):
        href = href.split("#", 1)[0].split("?", 1)[0]
        if not href or href.startswith(("../", "http")):
            continue
        if href.startswith("/"):
            out.append(href)
        else:
            out.append(base_path.rstrip("/") + "/" + href if base_path != "/" else "/" + href)
    return out


def main() -> None:
    client = httpx.Client(headers={"User-Agent": UA, "X-Agent-Model": "openrouter/anthropic/claude-haiku"},
                          timeout=10)
    frontier = ["/"]
    seen = set()
    hits = 0
    # Mixed BFS/DFS: follows nearly every link (exhaustive fan-out) and descends deep.
    while frontier and hits < 40:
        path = frontier.pop(0)
        if path in seen:
            continue
        seen.add(path)
        r = client.get(BASE + path)
        hits += 1
        time.sleep(0.4)  # regular interval -> fires cadence_check
        ct = r.headers.get("content-type", "")
        if "html" in ct:
            found = links(r.text, path)
            # Follows EVERYTHING listed (agent behavior, not human).
            frontier.extend(found)
        print(f"{r.status_code}  {path:45.45}  {len(r.content):>7}b  {ct.split(';')[0]}")
    print(f"\nTotal requests by the simulated agent: {hits}")


if __name__ == "__main__":
    main()
