"""Simple smoke tests for SmartStylist backend.

Run:
    python test_system.py
"""

import os
from dotenv import load_dotenv
load_dotenv()

from wardrobe_database import WardrobeDatabase
from outfit_generator import OutfitGenerator

def main():
    db = WardrobeDatabase()
    gen = OutfitGenerator(db)
    # If wardrobe is empty, generator returns an empty list (expected).
    weather = {"city":"Rabat","temp_c":22,"condition":"clear"}
    outfits = gen.generate_outfits("casual day out", weather, num_outfits=2)
    assert isinstance(outfits, list)
    if not outfits:
        print("✅ Smoke test passed (wardrobe empty => 0 outfits).")
        return

    print("✅ Smoke test passed. Generated:")
    for o in outfits:
        print("-", o.get("title"), ":", str(o.get("details", ""))[:80], "...")

if __name__ == "__main__":
    main()
