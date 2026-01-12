from __future__ import annotations

import os
from typing import List, Dict, Optional, Any
from mongodb_client import db_client
from style_scoring import normalize_category  # FIX: Import normalize_category


class WardrobeDatabase:
    """Complete wardrobe database using MongoDBClient."""
    
    def __init__(self, vector_dir: str = "./wardrobe_db"):
        self.db = db_client
        
    def add_clothing_item(self, image_path: str, description: str, 
                         user_id: str = "anonymous", 
                         category: str = None,
                         analysis: Dict[str, Any] = None) -> str:
        """Add clothing item to wardrobe with analysis."""
        try:
            # Store image in GridFS
            file_id = self.db.save_image(image_path, user_id)
            
            # Create document
            doc = {
                "image_file_id": file_id,
                "image_path": image_path,
                "description": description,
                "user_id": user_id,
                "category": category or (analysis.get("category") if analysis else "unknown"),
                "color": analysis.get("color", "unknown") if analysis else "unknown",
                "style_tags": analysis.get("style_tags", []) if analysis else [],
                "season": analysis.get("season", "all-season") if analysis else "all-season",
                "formality": analysis.get("formality", "casual") if analysis else "casual",
                "analysis": analysis or {},
            }
            
            # Save to MongoDB
            item_id = self.db.save_clothing_item(doc)
            return item_id
            
        except Exception as e:
            raise Exception(f"Failed to add clothing item: {str(e)}")
    
    def add_clothing_item_with_analysis(self, item_data: Dict, analysis: Dict) -> str:
        """Add clothing item with pre-existing analysis."""
        return self.add_clothing_item(
            image_path=item_data.get("image_path", ""),
            description=item_data.get("description", ""),
            user_id=item_data.get("user_id", "anonymous"),
            category=item_data.get("category"),
            analysis=analysis
        )
    
    def get_user_items(self, user_id: str = "anonymous") -> List[Dict[str, Any]]:
        """Get all wardrobe items for a user."""
        try:
            items = self.db.list_clothing_items(user_id=user_id, limit=200)
        
            # Ensure all items have required fields
            for item in items:
                # Ensure _id is string
                if "_id" in item and not isinstance(item["_id"], str):
                    item["_id"] = str(item["_id"])
            
              # Ensure category exists and is normalized
                if "category" not in item or not item["category"]:
                    item["category"] = "unknown"
                else:
                    item["category"] = normalize_category(item["category"])
            
            # FIX: Ensure color is NEVER None - default to "unknown"
                if "color" not in item or item["color"] is None:
                    item["color"] = "unknown"
            
            # Ensure style_tags exists
                if "style_tags" not in item:
                    item["style_tags"] = []
            
            # Ensure formality exists
                if "formality" not in item:
                    item["formality"] = "casual"
            
            # Ensure season exists
                if "season" not in item:
                    item["season"] = "all-season"
        
            return items
        except Exception as e:
            print(f"Error getting user items: {e}")
            return []
    
    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get specific wardrobe item by ID."""
        return self.db.get_clothing_item(item_id)
    
    def get_items_by_category(self, category: str, user_id: str = "anonymous") -> List[Dict[str, Any]]:
        """Get items filtered by category.
        
        FIX: Now uses normalize_category() for consistent matching.
        """
        items = self.get_user_items(user_id)
        normalized_target = normalize_category(category)
        
        # Filter using normalized categories
        return [item for item in items 
                if normalize_category(item.get("category", "")) == normalized_target]
    
    def count_items(self, user_id: str = "anonymous") -> int:
        """Count total items in wardrobe."""
        items = self.get_user_items(user_id)
        return len(items)
    
    def count_by_category(self, user_id: str = "anonymous") -> Dict[str, int]:
        """Count items by category."""
        return self.db.count_by_category(user_id)
    
    def delete_item(self, item_id: str) -> bool:
        """Delete wardrobe item."""
        return self.db.delete_clothing_item(item_id)
    
    def search_items(self, query: str, user_id: str = "anonymous") -> List[Dict[str, Any]]:
        """Search items by description or tags."""
        items = self.get_user_items(user_id)
        query_lower = query.lower()
        
        results = []
        for item in items:
            # Search in description
            if query_lower in item.get("description", "").lower():
                results.append(item)
                continue
                
            # Search in category
            if query_lower in item.get("category", "").lower():
                results.append(item)
                continue
                
            # Search in style tags
            tags = item.get("style_tags", [])
            if any(query_lower in tag.lower() for tag in tags):
                results.append(item)
                continue
                
            # Search in color
            if query_lower in item.get("color", "").lower():
                results.append(item)
        
        return results


# For backward compatibility
def get_items_by_category(category: str) -> List[Dict[str, Any]]:
    """Legacy function."""
    db = WardrobeDatabase()
    return db.get_items_by_category(category)


def get_all_items() -> List[Dict[str, Any]]:
    """Legacy function - get all items for anonymous user."""
    db = WardrobeDatabase()
    return db.get_user_items("anonymous")
