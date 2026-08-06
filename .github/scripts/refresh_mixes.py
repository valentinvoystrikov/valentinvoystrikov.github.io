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

# ID канала добываем САМИ по хэндлу — попытка взять его из адреса
# YouTube Studio закончилась несуществующим UC0ZfP…: RSS отвечал честным
# 404 даже из обычного браузера. Хэндл — то, что видно в шапке канала,
# он проверяемый и стабильный.
HANDLE = "@wellmusic_lofi"
# Качаем сразу вкладку «Видео»: в ней есть и channelId (для RSS), и сам
# список роликов (запасной парсинг, когда RSS молчит)
CHANNEL_URL = f"https://www.youtube.com/{HANDLE}/videos"
CHANNEL_ID_RE = re.compile(r'"(?:channelId|externalId)":"(UC[A-Za-z0-9_-]{22})"')
VIDEO_CHUNK_RE = re.compile(r'"videoRenderer":\{"videoId":"([A-Za-z0-9_-]{11})"')
TITLE_RE = re.compile(r'"title":\{"runs":\[\{"text":"((?:[^"\\]|\\.)*)"')
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
    print(f"источник {url.rsplit('/', 1)[-1]} недоступен ({last})")
    return None


def resolve_channel_id(html: bytes) -> str | None:
    m = CHANNEL_ID_RE.search(html.decode("utf-8", "replace"))
    return m.group(1) if m else None


def scrape_mix_ids(html: bytes) -> list[str]:
    """Миксы прямо со страницы «Видео» — когда RSS-лента отдаёт 404.
    Проверено вживую: для этого канала (создан 2026-08) фид не работает
    ни с раннеров, ни из обычного браузера, а страница отдаётся всем.
    Порядок роликов на вкладке — по дате, свежие первыми."""
    text = html.decode("utf-8", "replace")
    out = []
    for m in VIDEO_CHUNK_RE.finditer(text):
        vid = m.group(1)
        t = TITLE_RE.search(text, m.end(), m.end() + 2000)
        title = t.group(1).encode().decode("unicode_escape") if t else ""
        if MIX_MARKER in title.lower() and vid not in out:
            out.append(vid)
        if len(out) == WANT:
            break
    return out


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
    html = fetch(CHANNEL_URL)
    cid = resolve_channel_id(html) if html else None
    if not cid:
        print(f"::warning::не удалось определить ID канала по {HANDLE} — "
              "миксы не обновлены")
        return 0
    print(f"канал {HANDLE} → {cid}")
    # Один и тот же RSS доступен двумя путями: по каналу и по плейлисту
    # загрузок (UU…). На датацентровые IP YouTube иногда отвечает 404 по
    # одному, но отдаёт другой — пробуем оба.
    xml = None
    for feed in (f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}",
                 f"https://www.youtube.com/feeds/videos.xml?playlist_id=UU{cid[2:]}"):
        xml = fetch(feed)
        if xml is not None:
            break

    if xml is not None:
        ids = latest_mix_ids(xml)
    else:
        print("RSS молчит — берём миксы со страницы «Видео»")
        ids = scrape_mix_ids(html)
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
