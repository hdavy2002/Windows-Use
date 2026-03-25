"""
humphi/audio.py — Mic input + speaker output for Gemini Live

Mic: PCM 16-bit 16kHz mono → base64 → Gemini
Speaker: PCM 24kHz from Gemini → playback
"""

import base64
import threading
import queue
import numpy as np

try:
    import sounddevice as sd
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

MIC_RATE = 16000      # Gemini expects 16kHz
MIC_CHANNELS = 1
MIC_CHUNK = 4096      # samples per chunk
SPEAKER_RATE = 24000  # Gemini outputs 24kHz


class MicCapture:
    """Captures microphone audio as PCM 16-bit 16kHz base64 chunks."""

    def __init__(self, on_audio_chunk=None):
        self.on_audio_chunk = on_audio_chunk  # callback(b64_str)
        self._stream = None
        self._running = False

    def start(self):
        if not HAS_AUDIO:
            print("WARNING: sounddevice not installed, mic disabled")
            return
        self._running = True
        self._stream = sd.InputStream(
            samplerate=MIC_RATE, channels=MIC_CHANNELS,
            dtype='int16', blocksize=MIC_CHUNK,
            callback=self._callback
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        if not self._running or self.on_audio_chunk is None:
            return
        pcm_bytes = indata.tobytes()
        b64 = base64.b64encode(pcm_bytes).decode("utf-8")
        self.on_audio_chunk(b64)

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None


class SpeakerOutput:
    """Plays PCM 24kHz audio from Gemini."""

    def __init__(self):
        self._queue = queue.Queue()
        self._stream = None
        self._running = False
        self._thread = None

    def start(self):
        if not HAS_AUDIO:
            print("WARNING: sounddevice not installed, speaker disabled")
            return
        self._running = True
        self._stream = sd.OutputStream(
            samplerate=SPEAKER_RATE, channels=1,
            dtype='int16', blocksize=2048,
            callback=self._callback
        )
        self._stream.start()

    def _callback(self, outdata, frames, time_info, status):
        try:
            data = self._queue.get_nowait()
            # Pad or trim to match expected frames
            if len(data) < len(outdata):
                outdata[:len(data)] = data
                outdata[len(data):] = b'\x00' * (len(outdata) - len(data))
            else:
                outdata[:] = data[:len(outdata)]
        except queue.Empty:
            outdata[:] = b'\x00' * len(outdata)

    def play(self, pcm_bytes: bytes):
        """Queue PCM bytes for playback."""
        # Convert bytes to int16 numpy array, chunk it
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        chunk_size = 2048
        for i in range(0, len(arr), chunk_size):
            chunk = arr[i:i+chunk_size]
            self._queue.put(chunk.reshape(-1, 1))

    def stop(self):
        self._running = False
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
