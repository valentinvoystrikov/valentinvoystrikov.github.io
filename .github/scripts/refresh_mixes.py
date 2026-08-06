#!/usr/bin/env python3
"""Подставить в index.html id двух свежих миксов канала.

Источник — публичный RSS канала (ключ API не нужен, квоты нет). В ленте
вперемешку Shorts с отдельными треками и длинные миксы, поэтому берём
только записи с MIX_MARKER в названии: миксы всегда называются
«… Mix Vol. N» (wellmusic/pipeline.py), у треков названия песенные.

Ничего не трогаем, если лента недоступна или подходящих роликов не
нашлось: лучше оставить прошлые миксы, чем стереть их пустотой.
"""

import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CHANNEL_ID = "UC0ZfP-xuh9qyUlNOUKJhLEA"
FEED = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
MIX_MARKER = "mix vol."
WANT = 2
PAGE = Path(__file__).resolve().parents[2] / "index.html"
LINE = re.compile(r"^(?P<pre>\s*MIXES:\s*)\[[^\]]*\](?P<post>,\s*/\* auto \*/\s*)$",
                  re.M)
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}


def latest_mix_ids(xml: bytes) -> list[str]:
    root = ET.fromstring(xml)
    out = []
    for entry in root.findall("a:entry", NS):
        title = (entry.findtext("a:title", "", NS) or "")
        vid = (entry.findtext("yt:videoId", "", NS) or "").strip()
        if MIX_MARKER in title.lower() and VIDEO_ID.match(vid) and vid not in out:
            out.append(vid)
        if len(out) == WANT:
            break
    return out


def main() -> int:
    try:
        with urllib.request.urlopen(FEED, timeout=30) as resp:
            xml = resp.read()
    except Exception as e:
        print(f"лента недоступна ({e}) — страницу не трогаем")
        return 0

    ids = latest_mix_ids(xml)
    if not ids:
        print("миксов в ленте не нашлось — страницу не трогаем")
        return 0

    page = PAGE.read_text(encoding="utf-8")
    if not LINE.search(page):
        print("не найдена строка MIXES с маркером /* auto */", file=sys.stderr)
        return 1

    listing = ", ".join(f'"{i}"' for i in ids)
    new = LINE.sub(lambda m: f"{m['pre']}[{listing}]{m['post']}", page)
    if new == page:
        print(f"уже актуально: {ids}")
        return 0
    PAGE.write_text(new, encoding="utf-8")
    print(f"обновлено: {ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
