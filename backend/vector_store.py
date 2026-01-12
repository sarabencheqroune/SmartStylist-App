import chromadb
from chromadb.config import Settings
from typing import List, Dict
import numpy as np

class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path="./chroma_db",
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            name="wardrobe_embeddings"
        )
    
    def add_item_embedding(self, item_id: str, item_data: Dict):
        """Create embedding from item data and store in vector DB."""
        # Create text representation
        text = f"{item_data.get('category', '')} {item_data.get('color', '')} "
        text += f"{item_data.get('formality', '')} {' '.join(item_data.get('style_tags', []))}"
        
        # Generate embedding (simplified - in production use sentence-transformers)
        embedding = self._create_embedding(text)
        
        # Store in vector DB
        self.collection.add(
            ids=[item_id],
            embeddings=[embedding],
            metadatas=[{
                "category": item_data.get("category"),
                "formality": item_data.get("formality"),
                "season": item_data.get("season")
            }]
        )
    
    def find_similar_items(self, query: str, k: int = 10) -> List[str]:
        """Find similar items using vector similarity."""
        query_embedding = self._create_embedding(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=k
        )
        return results["ids"][0] if results["ids"] else []
    
    def _create_embedding(self, text: str) -> List[float]:
        """Simple embedding creation. Replace with proper model in production."""
        # This is a placeholder - use sentence-transformers in production
        import hashlib
        hash_obj = hashlib.md5(text.encode())
        hex_dig = hash_obj.hexdigest()
        
        # Create deterministic "embedding" from hash
        np.random.seed(int(hex_dig[:8], 16))
        return list(np.random.randn(384))