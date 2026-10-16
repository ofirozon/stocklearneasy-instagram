#!/usr/bin/env python3
"""Item 55: the profile grid as a visitor sees it.

Pulls the last 12 posts from the Graph API and lays out their thumbnails
cropped to 3:4, the shape the profile grid uses for every tile. The first run
(16.10.2026) found every news reel sitting in the grid as a black square and
every square carousel missing the first letter of its hook. Neither shows up
when you look at the posts one at a time.

    python grid_audit.py [out.jpg]
"""
import io
import json
import subprocess
import sys
import urllib.request

from PIL import Image

GRAPH = "https://graph.instagram.com/v21.0"
TILE_W, TILE_H, GAP = 300, 400, 4


def keychain(service):
    return subprocess.run(
        ["security", "find-generic-password", "-a", "stocklearneasy", "-s", service, "-w"],
        capture_output=True, text=True).stdout.strip()


def tile(im):
    w, h = im.size
    if w / h > 3 / 4:
        cw = int(h * 3 / 4)
        im = im.crop(((w - cw) // 2, 0, (w - cw) // 2 + cw, h))
    else:
        ch = int(w * 4 / 3)
        im = im.crop((0, (h - ch) // 2, w, (h - ch) // 2 + ch))
    return im.resize((TILE_W, TILE_H))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "grid-audit.jpg"
    token, user = keychain("stocklearneasy-ig-token"), keychain("stocklearneasy-ig-user-id")
    media = json.load(urllib.request.urlopen(
        f"{GRAPH}/{user}/media?fields=media_product_type,thumbnail_url,media_url,timestamp"
        f"&limit=12&access_token={token}"))["data"]
    grid = Image.new("RGB", (3 * TILE_W + 2 * GAP, 4 * TILE_H + 3 * GAP), "white")
    for i, m in enumerate(media[:12]):
        url = m.get("thumbnail_url") or m.get("media_url")
        im = Image.open(io.BytesIO(urllib.request.urlopen(url).read())).convert("RGB")
        grid.paste(tile(im), ((i % 3) * (TILE_W + GAP), (i // 3) * (TILE_H + GAP)))
        print(m["timestamp"][:16], m["media_product_type"])
    grid.save(out, quality=88)
    print(out)


if __name__ == "__main__":
    main()
