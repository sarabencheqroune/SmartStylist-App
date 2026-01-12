from __future__ import annotations

import os
import time
import random
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple, Set
from datetime import datetime
from enum import Enum
import numpy as np

from dotenv import load_dotenv

from mongodb_client import db_client
from wardrobe_database import WardrobeDatabase
from style_scoring import (
    WeatherProfile,
    build_weather_profile,
    choose_outfit_title,
    combo_score,
    normalize_category,
)

load_dotenv()


class OutfitType(Enum):
    """Types of outfits based on occasion."""
    CASUAL = "casual"
    BUSINESS_CASUAL = "business-casual"
    BUSINESS = "business"
    FORMAL = "formal"
    PARTY = "party"
    DATE_NIGHT = "date"
    SPORT = "sport"
    TRAVEL = "travel"


class OutfitComplexity(Enum):
    """Complexity levels for outfit generation."""
    SIMPLE = "simple"      # 2-3 items
    STANDARD = "standard"  # 3-4 items
    COMPLEX = "complex"    # 4-6 items


@dataclass
class OutfitConfig:
    """Configuration for outfit generation."""
    min_items: int = 3
    max_items: int = 6
    complexity: OutfitComplexity = OutfitComplexity.STANDARD
    diversity_weight: float = 0.7
    style_consistency_weight: float = 0.8
    color_harmony_weight: float = 0.9
    weather_adaptation_weight: float = 1.0
    max_generation_attempts: int = 100


@dataclass
class GenerationContext:
    """Context for outfit generation."""
    user_id: str
    occasion: str
    weather_profile: WeatherProfile
    outfit_type: OutfitType
    config: OutfitConfig
    available_items: List[Dict[str, Any]]
    focus_item: Optional[Dict[str, Any]] = None
    blacklisted_item_ids: Set[str] = field(default_factory=set)


# -----------------------------
# Optional Gemini helper (enhanced)
# -----------------------------

def _enhanced_gemini_refine(outfits: List[Dict[str, Any]], occasion: str, 
                           weather: Dict[str, Any], user_id: str) -> None:
    """Ask Gemini to refine outfit descriptions and provide styling tips."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        return
    
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")
        
        for outfit in outfits:
            items = outfit.get("items") or []
            
            # Prepare item details
            item_details = []
            for i, item in enumerate(items):
                cat = item.get('category', 'item')
                color = item.get('color', '')
                style = ', '.join(item.get('style_tags', [])[:3])
                item_details.append(f"{i+1}. {cat} ({color}) - {style}")
            
            prompt = f"""
            You are a professional fashion stylist. Analyze this outfit and provide:
            1. A catchy, engaging title (max 5 words)
            2. A detailed description of the outfit (2-3 sentences)
            3. Styling tips for this occasion (2-3 bullet points)
            4. Occasion suitability score (1-10)
            
            Outfit Context:
            - Occasion: {occasion}
            - Weather: {weather.get('temp_c')}°C, {weather.get('condition')} in {weather.get('city')}
            - User Profile: Fashion-conscious individual
            
            Outfit Items:
            {chr(10).join(item_details)}
            
            Respond in JSON format:
            {{
                "title": "string",
                "description": "string",
                "styling_tips": ["tip1", "tip2", "tip3"],
                "suitability_score": number
            }}
            """
            
            try:
                resp = model.generate_content(prompt)
                txt = (getattr(resp, "text", None) or "").strip()
                
                # Extract JSON from response
                import json
                import re
                
                # Find JSON in the response
                json_match = re.search(r'\{.*\}', txt, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group())
                    
                    # Update outfit with AI suggestions
                    outfit["ai_title"] = data.get("title", outfit.get("title", ""))
                    outfit["ai_description"] = data.get("description", "")
                    outfit["styling_tips"] = data.get("styling_tips", [])
                    outfit["suitability_score"] = data.get("suitability_score", 7)
                    
                    # Keep original title as fallback
                    if "title" not in outfit:
                        outfit["title"] = outfit["ai_title"]
            except Exception as e:
                # Silently fail - keep original data
                continue
                
    except Exception:
        # Never fail generation because of Gemini
        return


# -----------------------------
# Color Harmony System
# -----------------------------

class ColorHarmony:
    """Advanced color harmony system."""
    
    COLOR_FAMILIES = {
        "neutral": {"black", "white", "gray", "grey", "beige", "brown", "navy", "cream", "khaki"},
        "warm": {"red", "orange", "yellow", "pink", "coral", "peach", "gold"},
        "cool": {"blue", "green", "purple", "teal", "turquoise", "lavender", "mint"},
        "earth": {"brown", "beige", "olive", "mustard", "rust", "terracotta"},
        "jewel": {"emerald", "sapphire", "ruby", "amethyst", "topaz"}
    }
    
    COMPLEMENTARY_PAIRS = {
        "red": "green",
        "orange": "blue",
        "yellow": "purple",
        "pink": "mint",
        "blue": "orange",
        "green": "red",
        "purple": "yellow"
    }
    
    ANALOGOUS_RANGES = {
        "red": ["pink", "orange", "coral"],
        "blue": ["teal", "purple", "navy"],
        "green": ["mint", "olive", "teal"],
        "purple": ["lavender", "pink", "blue"]
    }
    
    @classmethod
    def get_color_family(cls, color: str) -> str:
        """Determine which family a color belongs to."""
        color_lower = color.lower()
        for family, colors in cls.COLOR_FAMILIES.items():
            if color_lower in colors:
                return family
        return "unknown"
    
    @classmethod
    def calculate_harmony_score(cls, color1: str, color2: str) -> float:
        """Calculate harmony score between two colors (0-1)."""
        if color1 == "unknown" or color2 == "unknown":
            return 0.6
        
        color1 = color1.lower()
        color2 = color2.lower()
        
        # Same color - good harmony
        if color1 == color2:
            return 0.8
        
        # Both neutrals - always good
        if (color1 in cls.COLOR_FAMILIES["neutral"] and 
            color2 in cls.COLOR_FAMILIES["neutral"]):
            return 0.9
        
        # One neutral - good with anything
        if (color1 in cls.COLOR_FAMILIES["neutral"] or 
            color2 in cls.COLOR_FAMILIES["neutral"]):
            return 0.85
        
        # Complementary colors - great harmony
        if (color1 in cls.COMPLEMENTARY_PAIRS and 
            cls.COMPLEMENTARY_PAIRS[color1] == color2):
            return 0.95
        
        # Analogous colors - good harmony
        if (color1 in cls.ANALOGOUS_RANGES and 
            color2 in cls.ANALOGOUS_RANGES[color1]):
            return 0.85
        
        # Same color family - good harmony
        family1 = cls.get_color_family(color1)
        family2 = cls.get_color_family(color2)
        if family1 == family2 and family1 != "unknown":
            return 0.8
        
        # Different warm/cool families - potential clash
        if (family1 in ["warm", "earth"] and family2 in ["cool", "jewel"]):
            return 0.5
        
        # Default moderate harmony
        return 0.7
    
    @classmethod
    def get_recommended_colors(cls, base_color: str, weather: str) -> List[str]:
        """Get recommended colors based on base color and weather."""
        base_color = base_color.lower()
        recommendations = []
        
        # Always include neutrals
        recommendations.extend(list(cls.COLOR_FAMILIES["neutral"]))
        
        # Add complementary color
        if base_color in cls.COMPLEMENTARY_PAIRS:
            recommendations.append(cls.COMPLEMENTARY_PAIRS[base_color])
        
        # Add analogous colors
        if base_color in cls.ANALOGOUS_RANGES:
            recommendations.extend(cls.ANALOGOUS_RANGES[base_color])
        
        # Weather-based adjustments
        if "rain" in weather or "cloud" in weather:
            recommendations.extend(["yellow", "red", "orange"])  # Bright colors for gloomy days
        elif "sun" in weather or "clear" in weather:
            recommendations.extend(["white", "beige", "light blue"])  # Light colors for sunny days
        elif "cold" in weather or "snow" in weather:
            recommendations.extend(["red", "green", "navy"])  # Rich colors for cold days
        
        return list(set(recommendations))[:10]


# -----------------------------
# Style Compatibility System
# -----------------------------

class StyleCompatibility:
    """Advanced style compatibility system."""
    
    STYLE_CATEGORIES = {
        "minimal": {"simple", "clean", "basic", "neutral"},
        "streetwear": {"urban", "casual", "edgy", "sporty"},
        "classic": {"timeless", "elegant", "traditional", "sophisticated"},
        "bohemian": {"boho", "flowy", "patterned", "natural"},
        "glam": {"glamorous", "sparkly", "luxurious", "evening"},
        "sporty": {"athletic", "active", "comfortable", "performance"},
        "business": {"professional", "tailored", "sharp", "formal"}
    }
    
    @classmethod
    def get_style_category(cls, tags: List[str]) -> str:
        """Determine the dominant style category from tags."""
        tag_set = set(t.lower() for t in tags)
        
        scores = {}
        for category, keywords in cls.STYLE_CATEGORIES.items():
            intersection = tag_set.intersection(keywords)
            scores[category] = len(intersection)
        
        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        return "minimal"  # Default
    
    @classmethod
    def calculate_style_compatibility(cls, item1_tags: List[str], 
                                     item2_tags: List[str]) -> float:
        """Calculate style compatibility between two items."""
        if not item1_tags or not item2_tags:
            return 0.7
        
        cat1 = cls.get_style_category(item1_tags)
        cat2 = cls.get_style_category(item2_tags)
        
        # Same category - perfect match
        if cat1 == cat2:
            return 1.0
        
        # Compatible categories
        compatible_pairs = {
            ("minimal", "classic"),
            ("minimal", "business"),
            ("classic", "business"),
            ("streetwear", "sporty"),
            ("bohemian", "glam")
        }
        
        if (cat1, cat2) in compatible_pairs or (cat2, cat1) in compatible_pairs:
            return 0.8
        
        # Neutral categories (minimal, classic) work with most things
        if cat1 in ["minimal", "classic"] or cat2 in ["minimal", "classic"]:
            return 0.75
        
        # Potentially clashing categories
        clashing_pairs = {
            ("sporty", "business"),
            ("streetwear", "glam"),
            ("bohemian", "business")
        }
        
        if (cat1, cat2) in clashing_pairs or (cat2, cat1) in clashing_pairs:
            return 0.5
        
        # Default moderate compatibility
        return 0.7
    
    @classmethod
    def get_style_recommendations(cls, occasion: str) -> Dict[str, Any]:
        """Get style recommendations for an occasion."""
        recommendations = {
            "casual": {
                "categories": ["minimal", "streetwear", "sporty"],
                "colors": ["neutral", "cool", "earth"],
                "complexity": "simple"
            },
            "business": {
                "categories": ["business", "classic", "minimal"],
                "colors": ["neutral", "cool"],
                "complexity": "standard"
            },
            "formal": {
                "categories": ["classic", "glam", "business"],
                "colors": ["neutral", "jewel"],
                "complexity": "complex"
            },
            "date": {
                "categories": ["classic", "glam", "bohemian"],
                "colors": ["warm", "cool", "jewel"],
                "complexity": "standard"
            },
            "party": {
                "categories": ["glam", "streetwear", "bohemian"],
                "colors": ["jewel", "warm", "cool"],
                "complexity": "complex"
            }
        }
        
        occasion_lower = occasion.lower()
        for key, value in recommendations.items():
            if key in occasion_lower:
                return value
        
        return recommendations["casual"]  # Default


# -----------------------------
# Cache System
# -----------------------------

@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    generation_params: Dict[str, Any]


class EnhancedCache:
    """Enhanced cache with TTL and generation parameter tracking."""
    
    def __init__(self, ttl_seconds: int = 30, max_size: int = 128):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._data: Dict[str, CacheEntry] = {}
        self._access_times: Dict[str, float] = {}
    
    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        ent = self._data.get(key)
        
        if not ent:
            return None
        
        if ent.expires_at < now:
            self._data.pop(key, None)
            self._access_times.pop(key, None)
            return None
        
        # Update access time (LRU)
        self._access_times[key] = now
        return ent.value
    
    def set(self, key: str, value: Any, generation_params: Dict[str, Any]) -> None:
        now = time.time()
        
        # Evict if needed (LRU)
        if len(self._data) >= self.max_size:
            oldest_key = min(self._access_times.items(), key=lambda x: x[1])[0]
            self._data.pop(oldest_key, None)
            self._access_times.pop(oldest_key, None)
        
        self._data[key] = CacheEntry(
            value=value,
            expires_at=now + self.ttl_seconds,
            generation_params=generation_params
        )
        self._access_times[key] = now
    
    def clear(self) -> None:
        self._data.clear()
        self._access_times.clear()


# -----------------------------
# Enhanced Outfit Generator
# -----------------------------

class EnhancedOutfitGenerator:
    """Enhanced outfit generation engine with better algorithms."""
    
    def __init__(self, wardrobe_db: WardrobeDatabase):
        self.wardrobe_db = wardrobe_db
        self._cache = EnhancedCache(
            ttl_seconds=int(os.getenv("OUTFIT_CACHE_TTL", "30")), 
            max_size=128
        )
        
    def _categorize_items(self, items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Categorize items by normalized category."""
        categorized = {}
        for item in items:
            cat = normalize_category(item.get("category"))
            if cat not in categorized:
                categorized[cat] = []
            categorized[cat].append(item)
        return categorized
    
    def _determine_outfit_type(self, occasion: str) -> OutfitType:
        """Determine outfit type based on occasion."""
        occasion_lower = occasion.lower()
        
        if any(word in occasion_lower for word in ["wedding", "gala", "formal", "ceremony"]):
            return OutfitType.FORMAL
        elif any(word in occasion_lower for word in ["meeting", "office", "work", "business", "interview"]):
            return OutfitType.BUSINESS
        elif any(word in occasion_lower for word in ["date", "romantic", "anniversary"]):
            return OutfitType.DATE_NIGHT
        elif any(word in occasion_lower for word in ["party", "celebration", "festival"]):
            return OutfitType.PARTY
        elif any(word in occasion_lower for word in ["sport", "gym", "workout", "athletic"]):
            return OutfitType.SPORT
        elif any(word in occasion_lower for word in ["travel", "airport", "journey"]):
            return OutfitType.TRAVEL
        elif any(word in occasion_lower for word in ["casual", "relaxed", "everyday"]):
            return OutfitType.CASUAL
        else:
            return OutfitType.BUSINESS_CASUAL
    
    def _get_outfit_config(self, outfit_type: OutfitType) -> OutfitConfig:
        """Get configuration for outfit type."""
        configs = {
            OutfitType.CASUAL: OutfitConfig(
                min_items=2,
                max_items=4,
                complexity=OutfitComplexity.SIMPLE
            ),
            OutfitType.BUSINESS_CASUAL: OutfitConfig(
                min_items=3,
                max_items=5,
                complexity=OutfitComplexity.STANDARD
            ),
            OutfitType.BUSINESS: OutfitConfig(
                min_items=3,
                max_items=5,
                complexity=OutfitComplexity.STANDARD,
                style_consistency_weight=0.9
            ),
            OutfitType.FORMAL: OutfitConfig(
                min_items=3,
                max_items=6,
                complexity=OutfitComplexity.COMPLEX,
                style_consistency_weight=0.95
            ),
            OutfitType.PARTY: OutfitConfig(
                min_items=3,
                max_items=6,
                complexity=OutfitComplexity.COMPLEX,
                diversity_weight=0.8
            ),
            OutfitType.DATE_NIGHT: OutfitConfig(
                min_items=3,
                max_items=5,
                complexity=OutfitComplexity.STANDARD,
                style_consistency_weight=0.85
            ),
            OutfitType.SPORT: OutfitConfig(
                min_items=2,
                max_items=4,
                complexity=OutfitComplexity.SIMPLE,
                weather_adaptation_weight=1.2
            ),
            OutfitType.TRAVEL: OutfitConfig(
                min_items=2,
                max_items=4,
                complexity=OutfitComplexity.SIMPLE,
                weather_adaptation_weight=1.1
            )
        }
        
        return configs.get(outfit_type, OutfitConfig())
    
    def _calculate_item_suitability(self, item: Dict[str, Any], 
                                   context: GenerationContext) -> float:
        """Calculate how suitable an item is for the given context."""
        score = 1.0
        
        # Category relevance
        category = normalize_category(item.get("category"))
        if category in ["top", "dress"]:
            score *= 1.1  # Core items get bonus
        
        # Formality matching
        item_formality = item.get("formality", "casual").lower()
        if context.outfit_type == OutfitType.FORMAL and item_formality != "formal":
            score *= 0.7
        elif context.outfit_type == OutfitType.BUSINESS and item_formality not in ["business", "business-casual"]:
            score *= 0.8
        
        # Season suitability
        item_season = item.get("season", "all-season").lower()
        weather_temp = context.weather_profile.temp_c
        
        if item_season != "all-season":
            if weather_temp < 15 and item_season not in ["winter", "fall"]:
                score *= 0.7
            elif weather_temp > 25 and item_season not in ["summer", "spring"]:
                score *= 0.7
        
        # Weather condition adaptation
        condition = context.weather_profile.condition
        if "rain" in condition and category not in ["shoes", "outerwear"]:
            # Non-protective items less suitable for rain
            score *= 0.9
        elif "cold" in condition and category in ["shorts", "skirt"]:
            score *= 0.6
        
        return score
    
    def _select_base_items(self, categorized_items: Dict[str, List[Dict[str, Any]]], 
                          context: GenerationContext) -> List[Dict[str, Any]]:
        """Select base items for the outfit."""
        base_items = []
        
        # Start with focus item if provided
        if context.focus_item:
            base_items.append(context.focus_item)
        
        # Determine what categories we need
        required_categories = self._get_required_categories(context)
        
        print(f"🔍 Looking for required categories: {required_categories}")
        print(f"📁 Available categories: {list(categorized_items.keys())}")
        
        # Select items from required categories
        for category in required_categories:
            if category in categorized_items and categorized_items[category]:
                print(f"✅ Found {len(categorized_items[category])} items in category: {category}")
                
                # Score items in this category
                scored_items = []
                for item in categorized_items[category]:
                    # Skip if item is already selected or blacklisted
                    item_id = str(item.get("_id", ""))
                    if not item_id:
                        continue
                        
                    if item_id in context.blacklisted_item_ids:
                        print(f"   Skipping {item_id} - blacklisted")
                        continue
                    
                    suitability = self._calculate_item_suitability(item, context)
                    scored_items.append((item, suitability))
                    print(f"   Item {item_id[:8]}: {item.get('category', 'unknown')} - suitability: {suitability:.2f}")
                
                # Sort by score and pick the best
                if scored_items:
                    scored_items.sort(key=lambda x: x[1], reverse=True)
                    selected_item = scored_items[0][0]
                    
                    # Check if this item works with existing base items
                    if self._check_item_compatibility(selected_item, base_items, context):
                        base_items.append(selected_item)
                        context.blacklisted_item_ids.add(str(selected_item.get("_id", "")))
                        print(f"✅ Added item to base: {selected_item.get('category', 'unknown')}")
                    else:
                        print(f"❌ Item not compatible with existing items")
                else:
                    print(f"❌ No suitable items found in category: {category}")
            else:
                print(f"❌ No items found in required category: {category}")
        
        print(f"📦 Selected {len(base_items)} base items")
        return base_items
    
    def _get_required_categories(self, context: GenerationContext) -> List[str]:
        """Get required categories based on outfit type."""
        if context.outfit_type == OutfitType.FORMAL:
            return ["dress", "shoes", "accessory"]
        elif context.outfit_type in [OutfitType.BUSINESS, OutfitType.BUSINESS_CASUAL]:
            return ["top", "bottom", "shoes", "outerwear"]
        elif context.outfit_type == OutfitType.SPORT:
            return ["top", "bottom", "shoes"]
        else:  # CASUAL, PARTY, DATE_NIGHT, TRAVEL
            return ["top", "bottom", "shoes"]
    
    def _check_item_compatibility(self, new_item: Dict[str, Any], 
                                 existing_items: List[Dict[str, Any]], 
                                 context: GenerationContext) -> bool:
        """Check if a new item is compatible with existing items."""
        if not existing_items:
            return True
    
    # FIX: Ensure color is string
        new_color = new_item.get("color", "")
        if new_color is None:  # Handle None case
            new_color = "unknown"
        else:
            new_color = str(new_color).lower()
    
    # Check color harmony
        for existing_item in existing_items:
            existing_color = existing_item.get("color", "")
            if existing_color is None:  # Handle None case
                existing_color = "unknown"
            else:
                existing_color = str(existing_color).lower()
            
            harmony = ColorHarmony.calculate_harmony_score(new_color, existing_color)
            if harmony < 0.5:  # Poor harmony
                return False
    
    # Check style compatibility
        new_tags = new_item.get("style_tags", [])
        for existing_item in existing_items:
            existing_tags = existing_item.get("style_tags", [])
            compatibility = StyleCompatibility.calculate_style_compatibility(new_tags, existing_tags)
            if compatibility < 0.5:  # Poor compatibility
                return False
    
        return True
    
    def _add_complementary_items(self, base_items: List[Dict[str, Any]], 
                                categorized_items: Dict[str, List[Dict[str, Any]]], 
                                context: GenerationContext) -> List[Dict[str, Any]]:
        """Add complementary items to complete the outfit."""
        outfit_items = base_items.copy()
        
        # Determine what complementary categories we need
        complementary_categories = self._get_complementary_categories(context)
        
        for category in complementary_categories:
            if category in categorized_items and categorized_items[category]:
                # Find best matching item in this category
                best_item = None
                best_score = 0
                
                for item in categorized_items[category]:
                    if str(item.get("_id")) in context.blacklisted_item_ids:
                        continue
                    
                    # Score based on compatibility with existing items
                    compatibility_score = self._calculate_compatibility_score(item, outfit_items, context)
                    
                    if compatibility_score > best_score:
                        best_score = compatibility_score
                        best_item = item
                
                # Add item if it meets threshold
                if best_item and best_score > 0.6:
                    outfit_items.append(best_item)
                    context.blacklisted_item_ids.add(str(best_item.get("_id")))
        
        return outfit_items
    
    def _get_complementary_categories(self, context: GenerationContext) -> List[str]:
        """Get complementary categories based on outfit type and weather."""
        complementary = ["accessory"]
        
        # Weather-based additions
        if context.weather_profile.temp_c < 15:
            complementary.append("outerwear")
        if "rain" in context.weather_profile.condition:
            complementary.append("outerwear")  # Assuming waterproof
        
        # Occasion-based additions
        if context.outfit_type in [OutfitType.FORMAL, OutfitType.PARTY, OutfitType.DATE_NIGHT]:
            complementary.extend(["accessory", "accessory"])  # More accessories for special occasions
        
        return complementary
    
    def _calculate_compatibility_score(self, item: Dict[str, Any], 
                                      outfit_items: List[Dict[str, Any]], 
                                      context: GenerationContext) -> float:
        """Calculate how well an item complements existing outfit items."""
        if not outfit_items:
            return self._calculate_item_suitability(item, context)
        
        scores = []
        
        for outfit_item in outfit_items:
            # Color harmony
            color_score = ColorHarmony.calculate_harmony_score(
                item.get("color", "").lower(),
                outfit_item.get("color", "").lower()
            )
            
            # Style compatibility
            style_score = StyleCompatibility.calculate_style_compatibility(
                item.get("style_tags", []),
                outfit_item.get("style_tags", [])
            )
            
            # Category synergy (some categories work better together)
            cat1 = normalize_category(item.get("category"))
            cat2 = normalize_category(outfit_item.get("category"))
            category_synergy = self._get_category_synergy(cat1, cat2)
            
            # Combine scores
            combined = (color_score * 0.4 + style_score * 0.4 + category_synergy * 0.2)
            scores.append(combined)
        
        return np.mean(scores) if scores else 0
    
    def _get_category_synergy(self, cat1: str, cat2: str) -> float:
        """Get synergy score between two categories."""
        synergy_pairs = {
            ("top", "bottom"): 1.0,
            ("dress", "shoes"): 1.0,
            ("top", "outerwear"): 0.9,
            ("bottom", "shoes"): 0.9,
            ("accessory", "top"): 0.8,
            ("accessory", "dress"): 0.8,
            ("accessory", "bottom"): 0.7
        }
        
        key = (cat1, cat2) if cat1 < cat2 else (cat2, cat1)
        return synergy_pairs.get(key, 0.5)
    
    def _calculate_outfit_score(self, outfit_items: List[Dict[str, Any]], 
                               context: GenerationContext) -> float:
        """Calculate overall score for an outfit."""
        if len(outfit_items) < context.config.min_items:
            return 0.0
        
        scores = []
        
        # Individual item suitability
        for item in outfit_items:
            suitability = self._calculate_item_suitability(item, context)
            scores.append(suitability)
        
        # Pairwise compatibility
        for i in range(len(outfit_items)):
            for j in range(i + 1, len(outfit_items)):
                item1 = outfit_items[i]
                item2 = outfit_items[j]
                
                # Color harmony
                color_score = ColorHarmony.calculate_harmony_score(
                    item1.get("color", "").lower(),
                    item2.get("color", "").lower()
                )
                
                # Style compatibility
                style_score = StyleCompatibility.calculate_style_compatibility(
                    item1.get("style_tags", []),
                    item2.get("style_tags", [])
                )
                
                compatibility = (color_score + style_score) / 2
                scores.append(compatibility)
        
        # Weather adaptation bonus
        weather_bonus = self._calculate_weather_adaptation_bonus(outfit_items, context)
        scores.append(weather_bonus)
        
        # Occasion suitability bonus
        occasion_bonus = self._calculate_occasion_bonus(outfit_items, context)
        scores.append(occasion_bonus)
        
        # Calculate final score (weighted average)
        return np.mean(scores) if scores else 0.0
    
    def _calculate_weather_adaptation_bonus(self, outfit_items: List[Dict[str, Any]], 
                                           context: GenerationContext) -> float:
        """Calculate bonus for weather adaptation."""
        bonus = 1.0
        
        # Check for appropriate outerwear in cold weather
        if context.weather_profile.temp_c < 15:
            has_outerwear = any(normalize_category(item.get("category")) == "outerwear" 
                               for item in outfit_items)
            if has_outerwear:
                bonus *= 1.2
            else:
                bonus *= 0.8
        
        # Check for appropriate footwear in rain
        if "rain" in context.weather_profile.condition:
            has_waterproof = any("waterproof" in item.get("style_tags", []) or 
                                "boot" in str(item.get("category", "")).lower()
                                for item in outfit_items)
            if has_waterproof:
                bonus *= 1.1
        
        return bonus
    
    def _calculate_occasion_bonus(self, outfit_items: List[Dict[str, Any]], 
                                 context: GenerationContext) -> float:
        """Calculate bonus for occasion suitability."""
        # Count formal items for formal occasions
        if context.outfit_type == OutfitType.FORMAL:
            formal_count = sum(1 for item in outfit_items 
                             if item.get("formality") == "formal")
            if formal_count >= 2:
                return 1.2
            elif formal_count >= 1:
                return 1.0
            else:
                return 0.8
        
        # Count business items for business occasions
        elif context.outfit_type in [OutfitType.BUSINESS, OutfitType.BUSINESS_CASUAL]:
            business_count = sum(1 for item in outfit_items 
                               if item.get("formality") in ["business", "business-casual"])
            if business_count >= 2:
                return 1.1
        
        return 1.0
    
    def _deduplicate_items(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate items from the list."""
        seen_ids = set()
        unique_items = []
        
        for item in items:
            item_id = str(item.get("_id"))
            if item_id and item_id not in seen_ids:
                seen_ids.add(item_id)
                unique_items.append(item)
        
        return unique_items
    
    def _format_outfit_for_response(self, outfit_items: List[Dict[str, Any]], 
                                   context: GenerationContext, 
                                   outfit_score: float) -> Dict[str, Any]:
        """Format outfit for API response."""
        # Get base64 images for all items
        for item in outfit_items:
            if "image_file_id" in item:
                try:
                    item["image_base64"] = db_client.get_image_base64(item["image_file_id"])
                except:
                    item["image_base64"] = None
        
        # Generate title and details
        title = choose_outfit_title(outfit_items, context.occasion, context.weather_profile)
        
        # Create detailed description
        categories = [normalize_category(item.get("category")) for item in outfit_items]
        colors = [item.get("color", "unknown") for item in outfit_items]
        details = f"{', '.join(set(categories))} in {', '.join(set(colors))}"
        
        return {
            "title": title,
            "details": details,
            "items": [self._to_front_item(item) for item in outfit_items],
            "score": round(outfit_score, 3),
            "item_count": len(outfit_items),
            "occasion_suitability": self._calculate_occasion_bonus(outfit_items, context),
            "weather_adaptation": self._calculate_weather_adaptation_bonus(outfit_items, context)
        }
    
    def _to_front_item(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Convert database document to frontend item format."""
        return {
            "id": str(doc.get("_id")) if doc.get("_id") is not None else None,
            "image_file_id": doc.get("image_file_id"),
            "image_base64": doc.get("image_base64"),
            "category": doc.get("category") or normalize_category(doc.get("category")),
            "color": doc.get("color"),
            "style_tags": doc.get("style_tags", []),
            "formality": doc.get("formality"),
            "season": doc.get("season")
        }
    
    # ==================== PUBLIC API ====================
    
    def generate_outfits(self, user_id: str, occasion: str, 
                         weather: Dict[str, Any], num_outfits: int = 3, 
                         focus_item_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Generate outfits for a user."""
        # ADDED DEBUGGING
        print(f"🎨 ENTERING generate_outfits")
        print(f"   occasion param: '{occasion}' (type: {type(occasion)})")
        print(f"   user_id: '{user_id}'")
        print(f"   weather: {weather}")
        print(f"   num_outfits: {num_outfits}")
        print(f"   focus_item_id: '{focus_item_id}'")
    
        # Validate inputs with extra safety
        if occasion is None:
            print("⚠️  occasion is None, setting to 'casual day'")
            occasion = "casual day"
        elif not isinstance(occasion, str):
            print(f"⚠️  occasion is not a string ({type(occasion)}), converting")
            occasion = str(occasion)
    
        occasion = (occasion or "casual day").strip()
        print(f"✅ Sanitized occasion: '{occasion}'")
            
        # Create cache key
        wp = build_weather_profile(weather)
        cache_key = f"{user_id}|{occasion}|{wp.bucket}|{num_outfits}|{focus_item_id or ''}"
        
        # Check cache
        cached = self._cache.get(cache_key)
        if cached is not None:
            print("✅ Using cached outfits")
            return cached
        
        # Get user's wardrobe items
        print("📋 Getting user's wardrobe items...")
        user_items = self.wardrobe_db.get_user_items(user_id)
        print(f"   Found {len(user_items)} items in wardrobe")
        
        if not user_items:
            print("❌ No items in wardrobe!")
            return []
        
        # Show what categories we have
        categories = {}
        for item in user_items:
            cat = normalize_category(item.get("category", "unknown"))
            categories[cat] = categories.get(cat, 0) + 1
        
        print(f"   Categories: {categories}")
        
        # Show first few items
        for i, item in enumerate(user_items[:3]):
            print(f"   Item {i+1}: {item.get('category', 'unknown')} - {item.get('color', 'unknown')}")
        
        # Prepare generation context
        outfit_type = self._determine_outfit_type(occasion)
        config = self._get_outfit_config(outfit_type)
        
        print(f"   Outfit type: {outfit_type.value}")
        print(f"   Config: {config.min_items}-{config.max_items} items")
        
        # Get focus item if specified
        focus_item = None
        if focus_item_id:
            focus_item = next((item for item in user_items 
                             if str(item.get("_id")) == str(focus_item_id)), None)
            if focus_item:
                print(f"   Focus item: {focus_item.get('category', 'unknown')}")
            else:
                print(f"   Focus item not found: {focus_item_id}")
        
        # Categorize items
        categorized_items = self._categorize_items(user_items)
        print(f"   Categorized into: {list(categorized_items.keys())}")
        
        # Generate multiple outfits
        outfits = []
        used_outfit_combinations = set()
        
        print(f"\n🔄 Generating up to {num_outfits} outfits...")
        
        for attempt in range(config.max_generation_attempts):
            if len(outfits) >= num_outfits:
                break
            
            print(f"\n   Attempt {attempt + 1}:")
            
            # Create new context for this attempt
            context = GenerationContext(
                user_id=user_id,
                occasion=occasion,
                weather_profile=wp,
                outfit_type=outfit_type,
                config=config,
                available_items=user_items,
                focus_item=focus_item,
                blacklisted_item_ids=set()
            )
            
            # Select base items
            base_items = self._select_base_items(categorized_items, context)
            print(f"      Selected {len(base_items)} base items")
            
            if len(base_items) < config.min_items:
                print(f"      ❌ Not enough base items ({len(base_items)} < {config.min_items})")
                continue  # Not enough items for a complete outfit
            
            # Add complementary items
            outfit_items = self._add_complementary_items(base_items, categorized_items, context)
            outfit_items = self._deduplicate_items(outfit_items)
            print(f"      After adding complementary: {len(outfit_items)} items")
            
            # Ensure minimum items
            if len(outfit_items) < config.min_items:
                print(f"      ❌ Not enough total items ({len(outfit_items)} < {config.min_items})")
                continue
            
            # Calculate outfit score
            outfit_score = self._calculate_outfit_score(outfit_items, context)
            print(f"      Outfit score: {outfit_score:.2f}")
            
            # Check if this combination is unique
            item_ids = tuple(sorted(str(item.get("_id")) for item in outfit_items))
            if item_ids in used_outfit_combinations:
                print(f"      ❌ Duplicate combination")
                continue
            
            # Only keep outfits with decent score
            if outfit_score < 0.5:
                print(f"      ❌ Score too low ({outfit_score:.2f} < 0.5)")
                continue
            
            # Format outfit for response
            outfit = self._format_outfit_for_response(outfit_items, context, outfit_score)
            
            outfits.append(outfit)
            used_outfit_combinations.add(item_ids)
            print(f"      ✅ Added outfit {len(outfits)} with score {outfit_score:.2f}")
        
        print(f"\n🎉 Generated {len(outfits)} outfits")
        
        # Sort by score
        outfits.sort(key=lambda x: x.get("score", 0), reverse=True)
        outfits = outfits[:num_outfits]
        
        # Add AI refinements if available
        _enhanced_gemini_refine(outfits, occasion, weather, user_id)
        
        # Cache the results
        self._cache.set(cache_key, outfits, {
            "user_id": user_id,
            "occasion": occasion,
            "weather": weather,
            "num_outfits": num_outfits,
            "focus_item_id": focus_item_id
        })
        
        return outfits
    
    def generate_and_save_outfits(self, user_id: str, occasion: str, 
                                 weather: Dict[str, Any], num_outfits: int = 3, 
                                 focus_item_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Generate outfits and save to history."""
        outfits = self.generate_outfits(user_id, occasion, weather, num_outfits, focus_item_id)
        
        outfit_ids = []
        if outfits:
            outfit_ids = db_client.save_outfit_to_history(
                user_id=user_id,
                outfits=outfits,
                occasion=occasion,
                weather=weather
            )
        
        return outfits, outfit_ids
    
    def get_outfit_recommendations(self, user_id: str, item_id: str, 
                                  weather: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get recommendations for how to wear a specific item."""
        # Get the item
        item = self.wardrobe_db.get_item(item_id)
        if not item:
            return []
        
        # Generate outfits with this item as focus
        outfits = self.generate_outfits(
            user_id=user_id,
            occasion="casual",  # Default occasion
            weather=weather,
            num_outfits=5,
            focus_item_id=item_id
        )
        
        return outfits


# -----------------------------
# Backward Compatibility
# -----------------------------

class OutfitGenerator:
    """Legacy wrapper for backward compatibility."""
    
    def __init__(self, wardrobe_db: WardrobeDatabase):
        self.enhanced_generator = EnhancedOutfitGenerator(wardrobe_db)
        self.wardrobe_db = wardrobe_db
    
    def generate_outfits(self, occasion: str, weather: Dict[str, Any], 
                        num_outfits: int = 3, focus_item_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Legacy method - uses anonymous user."""
        return self.enhanced_generator.generate_outfits(
            user_id="anonymous",
            occasion=occasion,
            weather=weather,
            num_outfits=num_outfits,
            focus_item_id=focus_item_id
        )
    
    def generate_and_save_outfits(self, occasion: str, weather: Dict[str, Any], 
                                 num_outfits: int = 3, focus_item_id: Optional[str] = None, 
                                 user_id: Optional[str] = None, save_to_history: bool = True) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Legacy method with user support."""
        if not user_id:
            user_id = "anonymous"
        
        return self.enhanced_generator.generate_and_save_outfits(
            user_id=user_id,
            occasion=occasion,
            weather=weather,
            num_outfits=num_outfits,
            focus_item_id=focus_item_id
        )