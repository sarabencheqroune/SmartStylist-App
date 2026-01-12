from __future__ import annotations

import os
import re
from typing import Dict, Any, List, Optional

from PIL import Image
from transformers import pipeline

# ==========================
# Controlled vocabularies
# ==========================
VALID_CATEGORIES = [
    "shirt", "pants", "dress", "shoes",
    "jacket", "sweater", "skirt", "shorts", "accessory"
]
VALID_SEASONS = ["summer", "winter", "spring", "fall", "all-season"]
VALID_FORMALITY = ["casual", "business-casual", "business", "formal"]

STYLE_TAGS = ["casual", "elegant", "sport", "streetwear", "classic", "minimal", "chic", "formal"]

# ==========================
# Load GENERATIVE model (LOCAL)
# ==========================
generator = pipeline(
    "text-generation",
    model="distilgpt2",
    max_new_tokens=120
)

# ==========================
# Keyword dictionaries (strong, deterministic)
# ==========================
KEYWORDS = {
    "shoes": [
        "shoe", "shoes", "sneaker", "sneakers", "boot", "boots", "heel", "heels",
        "sandals", "loafer", "loafers", "mocassin", "chauss", "baskets"
    ],
    "pants": [
        "pants", "pant", "jean", "jeans", "trouser", "trousers", "denim",
        "pantalon", "jogger", "leggings", "legging"
    ],
    "dress": ["dress", "robe"],
    "jacket": ["jacket", "coat", "blazer", "veste", "manteau"],
    "sweater": ["sweater", "hoodie", "pull", "cardigan", "knit", "sweatshirt"],
    "skirt": ["skirt", "jupe"],
    "shorts": ["short", "shorts"],
    "accessory": ["bag", "handbag", "sac", "belt", "ceinture", "scarf", "foulard", "watch", "sunglass", "jewelry"],
    "shirt": ["shirt", "tshirt", "t-shirt", "tee", "top", "blouse", "chemise"]
}

# Normalize frequent variants to your VALID_CATEGORIES
CATEGORY_MAP = {
    "shoe": "shoes",
    "sneakers": "shoes",
    "boots": "shoes",
    "jeans": "pants",
    "trousers": "pants",
    "pant": "pants",
    "top": "shirt",
    "tshirt": "shirt",
    "t-shirt": "shirt",
}


def _normalize_text(s: str) -> str:
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9\s\-\_]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


# ==========================
# Better color detection (HSV-ish rules, still light)
# ==========================
# In gemini_analyzer.py, update the _dominant_color function:
def _dominant_color(image_path: str) -> str:
    """Returns a robust coarse color name using average RGB + simple heuristics."""
    try:
        # Check if file exists first
        if not os.path.exists(image_path):
            print(f"⚠️ Warning: Image file not found: {image_path}")
            return "unknown"
        
        img = Image.open(image_path).convert("RGB").resize((80, 80))
        # ... rest of the function
    except Exception as e:
        print(f"⚠️ Color detection error: {e}")
        return "unknown"


# ==========================
# Category inference (deterministic first)
# ==========================
def _infer_category_from_context(context: str) -> Optional[str]:
    """
    Strong, deterministic category inference using filename + user_description.
    Returns a VALID_CATEGORIES value or None.
    """
    ctx = _normalize_text(context)

    # priority order matters: shoes & pants first (to stop "shirt" domination)
    priority = ["shoes", "pants", "dress", "jacket", "sweater", "skirt", "shorts", "accessory", "shirt"]
    for cat in priority:
        for kw in KEYWORDS[cat]:
            if kw in ctx:
                return cat
    return None


def _infer_season_from_text(text: str) -> str:
    t = _normalize_text(text)
    if "summer" in t or "été" in t:
        return "summer"
    if "winter" in t or "hiver" in t:
        return "winter"
    if "spring" in t or "print" in t:
        return "spring"
    if "fall" in t or "autumn" in t or "automne" in t:
        return "fall"
    return "all-season"


def _infer_formality_from_text(text: str) -> str:
    t = _normalize_text(text)
    if "formal" in t or "gala" in t or "wedding" in t or "soiree" in t or "soir" in t:
        return "formal"
    if "business" in t or "office" in t or "interview" in t or "work" in t or "travail" in t:
        return "business-casual"
    return "casual"


# ==========================
# GENERATIVE ANALYSIS (LLM = helper, not judge)
# ==========================
def analyze_clothing_image(image_path: str, user_description: str) -> Dict[str, Any]:
    filename = os.path.basename(image_path).lower()
    desc = user_description or ""
    color = _dominant_color(image_path)

    # 1) Deterministic category first (MOST IMPORTANT)
    context = f"{filename} {desc}"
    forced_category = _infer_category_from_context(context)

    # 2) Use the generative model to enrich: tags / season / formality
    # Keep prompt short to avoid nonsense.
    prompt = (
        "Extract fashion attributes from the input.\n"
        f"Description: {desc}\n"
        f"Filename: {filename}\n"
        f"Color: {color}\n"
        "Return a short text mentioning: category, season, formality, and a few style tags.\n"
        "Be concise.\n"
    )
    llm_text = generator(prompt)[0]["generated_text"]
    llm_text_norm = _normalize_text(llm_text)

    # 3) Category: forced category wins; otherwise try from LLM; otherwise fallback
    category = forced_category

    if category is None:
        # parse from LLM text with priority order
        category = _infer_category_from_context(llm_text_norm)

    if category is None:
        category = "shirt"

    # normalize category variants (just in case)
    category = CATEGORY_MAP.get(category, category)
    if category not in VALID_CATEGORIES:
        category = "shirt"

    # 4) Season & formality: combine LLM + user text (stable)
    season = _infer_season_from_text(desc + " " + llm_text_norm)
    if season not in VALID_SEASONS:
        season = "all-season"

    formality = _infer_formality_from_text(desc + " " + llm_text_norm)
    if formality not in VALID_FORMALITY:
        formality = "casual"

    # 5) Style tags: pull from both description and LLM output
    tags = []
    merged = _normalize_text(desc + " " + llm_text_norm)
    for t in STYLE_TAGS:
        if t in merged and t not in tags:
            tags.append(t)

    # small derived tags
    if category in ["jacket", "sweater"] and "cozy" not in tags:
        tags.append("cozy")
    if category == "shoes" and "footwear" not in tags:
        tags.append("footwear")

    return {
        "category": category,
        "color": color,
        "style_tags": tags[:6],
        "season": season,
        "formality": formality,
        "confidence": 0.90 if forced_category else 0.78,
        "note": "Hybrid: deterministic category + local generative enrichment (distilgpt2)."
    }

def _dominant_color(image_path: str) -> str:
    """Returns a robust coarse color name using average RGB + simple heuristics."""
    try:
        # Check if file exists first
        if not os.path.exists(image_path):
            print(f"⚠️ Warning: Image file not found: {image_path}")
            return "unknown"
        
        img = Image.open(image_path).convert("RGB").resize((80, 80))
        pixels = list(img.getdata())
        
        if not pixels:
            return "unknown"
        
        # Average RGB
        avg_r = sum(p[0] for p in pixels) // len(pixels)
        avg_g = sum(p[1] for p in pixels) // len(pixels)
        avg_b = sum(p[2] for p in pixels) // len(pixels)
        
        # Map to color names (simplified)
        if avg_r > 200 and avg_g > 200 and avg_b > 200:
            return "white"
        elif avg_r < 50 and avg_g < 50 and avg_b < 50:
            return "black"
        elif abs(avg_r - avg_g) < 30 and abs(avg_g - avg_b) < 30:
            return "gray"
        elif avg_r > avg_g and avg_r > avg_b:
            if avg_r > 150:
                return "red"
            else:
                return "dark red"
        elif avg_g > avg_r and avg_g > avg_b:
            if avg_g > 150:
                return "green"
            else:
                return "dark green"
        elif avg_b > avg_r and avg_b > avg_g:
            if avg_b > 150:
                return "blue"
            else:
                return "dark blue"
        else:
            return "beige"  # default fallback
            
    except Exception as e:
        print(f"⚠️ Color detection error: {e}")
        return "unknown"  # Always return string, never None