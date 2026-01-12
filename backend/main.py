from __future__ import annotations

import os
from dotenv import load_dotenv

load_dotenv()

from clothing_item import ClothingItem
from gemini_analyzer import analyze_clothing_image
from wardrobe_database import WardrobeDatabase
from outfit_generator import OutfitGenerator

# Initialize core singletons used by the Flask API
wardrobe_db = WardrobeDatabase(vector_dir=os.getenv("VECTOR_DIR", "./wardrobe_db"))
outfit_gen = OutfitGenerator(wardrobe_db)

def add_clothing_to_wardrobe(image_path: str, user_description: str, user_id: str = "anonymous") -> dict:
    """Analyze + store item (MongoDB mandatory) and return stored document info."""
    analysis = analyze_clothing_image(image_path, user_description)
    
    # FIX: Call add_clothing_item with correct parameters
    item_id = wardrobe_db.add_clothing_item(
        image_path=image_path,
        description=user_description,
        user_id=user_id,
        analysis=analysis
    )

    return {
        "item_id": item_id,
        "analysis": analysis
    }
