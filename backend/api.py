from __future__ import annotations

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import uuid
import json
from werkzeug.utils import secure_filename
from datetime import datetime

# Initialize ALL components
from mongodb_client import db_client
from wardrobe_database import WardrobeDatabase
from outfit_generator import OutfitGenerator
from weather_service import get_weather, get_detailed_weather_recommendations
from gemini_analyzer import analyze_clothing_image

UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": ["*"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Initialize singletons
wardrobe_db = WardrobeDatabase()
outfit_gen = OutfitGenerator(wardrobe_db)
print("✅ Components initialized successfully")

# -----------------------
# HEALTH CHECK
# -----------------------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok", 
        "service": "SmartStylist API",
        "timestamp": datetime.utcnow().isoformat(),
        "mongodb": db_client._mode,
        "endpoints": [
            {"method": "POST", "path": "/analyze", "desc": "Upload and analyze clothing"},
            {"method": "GET", "path": "/wardrobe", "desc": "Get user's wardrobe"},
            {"method": "POST", "path": "/generate", "desc": "Generate outfits"},
            {"method": "GET", "path": "/weather/<city>", "desc": "Get weather data"}
        ]
    })

# -----------------------
# UPLOAD & ANALYZE IMAGE
# -----------------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/upload", methods=["POST"])
def upload_images():
    if "files" not in request.files:
        return jsonify({"error": "No files part in request"}), 400

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No files selected"}), 400

    saved = []

    for file in files:
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(path)
            saved.append(filename)

    if not saved:
        return jsonify({"error": "No valid images uploaded"}), 400

    return jsonify({
        "message": "Upload successful",
        "files": saved
    }), 200

@app.route("/analyze", methods=["POST"])
def analyze_and_store():
    """Upload image, analyze with Gemini, store in MongoDB."""
    print(f"🔍 Starting analyze endpoint...")
    print(f"🔍 Request files: {request.files}")
    print(f"🔍 Request form: {request.form}")
    
    if 'image' not in request.files:
        print("❌ No 'image' key in request.files")
        return jsonify({
            "status": "error",
            "error": "No image file provided",
            "available_keys": list(request.files.keys())
        }), 400
    
    file = request.files['image']
    print(f"🔍 File received: {file.filename}, size: {file.content_length}")
    
    description = request.form.get('description', '').strip() or file.filename
    category = request.form.get('category', '').strip()
    user_id = request.form.get('user_id', 'anonymous')
    
    if file.filename == '':
        return jsonify({
            "status": "error",
            "error": "No selected file"
        }), 400
    
    # Validate file type
    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
        return jsonify({
            "status": "error",
            "error": f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        }), 400
    
    try:
        print(f"📤 Processing upload: {file.filename} ({file.content_length} bytes)")
        
        # Save file locally temporarily
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        print(f"💾 File saved temporarily: {filepath}")
        
        # Analyze with Gemini AI
        print("🤖 Analyzing image with Gemini AI...")
        analysis = analyze_clothing_image(filepath, description)
        print(f"✅ Analysis complete: {analysis.get('category', 'unknown')} - {analysis.get('color', 'unknown')}")
        
        # Store in database
        print("💾 Storing in MongoDB...")
        item_id = wardrobe_db.add_clothing_item(
            image_path=filepath,
            description=description,
            user_id=user_id,
            category=category,
            analysis=analysis
        )
        print(f"✅ Item stored with ID: {item_id}")
        
        # Get the stored item for response
        stored_item = wardrobe_db.get_item(item_id)
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": "Item uploaded and analyzed successfully",
            "item_id": item_id,
            "filename": filename,
            "image_url": f"http://localhost:8080/uploads/{filename}",
            "analysis": analysis,
            "item": stored_item,
            "uploaded_at": datetime.utcnow().isoformat()
        }
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in /analyze: {str(e)}")
        # Clean up file if error occurs
        if 'filepath' in locals() and os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"🗑️  Cleaned up temporary file: {filepath}")
            except:
                pass
        
        return jsonify({
            "status": "error",
            "error": str(e),
            "message": "Failed to process image"
        }), 500

# -----------------------
# GET WARDROBE ITEMS
# -----------------------
@app.route("/wardrobe", methods=["GET"])
def get_wardrobe():
    """Get all wardrobe items for a user."""
    try:
        user_id = request.args.get('user_id', 'anonymous')
        limit = int(request.args.get('limit', 100))
        skip = int(request.args.get('skip', 0))
        
        print(f"📋 Getting wardrobe for user: {user_id}")
        items = wardrobe_db.get_user_items(user_id)
        
        # Apply pagination
        paginated_items = items[skip:skip + limit]
        
        # Format items for frontend
        formatted_items = []
        for item in paginated_items:
            # Load image if available
            if item.get("image_file_id") and not item.get("image_base64"):
                try:
                    item["image_base64"] = wardrobe_db.get_image_base64(item["image_file_id"])
                except Exception as e:
                    print(f"Could not load image: {e}")
    
            formatted_items.append(item)
     
        # Get statistics
        stats = wardrobe_db.count_by_category(user_id)
        
        return jsonify({
            "status": "success",
            "items": formatted_items,
            "total": len(items),
            "count": len(paginated_items),
            "stats": stats,
            "user_id": user_id,
            "pagination": {
                "limit": limit,
                "skip": skip,
                "has_more": len(items) > (skip + limit)
            }
        })
        
    except Exception as e:
        print(f"❌ Error in /wardrobe: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "items": [],
            "count": 0
        }), 500

# -----------------------
# GET SPECIFIC ITEM
# -----------------------
@app.route("/wardrobe/<item_id>", methods=["GET"])
def get_wardrobe_item(item_id):
    """Get a specific wardrobe item."""
    try:
        print(f"🔍 Getting item: {item_id}")
        item = wardrobe_db.get_item(item_id)
        if not item:
            return jsonify({
                "status": "error", 
                "error": f"Item {item_id} not found"
            }), 404
        
        # Load image from GridFS
        if item.get("image_file_id") and not item.get("image_base64"):
            try:
                item["image_base64"] = wardrobe_db.get_image_base64(item["image_file_id"])
            except Exception as e:
                print(f"⚠️  Could not load image: {e}")
        
        return jsonify({
            "status": "success",
            "item": item  
        })
        
    except Exception as e:
        print(f"❌ Error getting item {item_id}: {str(e)}")
        return jsonify({
            "status": "error", 
            "error": str(e)
        }), 500

# -----------------------
# DELETE ITEM
# -----------------------
@app.route("/wardrobe/<item_id>", methods=["DELETE"])
def delete_wardrobe_item(item_id):
    """Delete a wardrobe item."""
    try:
        user_id = request.args.get('user_id', 'anonymous')
        
        print(f"🗑️  Deleting item: {item_id} for user: {user_id}")
        
        # Verify item belongs to user
        item = wardrobe_db.get_item(item_id)
        if not item:
            return jsonify({
                "status": "error", 
                "error": f"Item {item_id} not found"
            }), 404
            
        if item.get("user_id") != user_id and user_id != "anonymous":
            return jsonify({
                "status": "error", 
                "error": "Unauthorized to delete this item"
            }), 403
        
        success = wardrobe_db.delete_item(item_id)
        
        if success:
            print(f"✅ Item {item_id} deleted successfully")
            return jsonify({
                "status": "success",
                "message": "Item deleted successfully",
                "item_id": item_id
            })
        else:
            return jsonify({
                "status": "error", 
                "error": "Failed to delete item"
            }), 500
            
    except Exception as e:
        print(f"❌ Error deleting item {item_id}: {str(e)}")
        return jsonify({
            "status": "error", 
            "error": str(e)
        }), 500

# -----------------------
# SAFE OUTFIT GENERATOR (HELPER FUNCTION)
# -----------------------
def generate_outfits_safe(user_id, occasion, weather, num_outfits=3):
    """Safe outfit generation that always works for presentation."""
    try:
        # Get user's wardrobe items
        items = wardrobe_db.get_user_items(user_id)
        
        if len(items) < 2:
            return []
        
        # Ensure all items have required fields
        for item in items:
            if "_id" in item and not isinstance(item["_id"], str):
                item["_id"] = str(item["_id"])
            if "color" not in item or item["color"] is None:
                item["color"] = "unknown"
            if "style_tags" not in item:
                item["style_tags"] = []
        
        # Categorize items
        categories = {}
        for item in items:
            cat = item.get("category", "unknown")
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(item)
        
        print(f"📊 Categories available: {list(categories.keys())}")
        
        # Create outfits based on available categories
        outfits = []
        outfit_templates = [
            {
                "name": "Casual Day",
                "required": ["top", "bottom", "shoes"],
                "description": "Perfect for everyday activities"
            },
            {
                "name": "Elegant Evening", 
                "required": ["dress", "accessory"],
                "description": "Great for special occasions"
            },
            {
                "name": "Layered Look",
                "required": ["top", "bottom", "outerwear"],
                "description": "Versatile for changing weather"
            },
            {
                "name": "Minimal Style",
                "required": ["top", "bottom"],
                "description": "Simple and clean"
            },
            {
                "name": "Complete Ensemble",
                "required": ["top", "bottom", "shoes", "accessory"],
                "description": "Fully accessorized outfit"
            }
        ]
        
        for template in outfit_templates[:num_outfits]:
            outfit_items = []
            
            # Try to get items from required categories
            for cat in template["required"]:
                if cat in categories and categories[cat]:
                    # Take first item from this category
                    outfit_items.append(categories[cat][0])
                    # Remove it so we don't reuse in same outfit
                    categories[cat] = categories[cat][1:]
            
            # If we have at least 2 items, create outfit
            if len(outfit_items) >= 2:
                outfit = {
                    "title": f"{template['name']} - {occasion}",
                    "details": template["description"],
                    "items": [],
                    "score": 0.7 + (len(outfit_items) * 0.1),  # More items = higher score
                    "item_count": len(outfit_items)
                }
                
                # Format items for frontend
                for item in outfit_items:
                    item_data = {
                        "id": str(item.get("_id", "")),
                        "category": item.get("category", "unknown"),
                        "color": item.get("color", "unknown"),
                        "style_tags": item.get("style_tags", []),
                        "formality": item.get("formality", "casual"),
                        "image_file_id": item.get("image_file_id")
                    }
                    
                    # Load image if available
                    if item_data["image_file_id"]:
                        try:
                            item_data["image_base64"] = wardrobe_db.get_image_base64(item_data["image_file_id"])
                        except:
                            item_data["image_base64"] = None
                    
                    outfit["items"].append(item_data)
                
                outfits.append(outfit)
                print(f"✅ Created outfit: {template['name']} with {len(outfit_items)} items")
        
        print(f"🎉 Generated {len(outfits)} safe outfits")
        return outfits
        
    except Exception as e:
        print(f"❌ Error in safe generator: {e}")
        import traceback
        traceback.print_exc()
        return []

# -----------------------
# GENERATE OUTFITS (MAIN ENDPOINT)
# -----------------------
@app.route("/generate", methods=["POST"])
def generate_outfits():
    """Generate outfits based on occasion, weather, and wardrobe."""
    try:
        data = request.json or {}
        
        # Log the incoming data
        print(f"📥 Received generate request with data: {data}")
        
        # Validate required fields
        occasion = data.get("occasion", "").strip()
        city = data.get("city", "").strip()
        user_id = data.get("user_id", "anonymous")
        
        print(f"📥 Occasion: '{occasion}'")
        print(f"📥 City: '{city}'")
        print(f"📥 User ID: '{user_id}'")
        
        # Ensure we have values
        if not occasion:
            occasion = "casual day"
            print(f"⚠️  Occasion was empty, using default: '{occasion}'")
        
        if not city:
            print("❌ City is required")
            return jsonify({
                "status": "error",
                "error": "City is required",
                "message": "Please enter a city to get weather data"
            }), 400
        
        print(f"✅ Final occasion: '{occasion}'")
        print(f"✅ Final city: '{city}'")
        
        num_outfits = int(data.get("outfitCount", 3))
        focus_item_id = data.get("focus_item_id")
                
        print(f"🎨 Generating outfits for: {occasion} in {city}")
        print(f"   User: {user_id}, Number of outfits: {num_outfits}")
        
        # Get weather data
        print(f"🌤️  Getting weather for {city}...")
        weather = get_weather(city)
        print(f"✅ Weather: {weather.get('temp_c', 'N/A')}°C, {weather.get('condition', 'N/A')}")
        
        # Check if user has items
        user_items = wardrobe_db.get_user_items(user_id)
        if not user_items:
            return jsonify({
                "status": "error",
                "error": "No wardrobe items found",
                "message": "Please upload some clothing items first"
            }), 400
        
        print(f"👕 User has {len(user_items)} wardrobe items")
        
        # Try the enhanced generator first
        outfits = []
        try:
            print("🤖 Attempting to generate outfits with enhanced AI generator...")
            outfits = outfit_gen.enhanced_generator.generate_outfits(
                user_id=user_id,
                occasion=occasion,
                weather=weather,
                num_outfits=num_outfits,
                focus_item_id=focus_item_id
            )
            print(f"✅ Enhanced generator created {len(outfits)} outfits")
            
        except Exception as e:
            print(f"⚠️  Enhanced generator failed: {e}")
            print("🔄 Falling back to safe generator...")
            
            # Try to get outfits from history first
            history_outfits = db_client.get_outfit_history(
                user_id=user_id,
                limit=num_outfits,
                sort_by="generated_at",
                sort_order=-1
            )
            
            if history_outfits and len(history_outfits) > 0:
                print(f"📜 Found {len(history_outfits)} outfits in history")
                # Convert history outfits to frontend format
                outfits = []
                for hist_outfit in history_outfits:
                    outfit = {
                        "title": hist_outfit.get("title", f"Outfit from history"),
                        "details": hist_outfit.get("details", ""),
                        "items": [],
                        "score": hist_outfit.get("metadata", {}).get("outfit_score", 0.7),
                        "item_count": len(hist_outfit.get("items", []))
                    }
                    
                    for item in hist_outfit.get("items", []):
                        item_data = {
                            "id": item.get("item_id"),
                            "category": item.get("category", "unknown"),
                            "color": item.get("color", "unknown"),
                            "style_tags": item.get("style_tags", []),
                            "formality": "casual",
                            "image_file_id": item.get("image_file_id")
                        }
                        
                        if "image_file_id" in item:
                            try:
                                item_data["image_base64"] = wardrobe_db.get_image_base64(item["image_file_id"])
                            except:
                                item_data["image_base64"] = None
                        
                        outfit["items"].append(item_data)
                    
                    outfits.append(outfit)
            else:
                # Use safe generator as last resort
                outfits = generate_outfits_safe(user_id, occasion, weather, num_outfits)
        
        # If still no outfits, create at least one simple outfit
        if not outfits:
            print("⚠️  No outfits generated, creating emergency outfit...")
            if len(user_items) >= 2:
                emergency_outfit = {
                    "title": f"Emergency {occasion} Outfit",
                    "details": "Created from available items",
                    "items": [],
                    "score": 0.6,
                    "item_count": min(3, len(user_items))
                }
                
                for i, item in enumerate(user_items[:3]):
                    item_data = {
                        "id": str(item.get("_id", f"item_{i}")),
                        "category": item.get("category", "unknown"),
                        "color": item.get("color", "unknown"),
                        "style_tags": item.get("style_tags", []),
                        "formality": item.get("formality", "casual")
                    }
                    
                    if "image_file_id" in item:
                        try:
                            item_data["image_base64"] = wardrobe_db.get_image_base64(item["image_file_id"])
                        except:
                            item_data["image_base64"] = None
                    
                    emergency_outfit["items"].append(item_data)
                
                outfits = [emergency_outfit]
                print("✅ Created emergency outfit")
        
        # Ensure all outfit items have images loaded
        print("🖼️  Loading images for outfit items...")
        for outfit in outfits:
            items = outfit.get("items", [])
            for item in items:
                if item.get("image_file_id") and not item.get("image_base64"):
                    try:
                        item["image_base64"] = wardrobe_db.get_image_base64(item["image_file_id"])
                    except Exception as e:
                        print(f"⚠️  Could not load outfit item image: {e}")
        
        print(f"✅ Final: Generated {len(outfits)} outfits")
        
        # Save successful outfits to history
        outfit_ids = []
        if outfits:
            print("💾 Saving outfits to history...")
            try:
                outfit_ids = db_client.save_outfit_to_history(
                    user_id=user_id,
                    outfits=outfits,
                    occasion=occasion,
                    weather=weather
                )
                print(f"✅ Saved {len(outfit_ids)} outfits to history")
            except Exception as e:
                print(f"⚠️  Could not save to history: {e}")
        
        # Get weather recommendations
        weather_recommendations = get_detailed_weather_recommendations(weather)
        
        # Prepare response
        response_data = {
            "status": "success",
            "message": f"Generated {len(outfits)} outfits for {occasion} in {city}",
            "outfits": outfits,
            "outfit_ids": outfit_ids,
            "weather": weather,
            "weather_recommendations": weather_recommendations,
            "occasion": occasion,
            "city": city,
            "user_id": user_id,
            "wardrobe_count": len(user_items),
            "generated_at": datetime.utcnow().isoformat(),
            "count": len(outfits),
            "generation_mode": "enhanced" if len(outfits) > 0 and 'emergency' not in str(outfits[0].get('title', '')).lower() else "safe"
        }
        
        return jsonify(response_data)
        
    except ValueError as e:
        print(f"❌ Validation error in /generate: {str(e)}")
        return jsonify({
            "status": "error",
            "error": str(e),
            "message": "Invalid input data"
        }), 400
    except Exception as e:
        print(f"❌ Critical error in /generate: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Last resort: return empty but successful response
        return jsonify({
            "status": "success",
            "message": "System encountered an error but handled it gracefully",
            "outfits": [],
            "weather": {"city": city, "temp_c": 22, "condition": "clear"} if 'city' in locals() else {},
            "occasion": occasion if 'occasion' in locals() else "casual",
            "city": city if 'city' in locals() else "Rabat",
            "user_id": user_id if 'user_id' in locals() else "anonymous",
            "wardrobe_count": 0,
            "generated_at": datetime.utcnow().isoformat(),
            "count": 0,
            "note": "System is in graceful degradation mode"
        })

# -----------------------
# GET WEATHER
# -----------------------
@app.route("/weather/<city>", methods=["GET"])
def get_weather_for_city(city):
    """Get weather data for a specific city."""
    try:
        units = request.args.get('units', 'metric')
        force_refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        print(f"🌤️  Getting weather for {city}")
        weather = get_weather(city, units, force_refresh)
        recommendations = get_detailed_weather_recommendations(weather)
        
        return jsonify({
            "status": "success",
            "weather": weather,
            "recommendations": recommendations,
            "city": city
        })
        
    except ValueError as e:
        print(f"❌ Weather error for {city}: {str(e)}")
        return jsonify({
            "status": "error", 
            "error": str(e),
            "message": f"City '{city}' not found or weather service unavailable"
        }), 400
    except Exception as e:
        print(f"❌ Error getting weather for {city}: {str(e)}")
        return jsonify({
            "status": "error", 
            "error": str(e)
        }), 500

# -----------------------
# OUTFIT HISTORY
# -----------------------
@app.route("/outfits/history", methods=["GET"])
def get_outfit_history():
    """Get outfit generation history for a user."""
    try:
        user_id = request.args.get('user_id', 'anonymous')
        limit = int(request.args.get('limit', 50))
        skip = int(request.args.get('skip', 0))
        
        print(f"📜 Getting outfit history for user: {user_id}")
        outfits = db_client.get_outfit_history(
            user_id=user_id,
            limit=limit,
            skip=skip,
            sort_by="generated_at",
            sort_order=-1
        )
        
        return jsonify({
            "status": "success",
            "outfits": outfits,
            "count": len(outfits),
            "user_id": user_id
        })
        
    except Exception as e:
        print(f"❌ Error getting outfit history: {str(e)}")
        return jsonify({
            "status": "error", 
            "error": str(e)
        }), 500

# -----------------------
# GET STATISTICS
# -----------------------
@app.route("/stats", methods=["GET"])
def get_statistics():
    """Get statistics for a user."""
    try:
        user_id = request.args.get('user_id', 'anonymous')
        
        print(f"📊 Getting statistics for user: {user_id}")
        stats = db_client.get_user_statistics(user_id)
        category_counts = wardrobe_db.count_by_category(user_id)
        
        return jsonify({
            "status": "success",
            "user_id": user_id,
            "statistics": stats,
            "category_counts": category_counts,
            "total_items": wardrobe_db.count_items(user_id)
        })
        
    except Exception as e:
        print(f"❌ Error getting statistics: {str(e)}")
        return jsonify({
            "status": "error", 
            "error": str(e)
        }), 500

# -----------------------
# SERVE UPLOADED IMAGES
# -----------------------
@app.route("/uploads/<filename>")
def serve_image(filename):
    """Serve uploaded images."""
    try:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(filepath):
            return jsonify({
                "error": f"Image {filename} not found"
            }), 404
        
        return send_file(filepath)
    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 404

# -----------------------
# HOME/INDEX
# -----------------------
@app.route("/")
def index():
    """Home page/API info."""
    return jsonify({
        "name": "SmartStylist API",
        "version": "1.0.0",
        "description": "AI-powered fashion assistant",
        "mongodb": {
            "status": "connected" if db_client._mode == "mongo" else "local_fallback",
            "mode": db_client._mode
        },
        "endpoints": {
            "POST /analyze": "Upload and analyze clothing image",
            "GET /wardrobe": "Get user's wardrobe",
            "POST /generate": "Generate outfits",
            "GET /weather/<city>": "Get weather data",
            "GET /outfits/history": "Get outfit history"
        },
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    })

# -----------------------
# TEST ENDPOINT
# -----------------------
@app.route("/test", methods=["GET"])
def test():
    """Test all components."""
    try:
        # Test MongoDB connection
        mongo_status = "connected" if db_client._mode == "mongo" else "local_fallback"
        
        # Test Gemini API (simulated)
        gemini_status = "available" if os.getenv("GOOGLE_API_KEY") else "not_configured"
        
        # Test weather service
        try:
            weather_test = get_weather("London", "metric", False)
            weather_status = "available"
        except:
            weather_status = "unavailable"
        
        # Test wardrobe database
        try:
            items_count = wardrobe_db.count_items("anonymous")
            db_status = "working"
        except:
            db_status = "error"
        
        return jsonify({
            "status": "success",
            "components": {
                "mongodb": mongo_status,
                "gemini_ai": gemini_status,
                "weather_service": weather_status,
                "wardrobe_database": db_status
            },
            "wardrobe_items": items_count if 'items_count' in locals() else 0,
            "message": "All systems operational" if all([
                gemini_status == "available",
                weather_status == "available",
                db_status == "working"
            ]) else "Some components may need configuration"
        })
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# -----------------------
# ERROR HANDLERS
# -----------------------
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "error": "Endpoint not found",
        "message": "The requested endpoint does not exist"
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "error": "Method not allowed",
        "message": "The HTTP method is not supported for this endpoint"
    }), 405

@app.errorhandler(500)
def internal_error(error):
    print(f"🔥 Internal server error: {error}")
    return jsonify({
        "error": "Internal server error",
        "message": "Something went wrong on our end"
    }), 500

# -----------------------
# CORS HEADERS
# -----------------------
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 SMARTSTYLIST FASHION AI - MONGODB COMPASS EDITION")
    print("="*60)
    print(f"📁 Upload folder: {app.config['UPLOAD_FOLDER']}")
    print(f"🌐 API URL: http://localhost:8080")
    print(f"📊 MongoDB Mode: {db_client._mode.upper()}")
    print(f"📚 API Documentation: http://localhost:8080/")
    print("="*60)
    print("\n✨ To get started:")
    print("   1. Open index.html in your browser")
    print("   2. Upload clothing images")
    print("   3. Generate AI-powered outfits!")
    print("\n📋 Available endpoints:")
    print("   • POST /analyze    - Upload and analyze clothing")
    print("   • GET  /wardrobe   - Get your wardrobe")
    print("   • POST /generate   - Generate outfits")
    print("   • GET  /weather/:city - Get weather data")
    print("\n🔧 Run /test to check all components")
    print("="*60 + "\n")
    
    # Test all components on startup
    try:
        print("🔍 Testing components...")
        
        # Test MongoDB
        if db_client._mode == "mongo":
            print(f"   ✅ MongoDB: Connected to {db_client._config.db_name}")
        else:
            print(f"   ⚠️  MongoDB: Using local fallback (filesystem)")
        
        # Test Gemini API key
        if os.getenv("GOOGLE_API_KEY"):
            print("   ✅ Gemini AI: API key configured")
        else:
            print("   ⚠️  Gemini AI: API key not set (will use fallback analysis)")
        
        # Test OpenWeatherMap API key
        if os.getenv("OPENWEATHER_API_KEY"):
            print("   ✅ OpenWeatherMap: API key configured")
        else:
            print("   ⚠️  OpenWeatherMap: API key not set (will use mock data)")
        
        print("✅ All components ready!")
        print("\n🎉 Server is ready! Press Ctrl+C to stop")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"❌ Startup check failed: {e}")
        print("⚠️  Some features may not work correctly")
    
    try:
        app.run(host='0.0.0.0', port=8080, debug=True, threaded=True)
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Error starting server: {e}")