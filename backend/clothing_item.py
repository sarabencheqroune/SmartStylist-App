from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

@dataclass
class ClothingItem:
    """Represents one wardrobe item."""
    image_path: str
    description: str
    category: Optional[str] = None
    color: Optional[str] = None
    style_tags: List[str] = field(default_factory=list)
    season: Optional[str] = None
    formality: Optional[str] = None
    mongo_id: Optional[str] = None  # stringified ObjectId

    def to_mongo_doc(self) -> Dict[str, Any]:
        return {
            "image_path": self.image_path,
            "description": self.description,
            "category": self.category,
            "color": self.color,
            "style_tags": self.style_tags,
            "season": self.season,
            "formality": self.formality,
        }
