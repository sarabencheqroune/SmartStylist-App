#!/usr/bin/env python3
"""
SmartStylist - Main entry point
Run with: python run.py
"""

import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

print("🚀 Starting SmartStylist Fashion AI...")
print("="*60)

# Check for required environment variables
required_vars = ['GOOGLE_API_KEY']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print("⚠️  Missing required environment variables:")
    for var in missing_vars:
        print(f"   - {var}")
    print("\nSome features will use fallback mode.")
    print("For full functionality, create a .env file with these variables.")

# Check if MongoDB is running
try:
    from pymongo import MongoClient
    client = MongoClient(os.getenv("MONGODB_URI", "mongodb://localhost:27017"), 
                         serverSelectionTimeoutMS=2000)
    client.admin.command('ping')
    print("✅ MongoDB connection successful")
    print(f"   Database: {os.getenv('MONGODB_DB', 'smartstylist')}")
except Exception as e:
    print("⚠️  MongoDB not reachable, using local fallback mode")
    print(f"   Error: {e}")
    print("\nNote: Some features may be limited in fallback mode.")
    print("To enable full functionality, make sure MongoDB is running.")
    print("You can install MongoDB from: https://www.mongodb.com/try/download/community")

print("="*60)

# Import and run the Flask app
try:
    from api import app
    
    if __name__ == '__main__':
        print("\n✨ SmartStylist is ready!")
        print(f"📁 Upload folder: {app.config['UPLOAD_FOLDER']}")
        print(f"🌐 API URL: http://localhost:8080")
        print(f"📚 API Docs: http://localhost:8080/")
        print(f"🔧 Debug mode: ON")
        print("="*60)
        print("\nTo get started:")
        print("1. Open index.html in your browser")
        print("2. Upload clothing images")
        print("3. Generate AI-powered outfits!")
        print("\nPress Ctrl+C to stop the server")
        print("="*60 + "\n")
        
        try:
            app.run(host='0.0.0.0', port=8080, debug=True, threaded=True)
        except KeyboardInterrupt:
            print("\n👋 Server stopped by user")
        except Exception as e:
            print(f"\n❌ Error starting server: {e}")
            print("Make sure port 8080 is not in use by another application.")
            
except ImportError as e:
    print(f"\n❌ Import error: {e}")
    print("Make sure all required packages are installed:")
    print("   pip install -r requirements.txt")
    sys.exit(1)
except Exception as e:
    print(f"\n❌ Unexpected error: {e}")
    sys.exit(1)