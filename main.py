"""
Optimist Computers Voice Agent - Server Entry Point

Starts a Starlette web server to handle:
  - POST /incoming-call  -> Twilio webhook (returns TwiML)
  - WS   /twilio         -> Twilio audio stream (or dev_client.py)
"""
import logging
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, WebSocketRoute
from starlette.responses import PlainTextResponse

from config import SERVER_HOST, SERVER_PORT, SERVER_EXTERNAL_URL, DEEPGRAM_API_KEY
from telephony.routes import incoming_call, twilio_websocket

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def dashboard(request):
    return PlainTextResponse(
        "Optimist Computers Voice Agent is running.\n"
        "Configure your Twilio number or use `python dev_client.py` to test locally."
    )

app = Starlette(
    routes=[
        Route("/incoming-call/{token:path}", incoming_call, methods=["POST"]),
        Route("/incoming-call", incoming_call, methods=["POST"]),
        WebSocketRoute("/twilio/{token:path}", twilio_websocket),
        WebSocketRoute("/twilio", twilio_websocket),
        Route("/", dashboard),
    ],
)

if __name__ == "__main__":
    logger.info(f"Deepgram API key: {'configured' if DEEPGRAM_API_KEY else 'MISSING'}")
    if SERVER_EXTERNAL_URL:
        logger.info(f"External URL: {SERVER_EXTERNAL_URL}")
        logger.info(f"Twilio webhook: {SERVER_EXTERNAL_URL}/incoming-call")
    else:
        logger.info("Running in local development mode (no SERVER_EXTERNAL_URL set)")
        logger.info("Use dev_client.py to test locally without Twilio")

    uvicorn.run(
        app,
        host=SERVER_HOST,
        port=int(SERVER_PORT),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
