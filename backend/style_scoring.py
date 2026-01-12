from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# -----------------------------
# Normalization helpers
# -----------------------------
def normalize_color(c: Optional[str]) -> str:
    if not c:
        return "unknown"
    
    if not isinstance(c, str):
        c = str(c)
        
    c = c.strip().lower()  # Now this is safe
    
    # common aliases
    aliases = {
        "grey": "gray",
        "navy": "blue",
        "offwhite": "white",
        "ivory": "white",
        "tan": "beige",
        "camel": "beige",
        "maroon": "red",
    }
    return aliases.get(c, c)


def normalize_category(cat: Optional[str]) -> str:
    """Map raw categories to a small set used by the generator."""
    if not cat:
        return "unknown"
    
    # ADDED: Ensure cat is a string
    if not isinstance(cat, str):
        cat = str(cat)
        
    c = cat.strip().lower()  

    # shoes
    if any(k in c for k in ["shoe", "sneaker", "heel", "boot", "loafer", "sandals", "footwear"]):
        return "shoes"

    # dresses
    if "dress" in c or "robe" in c or "gown" in c:
        return "dress"

    # accessories
    if any(k in c for k in ["watch", "belt", "bag", "scarf", "jewelry", "accessory", "hat", "cap", "glasses", "sunglasses"]):
        return "accessory"

    # bottoms
    if any(k in c for k in ["jean", "pant", "trouser", "skirt", "short", "legging", "bottom"]):
        return "bottom"

    # outerwear
    if any(k in c for k in ["jacket", "coat", "blazer", "veste", "hoodie", "sweater", "cardigan", "outerwear"]):
        return "outerwear"

    # tops
    if any(k in c for k in ["shirt", "tee", "t-shirt", "top", "blouse", "sweater", "pull", "tank", "polo"]):
        return "top"

    return c  


def _get(doc: Dict[str, Any], key: str, default: Any = None) -> Any:
    v = doc.get(key)
    return default if v is None else v


# -----------------------------
# Weather profile
# -----------------------------


@dataclass(frozen=True)
class WeatherProfile:
    temp_c: float
    condition: str
    bucket: str  # cold/mild/warm/hot
    label: str


def build_weather_profile(weather: Dict[str, Any]) -> WeatherProfile:
    temp = weather.get("temp_c")
    try:
        t = float(temp)
    except Exception:
        t = 22.0
    cond = str(weather.get("condition") or "clear").strip().lower()

    if t <= 12:
        bucket = "cold"
    elif t <= 20:
        bucket = "mild"
    elif t <= 28:
        bucket = "warm"
    else:
        bucket = "hot"

    city = weather.get("city") or ""
    label = f"{t:.0f}°C {cond}{(' in ' + city) if city else ''}".strip()
    return WeatherProfile(temp_c=t, condition=cond, bucket=bucket, label=label)


# -----------------------------
# Scoring (fast, rule-based)
# -----------------------------


NEUTRALS = {"black", "white", "gray", "beige", "brown", "navy", "blue"}


def _color_harmony(a: str, b: str) -> float:
    """Cheap harmony score in [0..1]."""
    a, b = normalize_color(a), normalize_color(b)
    if a == "unknown" or b == "unknown":
        return 0.55
    if a == b:
        return 0.7
    if a in NEUTRALS or b in NEUTRALS:
        return 0.85
    # some pleasant combos
    good_pairs = {
        ("blue", "white"),
        ("blue", "beige"),
        ("red", "black"),
        ("green", "white"),
        ("pink", "white"),
        ("purple", "black"),
        ("yellow", "blue"),
    }
    if (a, b) in good_pairs or (b, a) in good_pairs:
        return 0.8
    return 0.45


def _formality_score(doc: Dict[str, Any], occasion: str) -> float:
    occ = (occasion or "").lower()
    formality = str(_get(doc, "formality", "casual") or "casual").lower()

    want = "casual"
    if any(k in occ for k in ["wedding", "gala", "formal", "ceremony"]):
        want = "formal"
    elif any(k in occ for k in ["interview", "office", "work", "meeting", "business"]):
        want = "business"
    elif any(k in occ for k in ["date", "party", "anniversary"]):
        want = "business-casual"

    # map to levels
    lvl = {"casual": 0, "business-casual": 1, "business": 2, "formal": 3}
    a = lvl.get(formality, 0)
    b = lvl.get(want, 0)
    diff = abs(a - b)
    return {0: 1.0, 1: 0.8, 2: 0.55, 3: 0.35}.get(diff, 0.5)


def _season_score(doc: Dict[str, Any], wp: WeatherProfile) -> float:
    season = str(_get(doc, "season", "all-season") or "all-season").lower()
    if season in ["all-season", "all season", "all"]:
        return 0.85

    if wp.bucket == "cold":
        return 1.0 if season in ["winter", "fall"] else 0.5
    if wp.bucket == "hot":
        return 1.0 if season in ["summer", "spring"] else 0.5
    if wp.bucket == "warm":
        return 1.0 if season in ["summer", "spring", "all-season"] else 0.75
    # mild
    return 1.0 if season in ["spring", "fall", "all-season"] else 0.75


def _condition_penalty(wp: WeatherProfile, parts: List[Dict[str, Any]]) -> float:
    """Penalize obviously bad choices in rain/cold etc."""
    cond = wp.condition
    # Look for boots / coat / jacket in cold, etc.
    cats = [normalize_category(p.get("category")) for p in parts]

    if any(k in cond for k in ["rain", "drizzle", "storm", "thunder"]):
        # prefer closed shoes
        has_boot = any("boot" in str(p.get("category") or "").lower() for p in parts)
        return 1.0 if has_boot else 0.85

    if wp.bucket == "cold":
        has_outer = any(c == "outerwear" for c in cats)
        return 1.0 if has_outer else 0.88

    if wp.bucket == "hot":
        heavy_outer = any(c == "outerwear" for c in cats)
        return 0.75 if heavy_outer else 1.0

    return 1.0


def combo_score(parts: List[Dict[str, Any]], wp: WeatherProfile, occasion: str) -> float:
    """Overall score (bigger is better). Works for 1-item scoring too."""
    if not parts:
        return 0.0

    # Base
    score = 1.0

    # Formality and season
    for p in parts:
        score *= 0.65 + 0.35 * _formality_score(p, occasion)
        score *= 0.6 + 0.4 * _season_score(p, wp)

    # Color harmony: average pairwise harmony
    colors = [normalize_color(p.get("color")) for p in parts]
    if len(colors) >= 2:
        harms: List[float] = []
        for i in range(len(colors)):
            for j in range(i + 1, len(colors)):
                harms.append(_color_harmony(colors[i], colors[j]))
        if harms:
            score *= (sum(harms) / len(harms))

    # Weather condition penalty
    score *= _condition_penalty(wp, parts)

    return float(score)


def choose_outfit_title(parts: List[Dict[str, Any]], occasion: str, wp: WeatherProfile) -> str:
    occ = (occasion or "casual").strip().title()
    # Add a small vibe based on weather
    vibe = {
        "cold": "Cozy",
        "mild": "Classic",
        "warm": "Fresh",
        "hot": "Breezy",
    }.get(wp.bucket, "Style")
    return f"{vibe} {occ} Look"
