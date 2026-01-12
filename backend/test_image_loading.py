from mongodb_client import db_client
from wardrobe_database import WardrobeDatabase

db = WardrobeDatabase()
items = db.get_user_items("anonymous")

if items:
    item = items[0]
    print(f"Item ID: {item.get('_id')}")
    print(f"Image file ID: {item.get('image_file_id')}")
    
    # Try loading image
    if item.get('image_file_id'):
        try:
            image_data = db_client.get_image_base64(item['image_file_id'])
            print(f"✅ Image loaded: {len(image_data)} characters")
        except Exception as e:
            print(f"❌ Failed to load image: {e}")
