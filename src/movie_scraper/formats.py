"""How a showing is projected, and in what language, normalized across theaters.

Corey's rule (Nov 2026): only formats people choose a showing for get named. Film prints (16mm,
35mm, 70mm, VistaVision), IMAX (incl. IMAX 70mm and IMAX 3D), Dolby Cinema ("Dolby", "Dolby 3D")
and 3D. Every other premium screen (AMC Prime, RPX, 4DX, ScreenX, Harkins Ciné XL, …) is
theater-specific branding, so it's just "PLF" (premium large format). Laser projection, Atmos
sound, recliners and aspect ratios (Scope / Flat) aren't formats and are dropped.

Language: subtitled vs dubbed matters (anime especially), so it's kept separately.
"""
from __future__ import annotations

import re

_GAUGE = re.compile(r"\b(16|35|70)\s?mm\b", re.I)
# Branded premium screens: all "PLF". Matched as substrings of the lowercased label.
_PLF = ("premium format", "prime at amc", "4dx", "screenx", "rpx", "ciné xl", "cine xl", "d-box",
        "cinemark xd", "superscreen", "ultrascreen", "plf")


def canon(names: list[str], three_d: bool = False) -> str | None:
    """One label for a showing from its source labels; None for an ordinary 2D digital showing."""
    low = [(n or "").strip().lower() for n in names if n]
    gauges = {m.group(1) for n in low for m in [_GAUGE.search(n)] if m}
    imax = any("imax" in n for n in low)
    dolby = any(n.startswith("dolby") and "atmos" not in n for n in low)   # Dolby Cinema, not just sound
    three_d = three_d or any(re.search(r"(^|\W)3d\b", n) for n in low)
    if imax and "70" in gauges:
        return "IMAX 70mm"
    if gauges:                      # a film print: the gauge is what matters
        return f"{max(gauges, key=int)}mm"
    if any("vistavision" in n for n in low):
        return "VistaVision"
    base = "IMAX" if imax else "Dolby" if dolby else None
    if three_d:
        return f"{base} 3D" if base else "3D"
    if base:
        return base
    if any(p in n for n in low for p in _PLF):
        return "PLF"
    return None


PRINTS = {"16mm", "35mm", "70mm", "IMAX 70mm", "VistaVision"}


def on_film(fmt: str | None) -> bool:
    """Projected from a film print (the site's "On film")."""
    return fmt in PRINTS


def language(names: list[str]) -> str | None:
    """"Subtitled" or "Dubbed" (with the language when it isn't English: "Spanish dub"), else None.

    Sources only flag the exceptions (Fandango: "Japanese with English Subtitles", "Spanish Dubbed",
    "English Subtitles"), so an untagged showing of a foreign film can be either.
    """
    for n in names:
        s = (n or "").strip()
        m = re.match(r"(?i)^(\w+)\s+dub(bed)?$", s)
        if m:
            lang = m.group(1).capitalize()
            return "Dubbed" if lang == "English" else f"{lang} dub"
        if re.search(r"(?i)\bdubbed\b", s):
            return "Dubbed"
    if any(re.search(r"(?i)\bsubtitle[sd]?\b|\bsubbed\b", n or "") for n in names):
        return "Subtitled"
    return None
