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
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CHANNEL_ID = "UC0ZfP-xuh9qyUlNOUKJhLEA"
# Один и тот же RSS доступен двумя путями: по каналу и по его плейлисту
# загрузок (UU…). На датацентровые IP YouTube иногда отвечает 404 по
# одному пути, но отдаёт другой — пробуем оба.
FEEDS = [
    f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}",
    f"https://www.youtube.com/feeds/videos.xml?playlist_id=UU{CHANNEL_ID[2:]}",
]
MIX_MARKER = "mix vol."
WANT = 2
PAGE = Path(__file__).resolve().parents[2] / "index.html"
LINE = re.compile(r"^(?P<pre>\s*MIXES:\s*)\[[^\]]*\](?P<post>,\s*/\* auto \*/\s*)$",
                  re.M)
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
NS = {"a": "http://www.w3.org/2005/Atom", "yt": "http://www.youtube.com/xml/schemas/2015"}

# YouTube отвечает 500 на запросы, представившиеся как Python-urllib, —
# из дата-центров такие он отшивает. Прикидываемся обычным браузером.
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Accept": "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
ATTEMPTS = 3
PAUSE = 5.0


def fetch(url: str) -> bytes | None:
    """Лента с повторами: 500 у YouTube бывает и разовым."""
    last = ""
    for n in range(1, ATTEMPTS + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            print(f"попытка {n}/{ATTEMPTS} не удалась — {last}")
            if n < ATTEMPTS:
                time.sleep(PAUSE)
    print(f"источник {url.split('?')[1]} недоступен ({last})")
    return None


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
    xml = None
    for feed in FEEDS:
        xml = fetch(feed)
        if xml is not None:
            break
    if xml is None:
        # ::warning:: подсвечивает прогон в интерфейсе Actions: зелёная
        # галочка на ничего не сделавшем запуске вводит в заблуждение
        print("::warning::оба источника ленты недоступны, миксы не обновлены")
        return 0

    ids = latest_mix_ids(xml)
    if not ids:
        print("::warning::в ленте нет роликов с «Mix Vol.» в названии — "
              "миксы не обновлены")
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
