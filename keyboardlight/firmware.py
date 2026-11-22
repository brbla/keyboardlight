"""Firmware version check (no flashing – updates are done with the vendors' own tools).

AULA: the official link page https://bit.ly/m/AULA lists firmware downloads; their file names carry the board
code and version, e.g. WIN68HE_…_W669KBSI_SI2828HEARGB_V30821.exe  ->  board W669, version 3.08.21.
Yenkee Odyssey: firmware is not published; the vendor's Windows app updates it online.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

LINK_PAGE = 'https://bit.ly/m/AULA'
UA = 'Mozilla/5.0 (X11; Linux x86_64) KeyBoardLight firmware check'


@dataclass
class FirmwareOffer:
    title: str
    version: str        # "3.08.21"
    url: str            # official download (as linked by AULA)
    filename: str


def _get(url: str, timeout: float = 15) -> tuple[str, str]:
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.geturl(), r.read(2_000_000).decode('utf-8', 'replace')


def _resolve(short: str, timeout: float = 15) -> str:
    """Follow a bit.ly link without downloading the target."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request('https://' + short, headers={'User-Agent': UA}, method='HEAD')
    try:
        opener.open(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        return e.headers.get('Location', '')
    return ''


def version_tuple(v: str) -> tuple[int, ...]:
    """'V3.14.29' -> (3, 14, 29); '30821' (file-name form) -> (3, 8, 21)."""
    v = v.strip().lstrip('Vv')
    if '.' in v:
        return tuple(int(x) for x in v.split('.') if x.isdigit())
    if v.isdigit() and len(v) == 5:
        return int(v[0]), int(v[1:3]), int(v[3:5])
    return ()


def aula_offers(board: str) -> list[FirmwareOffer]:
    """Firmware files on the official AULA link page whose file name contains the board code (e.g. W669)."""
    _url, page = _get(LINK_PAGE)
    entries = re.findall(r'"title":"([^"]+)","description":"[^"]*","is_pinned":[a-z]+,"bitlink":"([^"]+)"', page)
    offers = []
    for title, link in entries:
        if 'firmware' not in title.lower():
            continue
        target = _resolve(link)
        name = urllib.parse.unquote(target.rsplit('/', 2)[-2] if target.endswith('/file') else target.rsplit('/', 1)[-1])
        if board.upper() not in name.upper():
            continue
        m = re.search(r'_V(\d{5})\b|V(\d+\.\d+\.\d+)', name)
        if not m:
            continue
        ver = '.'.join(str(x) for x in version_tuple(m.group(1) or m.group(2)))
        offers.append(FirmwareOffer(title=title, version=ver, url=target, filename=urllib.parse.unquote(name)))
    return offers


def check_aula(info) -> tuple[str, FirmwareOffer | None]:
    """('newer' | 'current' | 'none', best offer)."""
    offers = aula_offers(info.model)
    if not offers:
        return 'none', None
    best = max(offers, key=lambda o: version_tuple(o.version))
    return ('newer' if version_tuple(best.version) > version_tuple(info.version) else 'current'), best
