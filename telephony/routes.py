import json
import logging

from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.websockets import WebSocket

from config import SERVER_EXTERNAL_URL, TWILIO_AUTH_TOKEN, WEBHOOK_SECRET
from voice_agent.session import VoiceAgentSession

logger = logging.getLogger(__name__)

if TWILIO_AUTH_TOKEN:
    from twilio.request_validator import RequestValidator
    _twilio_validator = RequestValidator(TWILIO_AUTH_TOKEN)
else:
    _twilio_validator = None


def _check_webhook_secret(path_params: dict) -> bool:
    """Validate incoming request secret if set."""
    if not WEBHOOK_SECRET:
        return True
    token = path_params.get("token", "")
    return token == WEBHOOK_SECRET


active_sessions: dict[str, VoiceAgentSession] = {}


async def incoming_call(request: Request) -> Response:
    """Twilio webhook endpoint for incoming calls. Returns TwiML.

    TwiML connects Twilio audio stream to our WebSocket `/twilio` endpoint.
    """
    if not _check_webhook_secret(request.path_params):
        return Response(status_code=404)

    # Validate Twilio signature
    if _twilio_validator:
        url = str(request.url)
        form_data = await request.form()
        params = dict(form_data)
        signature = request.headers.get("X-Twilio-Signature", "")
        if not _twilio_validator.validate(url, params, signature):
            logger.warning("[TELEPHONY] Invalid Twilio Signature - Request Rejected")
            return Response(status_code=403)

    if SERVER_EXTERNAL_URL:
        host = SERVER_EXTERNAL_URL.replace("https://", "").replace("http://", "").rstrip("/")
    else:
        host = request.headers.get("host", "localhost:8080")

    ws_path = "/twilio"
    if WEBHOOK_SECRET:
        ws_path = f"/twilio/{WEBHOOK_SECRET}"

    twiml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="wss://{host}{ws_path}" />
    </Connect>
</Response>"""

    logger.info(f"[TELEPHONY] Call received. Streaming TwiML directed to wss://{host}{ws_path}")
    return Response(content=twiml, media_type="application/xml")


async def twilio_websocket(websocket: WebSocket):
    """WebSocket endpoint to bridge Twilio media stream."""
    if not _check_webhook_secret(websocket.path_params):
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logger.info("[TELEPHONY] WebSocket connection accepted.")

    call_sid = None
    stream_sid = None
    session = None

    try:
        # Await Twilio's start event to obtain call details
        while True:
            message = await websocket.receive_text()
            data = json.loads(message)

            if data.get("event") == "start":
                call_sid = data["start"].get("callSid", "unknown")
                stream_sid = data["start"].get("streamSid", "unknown")
                logger.info(f"[TELEPHONY] Call session started. Call SID: {call_sid}")
                break
            elif data.get("event") == "connected":
                continue

        # Start agent session
        session = VoiceAgentSession(websocket, call_sid, stream_sid)
        active_sessions[call_sid] = session

        await session.start()
        await session.run()

    except Exception as e:
        logger.error(f"[TELEPHONY] Error occurred during call {call_sid}: {e}")
    finally:
        if session:
            await session.cleanup()
        if call_sid and call_sid in active_sessions:
            del active_sessions[call_sid]
        logger.info(f"[TELEPHONY] Call {call_sid} disconnected.")
