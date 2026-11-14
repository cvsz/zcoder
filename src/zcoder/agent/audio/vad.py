"""
Voice Activity Detection (VAD) for ZCoder.

Provides VAD functionality using Silero VAD or other backends.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass

import numpy as np


@dataclass
class VADSegment:
    """A segment of speech detected by VAD."""

    start: float  # Start time in seconds
    end: float  # End time in seconds
    confidence: float  # Confidence score 0-1


@dataclass
class VADResult:
    """Result of VAD processing."""

    segments: list[VADSegment]
    has_speech: bool
    total_speech_duration: float


class VAD(abc.ABC):
    """Abstract base class for Voice Activity Detection."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """VAD name."""
        pass

    @abc.abstractmethod
    def process(self, audio_data: np.ndarray, sample_rate: int) -> VADResult:
        """Process audio data and detect voice activity.

        Args:
            audio_data: Audio data as numpy array
            sample_rate: Sample rate in Hz

        Returns:
            VADResult with detected speech segments
        """
        pass

    @abc.abstractmethod
    def process_stream(self, audio_chunk: np.ndarray, sample_rate: int) -> list[tuple[float, float]]:
        """Process streaming audio chunk and return speech segments.

        Args:
            audio_chunk: Audio chunk as numpy array
            sample_rate: Sample rate in Hz

        Returns:
            List of (start, end) tuples for speech segments in this chunk
        """
        pass

    @abc.abstractmethod
    def reset(self) -> None:
        """Reset VAD state for new stream."""
        pass


class SileroVAD(VAD):
    """Silero VAD implementation using ONNX or torch."""

    def __init__(
        self, threshold: float = 0.5, min_speech_duration_ms: int = 250, min_silence_duration_ms: int = 100
    ):
        self.threshold = threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self._model = None
        self._onnx_session = None
        self._state = None
        self._sample_rate = 16000
        self._backend = None

    @property
    def name(self) -> str:
        return "silero-vad"

    def _load_model(self):
        """Lazy load the Silero VAD model."""
        if self._model is not None:
            return

        try:
            import torch

            # Load Silero VAD from torch hub
            self._model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                trust_repo=True,
            )
            self._get_speech_timestamps = utils[0]
            self._backend = "torch"
        except ImportError:
            try:
                import os

                import onnxruntime as ort

                # Try to load ONNX model
                import requests

                model_path = os.path.join(os.path.dirname(__file__), "silero_vad.onnx")
                if not os.path.exists(model_path):
                    # Download model if not present
                    url = "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx"
                    import requests

                    response = requests.get(url, timeout=30)
                    with open(model_path, "wb") as f:
                        f.write(response.content)

                self._onnx_session = ort.InferenceSession(model_path)
                self._backend = "onnx"
            except ImportError as e:
                raise RuntimeError(
                    "Neither torch nor onnxruntime available. "
                    "Install with: pip install torch or pip install onnxruntime"
                ) from e

    def process(self, audio_data: np.ndarray, sample_rate: int = 16000) -> VADResult:
        self._load_model()

        # Resample if needed
        if sample_rate != 16000:
            import librosa

            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)
            sample_rate = 16000

        # Convert to float32 if needed
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32) / 32768.0

        if self._backend == "torch":
            import torch

            wav = torch.from_numpy(audio_data).float()
            speech_timestamps = self._get_speech_timestamps(wav, self._model, sampling_rate=16000)
        else:
            # ONNX backend
            # Simplified - would need proper ONNX inference
            speech_timestamps = []

        segments = []
        for ts in speech_timestamps:
            segments.append(
                VADSegment(
                    start=ts["start"] / 16000.0,
                    end=ts["end"] / 16000.0,
                    confidence=0.9,  # Silero doesn't provide per-segment confidence
                )
            )

        has_speech = len(segments) > 0
        total_duration = sum(s.end - s.start for s in segments)

        return VADResult(
            segments=segments,
            has_speech=has_speech,
            total_speech_duration=total_duration,
        )

    def process_stream(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> list[tuple[float, float]]:
        """Process streaming audio chunk."""
        result = self.process(audio_chunk, sample_rate)
        return [(seg.start, seg.end) for seg in result.segments]

    def reset(self) -> None:
        """Reset VAD state."""
        self._state = None


class WebRTCVAD(VAD):
    """WebRTC VAD implementation (alternative)."""

    def __init__(self, aggressiveness: int = 3):
        self.aggressiveness = aggressiveness
        self._vad = None

    @property
    def name(self) -> str:
        return "webrtc-vad"

    def _load_vad(self):
        if self._vad is None:
            try:
                import webrtcvad

                self._vad = webrtcvad.Vad(self.aggressiveness)
            except ImportError as e:
                raise RuntimeError("webrtcvad not available. Install with: pip install webrtcvad") from e

    def process(self, audio_data: np.ndarray, sample_rate: int = 16000) -> VADResult:
        self._load_vad()
        if self._vad is None:
            raise RuntimeError("WebRTC VAD failed to load")

        # WebRTC VAD requires 16kHz, 16-bit PCM, 10/20/30ms frames
        if sample_rate != 16000:
            import librosa

            audio_data = librosa.resample(audio_data, orig_sr=sample_rate, target_sr=16000)
            sample_rate = 16000

        # Convert to int16
        if audio_data.dtype != np.int16:
            audio_data = (audio_data * 32767).astype(np.int16)

        frame_duration_ms = 30
        frame_size = int(16000 * frame_duration_ms / 1000)

        segments = []
        in_speech = False
        segment_start = 0.0

        for i in range(0, len(audio_data) - frame_size, frame_size):
            frame = audio_data[i : i + frame_size]
            if len(frame) < frame_size:
                break

            is_speech = self._vad.is_speech(frame.tobytes(), 16000)

            if is_speech and not in_speech:
                in_speech = True
                segment_start = i / 16000.0
            elif not is_speech and in_speech:
                in_speech = False
                segment_end = (i + frame_size) / 16000.0
                segments.append(
                    VADSegment(
                        start=segment_start,
                        end=segment_end,
                        confidence=0.8,
                    )
                )

        # Handle case where speech continues to end
        if in_speech:
            segments.append(
                VADSegment(
                    start=segment_start,
                    end=len(audio_data) / 16000.0,
                    confidence=0.8,
                )
            )

        has_speech = len(segments) > 0
        total_duration = sum(s.end - s.start for s in segments)

        return VADResult(
            segments=segments,
            has_speech=has_speech,
            total_speech_duration=total_duration,
        )

    def process_stream(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> list[tuple[float, float]]:
        result = self.process(audio_chunk, sample_rate)
        return [(seg.start, seg.end) for seg in result.segments]

    def reset(self) -> None:
        pass


def create_vad(vad_type: str, **kwargs) -> VAD:
    """Factory function to create VAD instance.

    Args:
        vad_type: "silero" or "webrtc"
        **kwargs: VAD-specific arguments

    Returns:
        VAD instance
    """
    if vad_type == "silero":
        return SileroVAD(**kwargs)
    elif vad_type == "webrtc":
        return WebRTCVAD(**kwargs)
    else:
        raise ValueError(f"Unknown VAD type: {vad_type}")
