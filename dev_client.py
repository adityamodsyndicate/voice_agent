#!/usr/bin/env python3
"""
dev_client.py - Local development client for testing without Twilio.

Connects to the server's /twilio WebSocket endpoint and pretends to be Twilio:
  - Captures audio from your microphone
  - Resamples to 8kHz mono, encodes to mulaw
  - Wraps in Twilio-format JSON messages and sends over WebSocket
  - Receives agent audio, decodes, plays through your speakers
"""
import argparse
import asyncio
import audioop
import base64
import json
import sys
import time
import uuid

# Check dependencies
try:
    import numpy as np
except ImportError:
    print("ERROR: numpy is required for dev_client.py")
    print("Install it with: pip install numpy")
    sys.exit(1)

try:
    import sounddevice as sd
except ImportError:
    print("ERROR: sounddevice is required for dev_client.py")
    print("Install it with: pip install sounddevice")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("ERROR: websockets is required for dev_client.py")
    print("Install it with: pip install websockets")
    sys.exit(1)


# Audio constants
TWILIO_SAMPLE_RATE = 8000   # Twilio telephony uses 8kHz
MIC_SAMPLE_RATE = 16000     # Capture at 16kHz for better quality before downsampling
CHANNELS = 1
CHUNK_DURATION_MS = 20      # Send audio every 20ms
MIC_CHUNK_SIZE = int(MIC_SAMPLE_RATE * CHUNK_DURATION_MS / 1000)


def pcm16_to_mulaw(pcm_data: bytes) -> bytes:
    """Convert 16-bit signed PCM to mulaw encoding."""
    return audioop.lin2ulaw(pcm_data, 2)


def mulaw_to_pcm16(mulaw_data: bytes) -> bytes:
    """Convert mulaw encoding to 16-bit signed PCM."""
    return audioop.ulaw2lin(mulaw_data, 2)


def resample(data: bytes, from_rate: int, to_rate: int) -> bytes:
    """Resample PCM audio."""
    if from_rate == to_rate:
        return data
    return audioop.ratecv(data, 2, CHANNELS, from_rate, to_rate, None)[0]


class TerminalUI:
    """Simple terminal interface for displaying call logs and status."""

    def __init__(self):
        self.status = "Connecting..."
        self.transcript_lines = []
        self.function_calls = []
        self._last_render = 0

    def set_status(self, status: str):
        self.status = status
        self._render()

    def add_transcript(self, role: str, content: str):
        prefix = "You" if role == "user" else "Agent"
        self.transcript_lines.append(f"  {prefix}: {content}")
        if len(self.transcript_lines) > 20:
            self.transcript_lines = self.transcript_lines[-20:]
        self._render()

    def add_function_call(self, name: str, args: dict, result: dict = None):
        entry = f"  > {name}({json.dumps(args)})"
        if result:
            result_str = json.dumps(result)
            if len(result_str) > 100:
                result_str = result_str[:100] + "..."
            entry += f"\n    → {result_str}"
        self.function_calls.append(entry)
        if len(self.function_calls) > 10:
            self.function_calls = self.function_calls[-10:]
        self._render()

    def _render(self):
        now = time.time()
        if now - self._last_render < 0.1:
            return
        self._last_render = now

        lines = [
            "\033[2J\033[H",  # Clear screen
            "=" * 60,
            "  Optimist Computers Voice Agent - Dev Client",
            f"  Status: {self.status}",
            "=" * 60,
            "",
            "─── Transcript ─────────────────────────────────────"
        ]
        if self.transcript_lines:
            lines.extend(self.transcript_lines[-15:])
        else:
            lines.append("  (waiting for conversation...)")

        if self.function_calls:
            lines.append("")
            lines.append("─── Tool/Function Calls ────────────────────────────")
            lines.extend(self.function_calls[-5:])

        lines.extend([
            "",
            "─── Controls ───────────────────────────────────────",
            "  Ctrl+C to hang up/disconnect",
            ""
        ])

        print("\n".join(lines), end="", flush=True)


async def run_client(ws_url: str):
    """Bridge microphone, speakers, and WebSocket connection."""
    ui = TerminalUI()
    ui.set_status("Connecting...")

    call_sid = f"DEV-{uuid.uuid4().hex[:12]}"
    stream_sid = f"STR-{uuid.uuid4().hex[:12]}"

    try:
        async with websockets.connect(ws_url) as ws:
            ui.set_status("Connected. Initialising session...")

            # Send mock Twilio connection and start events
            await ws.send(json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}))
            await ws.send(json.dumps({
                "event": "start",
                "sequenceNumber": "1",
                "start": {
                    "accountSid": "DEV-ACCOUNT",
                    "streamSid": stream_sid,
                    "callSid": call_sid,
                    "tracks": ["inbound"],
                    "mediaFormat": {
                        "encoding": "audio/x-mulaw",
                        "sampleRate": 8000,
                        "channels": 1,
                    },
                },
                "streamSid": stream_sid,
            }))

            ui.set_status("Active. Talk into your microphone...")

            await asyncio.gather(
                _send_mic_audio(ws, stream_sid),
                _receive_agent_audio(ws, ui),
            )

    except websockets.exceptions.ConnectionClosed:
        ui.set_status("Disconnected (server closed connection).")
    except ConnectionRefusedError:
        print("\nERROR: Connection refused. Is the server running (python main.py)?")
        sys.exit(1)
    except KeyboardInterrupt:
        ui.set_status("Disconnected (hang up).")


async def _send_mic_audio(ws, stream_sid: str):
    """Capture local microphone input and stream to WebSocket."""
    loop = asyncio.get_event_loop()
    audio_queue = asyncio.Queue()
    seq = 2

    def audio_callback(indata, frames, time_info, status):
        pcm_int16 = (indata[:, 0] * 32767).astype("int16").tobytes()
        loop.call_soon_threadsafe(audio_queue.put_nowait, pcm_int16)

    stream = sd.InputStream(
        samplerate=MIC_SAMPLE_RATE,
        channels=CHANNELS,
        blocksize=MIC_CHUNK_SIZE,
        dtype="float32",
        callback=audio_callback,
    )

    with stream:
        while True:
            pcm_16k = await audio_queue.get()
            pcm_8k = resample(pcm_16k, MIC_SAMPLE_RATE, TWILIO_SAMPLE_RATE)
            mulaw = pcm16_to_mulaw(pcm_8k)
            payload = base64.b64encode(mulaw).decode("utf-8")

            message = {
                "event": "media",
                "sequenceNumber": str(seq),
                "media": {
                    "track": "inbound",
                    "chunk": str(seq),
                    "timestamp": str(seq * CHUNK_DURATION_MS),
                    "payload": payload,
                },
                "streamSid": stream_sid,
            }
            seq += 1
            await ws.send(json.dumps(message))


async def _receive_agent_audio(ws, ui: TerminalUI):
    """Receive audio from websocket and play it through speakers."""
    output_stream = sd.OutputStream(
        samplerate=TWILIO_SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=1024,
    )
    output_stream.start()

    try:
        async for message in ws:
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                continue

            event = data.get("event")
            if event == "media":
                payload = data.get("media", {}).get("payload", "")
                if payload:
                    mulaw_bytes = base64.b64decode(payload)
                    pcm_bytes = mulaw_to_pcm16(mulaw_bytes)
                    pcm_array = np.frombuffer(pcm_bytes, dtype="int16")
                    output_stream.write(pcm_array)

            elif event == "clear":
                # User interrupted - clear audio buffer immediately
                output_stream.abort()
                output_stream.start()

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        output_stream.stop()
        output_stream.close()


def main():
    parser = argparse.ArgumentParser(description="Local dev client for testing the voice agent")
    parser.add_argument("--url", default="ws://localhost:8080/twilio", help="Server WebSocket URL")
    args = parser.parse_args()

    print("Starting client...")
    print(f"Connecting to: {args.url}")
    print("Press Ctrl+C to terminate.\n")

    try:
        asyncio.run(run_client(args.url))
    except KeyboardInterrupt:
        print("\nDisconnected. Goodbye!")


if __name__ == "__main__":
    main()
