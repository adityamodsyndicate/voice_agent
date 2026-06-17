import asyncio
import base64
import json
import logging
from starlette.websockets import WebSocket

from deepgram import AsyncDeepgramClient
from deepgram.core.pydantic_utilities import parse_obj_as
from deepgram.agent.v1 import (
    AgentV1SettingsApplied,
    AgentV1FunctionCallRequest,
    AgentV1ConversationText,
    AgentV1UserStartedSpeaking,
    AgentV1AgentAudioDone,
    AgentV1Error,
    AgentV1Warning,
    AgentV1SendFunctionCallResponse,
)
from deepgram.agent.v1.socket_client import V1SocketClientResponse

from voice_agent.agent_config import get_agent_config

logger = logging.getLogger(__name__)


class VoiceAgentSession:
    """Manages one Deepgram Voice Agent session for the duration of a call."""

    def __init__(self, twilio_ws: WebSocket, call_sid: str, stream_sid: str):
        self.twilio_ws = twilio_ws
        self.call_sid = call_sid
        self.stream_sid = stream_sid

        # Deepgram client and connection state
        self._client = None
        self._connection = None
        self._context_manager = None

        # Synchronisation
        self._settings_applied = asyncio.Event()
        self._cleanup_done = False

        # Tasks
        self._listen_task = None
        self._audio_task = None

    async def start(self):
        """Establish connection with Deepgram, send config, and prepare loops."""
        logger.info(f"[SESSION:{self.call_sid}] Connecting to Deepgram Voice Agent API...")
        
        self._client = AsyncDeepgramClient()
        self._context_manager = self._client.agent.v1.connect()
        self._connection = await self._context_manager.__aenter__()

        # Start listening for messages from Deepgram
        self._listen_task = asyncio.create_task(self._listen_loop())

        # Send configuration settings
        config = get_agent_config()
        await self._connection.send_settings(config)

        # Wait for settings confirmation
        try:
            await asyncio.wait_for(self._settings_applied.wait(), timeout=5.0)
            logger.info(f"[SESSION:{self.call_sid}] Deepgram settings applied successfully.")
        except asyncio.TimeoutError:
            logger.error(f"[SESSION:{self.call_sid}] Timeout waiting for settings approval.")
            raise

    async def run(self):
        """Run the audio bridging loop between Twilio and Deepgram."""
        self._audio_task = asyncio.create_task(self._forward_twilio_audio())

        # Wait for either loop to complete (signalling call end)
        done, pending = await asyncio.wait(
            [self._audio_task, self._listen_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # Cancel remaining tasks
        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        logger.info(f"[SESSION:{self.call_sid}] Voice agent session complete.")

    async def cleanup(self):
        """Release resources and close socket connections."""
        if self._cleanup_done:
            return
        self._cleanup_done = True

        logger.info(f"[SESSION:{self.call_sid}] Cleaning up resources...")

        # Cancel tasks
        for task in [self._audio_task, self._listen_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # Close Deepgram connection
        if self._context_manager:
            try:
                await self._context_manager.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"[SESSION:{self.call_sid}] Error closing Deepgram connection: {e}")

        self._connection = None
        self._client = None
        logger.info(f"[SESSION:{self.call_sid}] Cleanup complete.")

    async def _listen_loop(self):
        """Listen for messages from Deepgram, ignoring unparseable event types."""
        try:
            async for raw_message in self._connection._websocket:
                try:
                    if isinstance(raw_message, bytes):
                        parsed = raw_message
                    else:
                        json_data = json.loads(raw_message)
                        parsed = parse_obj_as(V1SocketClientResponse, json_data)
                except Exception:
                    msg_type = json_data.get("type", "unknown") if isinstance(raw_message, str) else "binary"
                    logger.debug(f"[SESSION:{self.call_sid}] Skipping unparsed Deepgram message: {msg_type}")
                    continue

                if isinstance(parsed, AgentV1SettingsApplied):
                    self._settings_applied.set()
                else:
                    await self._handle_message(parsed)
        except Exception as e:
            logger.info(f"[SESSION:{self.call_sid}] Deepgram listener closed: {e}")
        finally:
            logger.info(f"[SESSION:{self.call_sid}] Deepgram WebSocket disconnected.")

    async def _handle_message(self, message):
        """Bridge Deepgram response events to Twilio."""
        try:
            # Binary audio payload
            if isinstance(message, bytes):
                audio_b64 = base64.b64encode(message).decode("utf-8")
                await self.twilio_ws.send_json({
                    "event": "media",
                    "streamSid": self.stream_sid,
                    "media": {"payload": audio_b64},
                })

            # Tool/Function call request
            elif isinstance(message, AgentV1FunctionCallRequest):
                await self._handle_function_call(message)

            # Transcript text logging
            elif isinstance(message, AgentV1ConversationText):
                logger.info(f"[SESSION:{self.call_sid}] {message.role.upper()}: {message.content}")

            # Interruption handling: user started speaking
            elif isinstance(message, AgentV1UserStartedSpeaking):
                logger.info(f"[SESSION:{self.call_sid}] Interruption: User started speaking")
                await self.twilio_ws.send_json({
                    "event": "clear",
                    "streamSid": self.stream_sid,
                })

            elif isinstance(message, AgentV1AgentAudioDone):
                logger.debug(f"[SESSION:{self.call_sid}] Agent audio done.")

            elif isinstance(message, AgentV1Error):
                logger.error(f"[SESSION:{self.call_sid}] Deepgram Agent error: {message.description}")
            elif isinstance(message, AgentV1Warning):
                logger.warning(f"[SESSION:{self.call_sid}] Deepgram Agent warning: {message.description}")

        except Exception as e:
            logger.error(f"[SESSION:{self.call_sid}] Error handling message from Deepgram: {e}")

    async def _handle_function_call(self, event: AgentV1FunctionCallRequest):
        """Execute and dispatch a tool call from the agent."""
        if not event.functions:
            return

        func = event.functions[0]
        function_name = func.name
        call_id = func.id
        args = json.loads(func.arguments) if func.arguments else {}

        logger.info(f"[SESSION:{self.call_sid}] Executing function: {function_name} with arguments: {args}")

        try:
            from voice_agent.function_handlers import dispatch_function
            result = await dispatch_function(function_name, args)
            logger.info(f"[SESSION:{self.call_sid}] Function result: {function_name} -> {result}")
        except Exception as e:
            logger.error(f"[SESSION:{self.call_sid}] Function dispatch error: {function_name} -> {e}")
            result = {"error": str(e)}

        # Respond to Deepgram
        response = AgentV1SendFunctionCallResponse(
            type="FunctionCallResponse",
            name=function_name,
            content=json.dumps(result),
            id=call_id,
        )
        await self._connection.send_function_call_response(response)

        # If agent wanted to hang up
        if function_name == "end_call":
            asyncio.create_task(self._end_call_after_delay())

    async def _end_call_after_delay(self):
        """Wait for TTS goodbye audio to finish playing, then terminate call."""
        await asyncio.sleep(3)
        logger.info(f"[SESSION:{self.call_sid}] Hanging up...")

        # Terminate Twilio call via REST API if credentials exist
        from config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            try:
                from twilio.rest import Client
                client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                await asyncio.to_thread(
                    client.calls(self.call_sid).update,
                    status="completed",
                )
                logger.info(f"[SESSION:{self.call_sid}] Twilio call marked completed.")
            except Exception as e:
                logger.error(f"[SESSION:{self.call_sid}] Failed to update Twilio call: {e}")

        # Close websocket
        try:
            await self.twilio_ws.close()
        except Exception:
            pass

    async def _forward_twilio_audio(self):
        """Forward Twilio audio stream to Deepgram."""
        try:
            while True:
                message = await self.twilio_ws.receive_text()
                data = json.loads(message)

                if data.get("event") == "media":
                    payload = data["media"]["payload"]
                    audio_bytes = base64.b64decode(payload)
                    if self._connection:
                        await self._connection.send_media(audio_bytes)

                elif data.get("event") == "stop":
                    logger.info(f"[SESSION:{self.call_sid}] Twilio sent stop event.")
                    break
        except Exception as e:
            logger.info(f"[SESSION:{self.call_sid}] Twilio WebSocket disconnected: {e}")
