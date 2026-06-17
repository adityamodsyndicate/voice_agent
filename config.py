import os
from dotenv import load_dotenv

load_dotenv()

# Required
DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")

# Server Configuration
SERVER_HOST = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.getenv("SERVER_PORT", "8080"))
SERVER_EXTERNAL_URL = os.getenv("SERVER_EXTERNAL_URL")

# Voice Agent Configuration
VOICE_MODEL = os.getenv("VOICE_MODEL", "aura-2-asteria-en")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

# Twilio Configuration (optional)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Security Configuration (optional)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# Validation
if not DEEPGRAM_API_KEY:
    raise ValueError(
        "Missing required environment variable: DEEPGRAM_API_KEY\n"
        "Please set it in your .env file or environment."
    )
