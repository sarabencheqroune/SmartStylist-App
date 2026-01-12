import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
    # Weather
    # Primary: OpenWeatherMap
    OPENWEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY')
    # Backward compatible alias (some users already set WEATHER_API_KEY)
    WEATHER_API_KEY = os.getenv('WEATHER_API_KEY')
    # Secondary: WeatherAPI.com
    WEATHERAPI_KEY = os.getenv('WEATHERAPI_KEY')
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "smartstylist")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "wardrobe_items")

