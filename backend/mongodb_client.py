from __future__ import annotations

import os
import io
import base64
import json
import uuid
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

from dotenv import load_dotenv
from pymongo import MongoClient
from bson import ObjectId
import gridfs

from config import MONGODB_URI, MONGODB_DB, MONGODB_COLLECTION

load_dotenv()

@dataclass
class DatabaseConfig:
    """Database configuration container."""
    uri: str = os.getenv("MONGODB_URI", MONGODB_URI)
    db_name: str = os.getenv("MONGODB_DB", MONGODB_DB)
    wardrobe_collection: str = os.getenv("MONGODB_COLLECTION", MONGODB_COLLECTION)
    outfit_history_collection: str = "outfit_history"
    users_collection: str = "users"
    images_bucket: str = "images"


class MongoDBClient:
    """Singleton MongoDB client with GridFS support."""
    _instance = None
    _client = None
    _db = None
    _fs = None
    _mode = "mongo"  # "mongo" or "local"
    _local_path = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MongoDBClient, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance
    
    def _init_client(self):
        """Initialize MongoDB connection (preferred) or fall back to a local JSON store."""
        config = DatabaseConfig()
        self._config = config

        # Local fallback DB file (in project folder)
        self._local_path = os.getenv("LOCAL_DB_PATH") or os.path.join(
            os.path.dirname(__file__), "local_db.json"
        )

        try:
            # Fast fail if MongoDB isn't reachable
            self._client = MongoClient(config.uri, serverSelectionTimeoutMS=1500)
            self._client.admin.command("ping")
            self._db = self._client[config.db_name]
            self._fs = gridfs.GridFS(self._db)
            self._mode = "mongo"
            print(f"✅ Connected to MongoDB: {config.db_name}")

            # Create indexes
            self._create_indexes()
        except Exception as e:
            # Fallback mode: use a JSON file on disk.
            print(f"⚠️ MongoDB connection failed, using local fallback: {e}")
            self._client = None
            self._db = None
            self._fs = None
            self._mode = "local"
            self._ensure_local_db()
            print("✅ Using local fallback storage")

    # ==================== LOCAL FALLBACK STORE ====================

    def _ensure_local_db(self) -> None:
        """Ensure local JSON database file exists."""
        if not self._local_path:
            return
        if not os.path.exists(self._local_path):
            os.makedirs(os.path.dirname(self._local_path), exist_ok=True)
            with open(self._local_path, "w", encoding="utf-8") as f:
                json.dump({"wardrobe_items": [], "outfit_history": []}, f)

    def _load_local(self) -> Dict[str, Any]:
        """Load data from local JSON file."""
        self._ensure_local_db()
        try:
            with open(self._local_path, "r", encoding="utf-8") as f:
                return json.load(f) or {"wardrobe_items": [], "outfit_history": []}
        except Exception:
            return {"wardrobe_items": [], "outfit_history": []}

    def _save_local(self, data: Dict[str, Any]) -> None:
        """Save data to local JSON file."""
        self._ensure_local_db()
        with open(self._local_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    def _create_indexes(self):
        """Create necessary database indexes."""
        if self._db is None:  # FIX: Check if db is not None
            return
            
        # Wardrobe items indexes
        wardrobe_coll = self._db[self._config.wardrobe_collection]
        wardrobe_coll.create_index("category")
        wardrobe_coll.create_index("style_tags")
        wardrobe_coll.create_index([("user_id", 1), ("created_at", -1)])
        wardrobe_coll.create_index([("category", 1), ("formality", 1)])
        
        # Outfit history indexes
        history_coll = self._db[self._config.outfit_history_collection]
        history_coll.create_index([("user_id", 1), ("generated_at", -1)])
        history_coll.create_index([("user_id", 1), ("metadata.tags", 1)])
        history_coll.create_index("metadata.tags")
        history_coll.create_index("occasion")
        history_coll.create_index([("items.item_id", 1)])
    
    # ==================== IMAGE STORAGE (GridFS) ====================
    
    def save_image(self, image_path: str, user_id: Optional[str] = None) -> str:
        """Save image to GridFS and return file_id."""
        if self._mode == "local":
            # Local mode: we don't use GridFS. Keep the original path.
            return f"local:{os.path.basename(image_path)}"
        
        if self._fs is None:  # FIX: Check if fs is not None
            raise Exception("GridFS not initialized")
            
        try:
            with open(image_path, 'rb') as f:
                metadata = {
                    "filename": os.path.basename(image_path),
                    "uploaded_at": datetime.utcnow(),
                    "user_id": user_id
                }
                file_id = self._fs.put(f, **metadata)
                return str(file_id)
        except Exception as e:
            raise Exception(f"Failed to save image to GridFS: {str(e)}")
    
    def save_image_bytes(self, image_bytes: bytes, filename: str, 
                        user_id: Optional[str] = None) -> str:
        """Save image bytes to GridFS."""
        if self._mode == "local":
            # Best-effort local save next to the JSON DB
            uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
            os.makedirs(uploads_dir, exist_ok=True)
            path = os.path.join(uploads_dir, filename)
            with open(path, "wb") as f:
                f.write(image_bytes)
            return f"local:{filename}"
        
        if self._fs is None:  # FIX: Check if fs is not None
            raise Exception("GridFS not initialized")
            
        metadata = {
            "filename": filename,
            "uploaded_at": datetime.utcnow(),
            "user_id": user_id
        }
        file_id = self._fs.put(image_bytes, **metadata)
        return str(file_id)
    
    def get_image(self, file_id: str) -> Tuple[bytes, Dict[str, Any]]:
        """Retrieve image and metadata from GridFS."""
        if self._mode == "local":
            # In local mode, file_id is either "local:<name>" or a path.
            name = str(file_id)
            if name.startswith("local:"):
                name = name.split(":", 1)[1]
            # Try both backend/uploads and absolute/relative paths
            candidates = [
                os.path.join(os.path.dirname(__file__), "uploads", name),
                name,
            ]
            for p in candidates:
                try:
                    if os.path.exists(p):
                        with open(p, "rb") as f:
                            return f.read(), {"filename": os.path.basename(p), "uploaded_at": None, "user_id": None}
                except Exception:
                    continue
            raise Exception("Image not found in local store")
        
        if self._fs is None:  # FIX: Check if fs is not None
            raise Exception("GridFS not initialized")
            
        try:
            file_data = self._fs.get(ObjectId(file_id))
            metadata = {
                "filename": file_data.filename,
                "uploaded_at": file_data.upload_date,
                "user_id": file_data.user_id if hasattr(file_data, 'user_id') else None
            }
            return file_data.read(), metadata
        except Exception as e:
            raise Exception(f"Failed to retrieve image from GridFS: {str(e)}")
    
    def get_image_base64(self, file_id: str) -> str:
        """Get image as base64 string for frontend display."""
        image_bytes, _ = self.get_image(file_id)
        return base64.b64encode(image_bytes).decode('utf-8')
    
    def delete_image(self, file_id: str) -> bool:
        """Delete image from GridFS."""
        if self._mode == "local":
            return False
        
        if self._fs is None:  # FIX: Check if fs is not None
            return False
            
        try:
            self._fs.delete(ObjectId(file_id))
            return True
        except Exception:
            return False
    
    # ==================== WARDROBE ITEMS ====================
    
    def save_clothing_item(self, doc: Dict[str, Any]) -> str:
        """Save clothing item to wardrobe collection."""
        if self._mode == "local":
            data = self._load_local()
            item_id = uuid.uuid4().hex
            doc = dict(doc)
            doc["_id"] = item_id
            doc["created_at"] = datetime.utcnow().isoformat()
            doc["updated_at"] = datetime.utcnow().isoformat()
            data.setdefault("wardrobe_items", []).append(doc)
            self._save_local(data)
            return item_id

        if self._db is None:  # FIX: Check if db is not None
            raise Exception("Database not initialized")
            
        doc["created_at"] = datetime.utcnow()
        doc["updated_at"] = datetime.utcnow()

        coll = self._db[self._config.wardrobe_collection]
        result = coll.insert_one(doc)
        return str(result.inserted_id)
    
    def update_clothing_item(self, item_id: str, updates: Dict[str, Any]) -> bool:
        """Update clothing item."""
        if self._mode == "local":
            data = self._load_local()
            items = data.get("wardrobe_items", [])
            changed = False
            for it in items:
                if str(it.get("_id")) == str(item_id):
                    it.update(dict(updates))
                    it["updated_at"] = datetime.utcnow().isoformat()
                    changed = True
                    break
            if changed:
                self._save_local(data)
            return changed

        if self._db is None:  # FIX: Check if db is not None
            raise Exception("Database not initialized")
            
        updates["updated_at"] = datetime.utcnow()

        coll = self._db[self._config.wardrobe_collection]
        result = coll.update_one(
            {"_id": ObjectId(item_id)},
            {"$set": updates}
        )
        return result.modified_count > 0
    
    def get_clothing_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific clothing item."""
        if self._mode == "local":
            data = self._load_local()
            for doc in data.get("wardrobe_items", []):
                if str(doc.get("_id")) == str(item_id):
                    # Best-effort image base64 (optional)
                    if doc.get("image_path") and os.path.exists(doc["image_path"]):
                        try:
                            with open(doc["image_path"], "rb") as f:
                                doc["image_base64"] = base64.b64encode(f.read()).decode("utf-8")
                        except Exception:
                            pass
                    return doc
            return None

        if self._db is None:  # FIX: Check if db is not None
            return None
            
        coll = self._db[self._config.wardrobe_collection]
        doc = coll.find_one({"_id": ObjectId(item_id)})

        if doc:
            doc["_id"] = str(doc["_id"])
            if "image_file_id" in doc:
                try:
                    doc["image_base64"] = self.get_image_base64(doc["image_file_id"])
                except Exception:
                    doc["image_base64"] = None
            return doc
        return None
    
    def get_clothing_items_by_user(self, user_id: str, limit: int = 100, 
                                  skip: int = 0) -> List[Dict[str, Any]]:
        """Get clothing items for a specific user."""
        if self._mode == "local":
            data = self._load_local()
            items = [it for it in data.get("wardrobe_items", []) if it.get("user_id") == user_id]
            items = sorted(items, key=lambda d: str(d.get("created_at", "")), reverse=True)
            return items[skip:skip + limit]

        if self._db is None:  # FIX: Check if db is not None
            return []
            
        coll = self._db[self._config.wardrobe_collection]
        cursor = coll.find({"user_id": user_id}) \
                      .sort("created_at", -1) \
                      .skip(skip) \
                      .limit(limit)
        
        items = []
        for doc in cursor:
            doc["_id"] = str(doc["_id"])
            if "image_file_id" in doc:
                try:
                    doc["image_base64"] = self.get_image_base64(doc["image_file_id"])
                except Exception:
                    doc["image_base64"] = None
            items.append(doc)
        
        return items
    
    def list_clothing_items(self, user_id: Optional[str] = None, 
                           limit: int = 200, skip: int = 0) -> List[Dict[str, Any]]:
        """List all clothing items, optionally filtered by user."""
        if self._mode == "local":
            data = self._load_local()
            items = data.get("wardrobe_items", [])
            if user_id:
                items = [it for it in items if it.get("user_id") == user_id]
            # Sort newest first (created_at iso)
            items = sorted(items, key=lambda d: str(d.get("created_at", "")), reverse=True)
            return items[skip:skip + limit]

        if self._db is None:  # FIX: Check if db is not None
            return []
            
        coll = self._db[self._config.wardrobe_collection]

        query = {}
        if user_id:
            query["user_id"] = user_id

        docs = list(coll.find(query)
                   .sort([("created_at", -1)])
                   .skip(skip)
                   .limit(limit))

        for doc in docs:
            doc["_id"] = str(doc["_id"])
            if "image_file_id" in doc:
                try:
                    doc["image_base64"] = self.get_image_base64(doc["image_file_id"])
                except Exception:
                    doc["image_base64"] = None

        return docs
    
    def count_by_category(self, user_id: Optional[str] = None) -> Dict[str, int]:
        """Count items by category."""
        if self._mode == "local":
            data = self._load_local()
            items = data.get("wardrobe_items", [])
            if user_id:
                items = [it for it in items if it.get("user_id") == user_id]
            
            result = {}
            for item in items:
                category = item.get("category", "unknown")
                result[category] = result.get(category, 0) + 1
            return result

        if self._db is None:  # FIX: Check if db is not None
            return {}
            
        coll = self._db[self._config.wardrobe_collection]
        
        query = {}
        if user_id:
            query["user_id"] = user_id
        
        pipeline = [
            {"$match": query},
            {"$group": {"_id": "$category", "count": {"$sum": 1}}}
        ]
        
        result = {}
        for doc in coll.aggregate(pipeline):
            result[doc["_id"]] = doc["count"]
        
        return result
    
    def delete_clothing_item(self, item_id: str) -> bool:
        """Delete clothing item and its associated image."""
        if self._mode == "local":
            data = self._load_local()
            before = len(data.get("wardrobe_items", []))
            data["wardrobe_items"] = [it for it in data.get("wardrobe_items", []) if str(it.get("_id")) != str(item_id)]
            after = len(data.get("wardrobe_items", []))
            self._save_local(data)
            return after < before

        if self._db is None:  # FIX: Check if db is not None
            return False
            
        coll = self._db[self._config.wardrobe_collection]

        # Get item first to delete image
        item = coll.find_one({"_id": ObjectId(item_id)})
        if item and "image_file_id" in item:
            self.delete_image(item["image_file_id"])

        # Delete the item
        result = coll.delete_one({"_id": ObjectId(item_id)})
        return result.deleted_count > 0
    
    # ==================== OUTFIT HISTORY ====================
    
    def save_outfit_to_history(self, user_id: str, outfits: List[Dict[str, Any]], 
                              occasion: str, weather: Dict[str, Any], 
                              user_feedback: Optional[Dict] = None) -> List[str]:
        """Save generated outfits to history."""
        if self._mode == "local":
            data = self._load_local()
            outfit_ids: List[str] = []
            for outfit in outfits:
                oid = uuid.uuid4().hex
                doc = {
                    "_id": oid,
                    "user_id": user_id,
                    "title": outfit.get("title", f"Outfit for {occasion}"),
                    "details": outfit.get("details", outfit.get("description", "")),
                    "items": outfit.get("items", []),
                    "occasion": occasion,
                    "weather": weather,
                    "generated_at": datetime.utcnow().isoformat(),
                    "user_feedback": user_feedback or {},
                    "metadata": {"tags": []},
                }
                data.setdefault("outfit_history", []).append(doc)
                outfit_ids.append(oid)
            self._save_local(data)
            return outfit_ids

        if self._db is None:  # FIX: Check if db is not None
            raise Exception("Database not initialized")
            
        coll = self._db[self._config.outfit_history_collection]
        
        outfit_ids = []
        for outfit in outfits:
            doc = {
                "user_id": user_id,
                "title": outfit.get("title", f"Outfit for {occasion}"),
                "details": outfit.get("details", ""),
                "items": [
                    {
                        "item_id": item.get("id"),
                        "image_file_id": item.get("image_file_id"),
                        "category": item.get("category"),
                        "color": item.get("color"),
                        "style_tags": item.get("style_tags", [])
                    }
                    for item in outfit.get("items", [])
                ],
                "occasion": occasion,
                "weather": {
                    "city": weather.get("city"),
                    "temp_c": weather.get("temp_c"),
                    "temp_f": weather.get("temp_f"),
                    "condition": weather.get("condition"),
                    "description": weather.get("description", "")
                },
                "generated_at": datetime.utcnow(),
                "user_feedback": user_feedback or {},
                "metadata": {
                    "outfit_score": outfit.get("score", 0.0),
                    "tags": outfit.get("tags", []),
                    "generation_params": {
                        "focus_item_id": outfit.get("focus_item_id"),
                        "num_outfits": len(outfits)
                    }
                }
            }
            
            result = coll.insert_one(doc)
            outfit_ids.append(str(result.inserted_id))
        
        return outfit_ids
    
    def get_outfit_history(self, user_id: str, limit: int = 50, 
                          skip: int = 0, sort_by: str = "generated_at", 
                          sort_order: int = -1) -> List[Dict[str, Any]]:
        """Retrieve outfit history for a user."""
        if self._mode == "local":
            data = self._load_local()
            outfits = [o for o in data.get("outfit_history", []) if o.get("user_id") == user_id]
            outfits = sorted(outfits, key=lambda d: str(d.get(sort_by, "")), reverse=(sort_order == -1))
            return outfits[skip:skip + limit]

        if self._db is None:  # FIX: Check if db is not None
            return []
            
        coll = self._db[self._config.outfit_history_collection]
        
        outfits = list(
            coll.find({"user_id": user_id})
            .sort(sort_by, sort_order)
            .skip(skip)
            .limit(limit)
        )
        
        # Convert ObjectId and datetime for JSON serialization
        for outfit in outfits:
            outfit["_id"] = str(outfit["_id"])
            outfit["generated_at"] = outfit["generated_at"].isoformat()
            
            # Add base64 images for frontend display
            for item in outfit.get("items", []):
                if "image_file_id" in item:
                    try:
                        item["image_base64"] = self.get_image_base64(item["image_file_id"])
                    except:
                        item["image_base64"] = None
        
        return outfits
    
    def get_outfit_by_id(self, outfit_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get a specific outfit by ID."""
        if self._mode == "local":
            data = self._load_local()
            for o in data.get("outfit_history", []):
                if str(o.get("_id")) == str(outfit_id) and (not user_id or o.get("user_id") == user_id):
                    return o
            return None

        if self._db is None:  # FIX: Check if db is not None
            return None
            
        coll = self._db[self._config.outfit_history_collection]
        
        query = {"_id": ObjectId(outfit_id)}
        if user_id:
            query["user_id"] = user_id
        
        doc = coll.find_one(query)
        if not doc:
            return None
        
        doc["_id"] = str(doc["_id"])
        doc["generated_at"] = doc["generated_at"].isoformat()
        
        # Add base64 images
        for item in doc.get("items", []):
            if "image_file_id" in item:
                try:
                    item["image_base64"] = self.get_image_base64(item["image_file_id"])
                except:
                    item["image_base64"] = None
        
        return doc
    
    def update_outfit_feedback(self, outfit_id: str, user_id: str, 
                              feedback_updates: Dict[str, Any]) -> bool:
        """Update user feedback for an outfit."""
        if self._mode == "local":
            data = self._load_local()
            changed = False
            for o in data.get("outfit_history", []):
                if str(o.get("_id")) == str(outfit_id) and o.get("user_id") == user_id:
                    o["user_feedback"] = feedback_updates
                    o["updated_at"] = datetime.utcnow().isoformat()
                    changed = True
                    break
            if changed:
                self._save_local(data)
            return changed

        if self._db is None:  # FIX: Check if db is not None
            return False
            
        coll = self._db[self._config.outfit_history_collection]
        
        result = coll.update_one(
            {"_id": ObjectId(outfit_id), "user_id": user_id},
            {
                "$set": {
                    "user_feedback": feedback_updates,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        return result.modified_count > 0
    
    def add_outfit_tag(self, outfit_id: str, user_id: str, tag: str) -> bool:
        """Add a tag to an outfit."""
        if self._mode == "local":
            data = self._load_local()
            changed = False
            for o in data.get("outfit_history", []):
                if str(o.get("_id")) == str(outfit_id) and o.get("user_id") == user_id:
                    meta = o.setdefault("metadata", {})
                    tags = meta.setdefault("tags", [])
                    if tag not in tags:
                        tags.append(tag)
                        changed = True
                    break
            if changed:
                self._save_local(data)
            return changed
        
        if self._db is None:  # FIX: Check if db is not None
            return False
            
        coll = self._db[self._config.outfit_history_collection]
        
        result = coll.update_one(
            {"_id": ObjectId(outfit_id), "user_id": user_id},
            {"$addToSet": {"metadata.tags": tag}}
        )
        
        return result.modified_count > 0
    
    def remove_outfit_tag(self, outfit_id: str, user_id: str, tag: str) -> bool:
        """Remove a tag from an outfit."""
        if self._db is None:  # FIX: Check if db is not None
            return False
            
        coll = self._db[self._config.outfit_history_collection]
        
        result = coll.update_one(
            {"_id": ObjectId(outfit_id), "user_id": user_id},
            {"$pull": {"metadata.tags": tag}}
        )
        
        return result.modified_count > 0
    
    def get_favorite_outfits(self, user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get outfits marked as favorites."""
        if self._mode == "local":
            data = self._load_local()
            outfits = [o for o in data.get("outfit_history", []) if o.get("user_id") == user_id and "favorite" in (o.get("metadata", {}).get("tags", []) or [])]
            outfits = sorted(outfits, key=lambda d: str(d.get("generated_at", "")), reverse=True)
            return outfits[:limit]
        
        if self._db is None:  # FIX: Check if db is not None
            return []
            
        coll = self._db[self._config.outfit_history_collection]
        
        outfits = list(
            coll.find({
                "user_id": user_id,
                "metadata.tags": "favorite"
            })
            .sort("generated_at", -1)
            .limit(limit)
        )
        
        for outfit in outfits:
            outfit["_id"] = str(outfit["_id"])
            outfit["generated_at"] = outfit["generated_at"].isoformat()
            
            # Add base64 images
            for item in outfit.get("items", []):
                if "image_file_id" in item:
                    try:
                        item["image_base64"] = self.get_image_base64(item["image_file_id"])
                    except:
                        item["image_base64"] = None
        
        return outfits
    
    def get_outfits_containing_item(self, item_id: str, user_id: str, 
                                   limit: int = 50) -> List[Dict[str, Any]]:
        """Get all outfits that contain a specific wardrobe item."""
        if self._db is None:  # FIX: Check if db is not None
            return []
            
        coll = self._db[self._config.outfit_history_collection]
        
        outfits = list(
            coll.find({
                "user_id": user_id,
                "items.item_id": item_id
            })
            .sort("generated_at", -1)
            .limit(limit)
        )
        
        for outfit in outfits:
            outfit["_id"] = str(outfit["_id"])
            outfit["generated_at"] = outfit["generated_at"].isoformat()
        
        return outfits
    
    def delete_outfit(self, outfit_id: str, user_id: str) -> bool:
        """Delete an outfit from history."""
        if self._db is None:  # FIX: Check if db is not None
            return False
            
        coll = self._db[self._config.outfit_history_collection]
        
        result = coll.delete_one({
            "_id": ObjectId(outfit_id),
            "user_id": user_id
        })
        
        return result.deleted_count > 0
    
    # ==================== USER MANAGEMENT ====================
    
    def create_user(self, user_data: Dict[str, Any]) -> str:
        """Create a new user."""
        if self._db is None:  # FIX: Check if db is not None
            raise Exception("Database not initialized")
            
        coll = self._db[self._config.users_collection]
        
        user_data["created_at"] = datetime.utcnow()
        user_data["updated_at"] = datetime.utcnow()
        
        result = coll.insert_one(user_data)
        return str(result.inserted_id)
    
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID."""
        if self._db is None:  # FIX: Check if db is not None
            return None
            
        coll = self._db[self._config.users_collection]
        
        doc = coll.find_one({"_id": ObjectId(user_id)})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email."""
        if self._db is None:  # FIX: Check if db is not None
            return None
            
        coll = self._db[self._config.users_collection]
        
        doc = coll.find_one({"email": email})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc
    
    def update_user(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update user information."""
        if self._db is None:  # FIX: Check if db is not None
            return False
            
        coll = self._db[self._config.users_collection]
        
        updates["updated_at"] = datetime.utcnow()
        result = coll.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": updates}
        )
        
        return result.modified_count > 0
    
    # ==================== STATISTICS ====================
    
    def get_user_statistics(self, user_id: str) -> Dict[str, Any]:
        """Get statistics for a user."""
        if self._mode == "local":
            data = self._load_local()
            wardrobe_items = [it for it in data.get("wardrobe_items", []) if it.get("user_id") == user_id]
            outfits = [o for o in data.get("outfit_history", []) if o.get("user_id") == user_id]
            
            # Count by category
            category_counts = {}
            for item in wardrobe_items:
                category = item.get("category", "unknown")
                category_counts[category] = category_counts.get(category, 0) + 1
            
            # Count favorite outfits
            favorite_outfits = sum(1 for o in outfits if "favorite" in (o.get("metadata", {}).get("tags", []) or []))
            
            return {
                "wardrobe": {
                    "total_items": len(wardrobe_items),
                    "by_category": category_counts
                },
                "outfits": {
                    "total_generated": len(outfits),
                    "favorites": favorite_outfits,
                    "most_used_items": []
                }
            }

        if self._db is None:  # FIX: Check if db is not None
            return {"wardrobe": {"total_items": 0, "by_category": {}}, 
                    "outfits": {"total_generated": 0, "favorites": 0, "most_used_items": []}}
            
        wardrobe_coll = self._db[self._config.wardrobe_collection]
        history_coll = self._db[self._config.outfit_history_collection]
        
        # Count wardrobe items
        total_items = wardrobe_coll.count_documents({"user_id": user_id})
        
        # Count by category
        category_counts = self.count_by_category(user_id)
        
        # Count outfits generated
        total_outfits = history_coll.count_documents({"user_id": user_id})
        
        # Favorite outfits
        favorite_outfits = history_coll.count_documents({
            "user_id": user_id,
            "metadata.tags": "favorite"
        })
        
        # Most used items
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$unwind": "$items"},
            {"$group": {"_id": "$items.item_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 5}
        ]
        
        most_used = list(history_coll.aggregate(pipeline))
        
        return {
            "wardrobe": {
                "total_items": total_items,
                "by_category": category_counts
            },
            "outfits": {
                "total_generated": total_outfits,
                "favorites": favorite_outfits,
                "most_used_items": most_used
            }
        }
    
    # ==================== CLEANUP ====================
    
    def close(self):
        """Close MongoDB connection."""
        if self._client:
            self._client.close()


# Singleton instance
db_client = MongoDBClient()


# Legacy functions for backward compatibility
def save_clothing_item(doc: Dict[str, Any]) -> str:
    return db_client.save_clothing_item(doc)

def update_clothing_item(item_id: str, updates: Dict[str, Any]) -> bool:
    return db_client.update_clothing_item(item_id, updates)

def get_clothing_item(item_id: str) -> Optional[Dict[str, Any]]:
    return db_client.get_clothing_item(item_id)

def list_clothing_items(limit: int = 200) -> List[Dict[str, Any]]:
    return db_client.list_clothing_items(limit=limit)

def save_outfit_to_history(user_id: Optional[str], outfits: List[Dict[str, Any]], 
                          occasion: str, weather: Dict[str, Any], 
                          user_feedback: Optional[Dict] = None) -> List[str]:
    if not user_id:
        user_id = "anonymous"
    return db_client.save_outfit_to_history(user_id, outfits, occasion, weather, user_feedback)

def get_outfit_history(user_id: Optional[str] = None, limit: int = 50, 
                      skip: int = 0, sort_by: str = "generated_at", 
                      sort_order: int = -1) -> List[Dict[str, Any]]:
    if not user_id:
        user_id = "anonymous"
    return db_client.get_outfit_history(user_id, limit, skip, sort_by, sort_order)

def get_outfit_by_id(outfit_id: str) -> Optional[Dict[str, Any]]:
    return db_client.get_outfit_by_id(outfit_id)

def update_outfit_feedback(outfit_id: str, feedback_updates: Dict[str, Any]) -> bool:
    # Note: This legacy function doesn't have user_id, using "anonymous"
    return db_client.update_outfit_feedback(outfit_id, "anonymous", feedback_updates)

def add_outfit_tag(outfit_id: str, tag: str) -> bool:
    # Note: This legacy function doesn't have user_id, using "anonymous"
    return db_client.add_outfit_tag(outfit_id, "anonymous", tag)

def get_favorite_outfits(user_id: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    if not user_id:
        user_id = "anonymous"
    return db_client.get_favorite_outfits(user_id, limit)
# Add debug logging to _init_client() method:

def _init_client(self):
    """Initialize MongoDB connection (preferred) or fall back to a local JSON store."""
    config = DatabaseConfig()
    self._config = config
    
    print(f"🔧 MongoDB URI: {config.uri}")
    print(f"🔧 Database name: {config.db_name}")
    
    try:
        # Try MongoDB with timeout
        self._client = MongoClient(config.uri, serverSelectionTimeoutMS=3000)  # Increased timeout
        self._client.admin.command("ping")
        self._db = self._client[config.db_name]
        self._fs = gridfs.GridFS(self._db)
        self._mode = "mongo"
        print(f"✅ Connected to MongoDB: {config.db_name}")
        
        # Test connection with a simple operation
        test_coll = self._db["test"]
        test_coll.insert_one({"test": datetime.utcnow()})
        print("✅ MongoDB write test successful")
        
        self._create_indexes()
        
    except Exception as e:
        print(f"⚠️ MongoDB connection failed: {e}")
        print("🔄 Switching to local fallback mode...")
        self._client = None
        self._db = None
        self._fs = None
        self._mode = "local"
        self._ensure_local_db()
        print("✅ Using local fallback storage")