"""
Audio input providers for ZCoder.

Supports microphone input and file-based audio input.
"""

from __future__ import annotations

import abc
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import numpy as np


@dataclass
class AudioConfig:
    """Configuration for audio input."""

    sample_rate: int = 16000
    channels: int = 1
    dtype: str = "int16"
    chunk_size: int = 1024


@dataclass
class AudioFrame:
    """A single frame of audio data."""

    data: np.ndarray
    sample_rate: int
    channels: int
    timestamp: float


class AudioInputProvider(abc.ABC):
    """Abstract base class for audio input providers."""

    def __init__(self, config: AudioConfig | None = None):
        self.config = config or AudioConfig()
        self._is_recording = False

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Provider name."""
        pass

    @abc.abstractmethod
    def start(self) -> None:
        """Start audio capture."""
        pass

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop audio capture."""
        pass

    @abc.abstractmethod
    def read(self, frames: int | None = None) -> AudioFrame | None:
        """Read audio data.

        Args:
            frames: Number of frames to read, or None for default chunk size.

        Returns:
            AudioFrame or None if no data available.
        """
        pass

    @abc.abstractmethod
    def __enter__(self) -> AudioInputProvider:
        """Context manager entry."""
        pass

    @abc.abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        pass

    @property
    def is_recording(self) -> bool:
        return self._is_recording


class MicrophoneProvider(AudioInputProvider):
    """Microphone audio input provider using sounddevice."""

    def __init__(self, config: AudioConfig | None = None, device: int | None = None):
        super().__init__(config)
        self.device = device
        self._stream = None
        self._buffer: list[np.ndarray] = []
        self._buffer_lock = None

        # Try to import sounddevice
        try:
            import sounddevice as sd

            self._sd = sd
            self._available = True
        except ImportError:
            self._sd = None
            self._available = False

        # Try to import threading for buffer lock
        try:
            import threading

            self._buffer_lock = threading.Lock()
        except ImportError:
            pass

    @property
    def name(self) -> str:
        return "microphone"

    def start(self) -> None:
        if not self._available:
            raise RuntimeError("sounddevice not available. Install with: pip install sounddevice")

        if self._is_recording:
            return

        self._buffer = []

        def callback(indata, frames, time_info, status):
            if status:
                pass  # Handle status if needed
            if self._buffer_lock:
                with self._buffer_lock:
                    self._buffer.append(indata.copy())
            else:
                self._buffer.append(indata.copy())

        self._stream = self._sd.InputStream(
            samplerate=self.config.sample_rate,
            channels=self.config.channels,
            dtype=self.config.dtype,
            device=self.device,
            callback=callback,
            blocksize=self.config.chunk_size,
        )
        if self._stream is not None:
            self._stream.start()
        self._is_recording = True

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._is_recording = False

    def read(self, frames: int | None = None) -> AudioFrame | None:
        if not self._is_recording or not self._buffer:
            return None

        if self._buffer_lock:
            with self._buffer_lock:
                if not self._buffer:
                    return None
                data = np.concatenate(self._buffer, axis=0)
                self._buffer.clear()
        else:
            if not self._buffer:
                return None
            data = np.concatenate(self._buffer, axis=0)
            self._buffer.clear()

        return AudioFrame(
            data=data,
            sample_rate=self.config.sample_rate,
            channels=self.config.channels,
            timestamp=0.0,  # Could use time.time() for real timestamp
        )

    def __enter__(self) -> MicrophoneProvider:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


class FileProvider(AudioInputProvider):
    """File-based audio input provider."""

    def __init__(self, file_path: str, config: AudioConfig | None = None):
        super().__init__(config)
        self.file_path = Path(file_path)
        self._file: BinaryIO | None = None
        self._wave_file: wave.Wave_read | None = None
        self._sample_rate = self.config.sample_rate
        self._channels = self.config.channels
        self._position = 0

    @property
    def name(self) -> str:
        return f"file:{self.file_path.name}"

    def start(self) -> None:
        if not self.file_path.exists():
            raise FileNotFoundError(f"Audio file not found: {self.file_path}")

        self._file = open(self.file_path, "rb")
        self._wave_file = wave.open(self._file, "rb")

        # Update config from file
        self._sample_rate = self._wave_file.getframerate()
        self._channels = self._wave_file.getnchannels()
        self._is_recording = True
        self._position = 0

    def stop(self) -> None:
        if self._wave_file:
            self._wave_file.close()
            self._wave_file = None
        if self._file:
            self._file.close()
            self._file = None
        self._is_recording = False

    def read(self, frames: int | None = None) -> AudioFrame | None:
        if not self._is_recording or not self._wave_file:
            return None

        frames = frames or self.config.chunk_size
        data = self._wave_file.readframes(frames)

        if not data:
            return None

        # Convert to numpy array
        dtype = np.int16  # Assume 16-bit for now
        audio_data: np.ndarray = np.frombuffer(data, dtype=dtype)

        # Handle stereo
        if self._channels > 1:
            audio_data = audio_data.reshape(-1, self._channels)

        self._position += len(audio_data)

        return AudioFrame(
            data=audio_data,
            sample_rate=self._sample_rate,
            channels=self._channels,
            timestamp=self._position / self._sample_rate,
        )

    def seek(self, position: float) -> None:
        """Seek to a position in seconds."""
        if self._wave_file:
            frame_pos = int(position * self._sample_rate)
            self._wave_file.setpos(frame_pos)
            self._position = frame_pos

    def get_duration(self) -> float:
        """Get audio duration in seconds."""
        if self._wave_file:
            return self._wave_file.getnframes() / self._wave_file.getframerate()
        return 0.0

    def __enter__(self) -> FileProvider:
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()


def create_audio_provider(source: str, config: AudioConfig | None = None, **kwargs) -> AudioInputProvider:
    """Factory function to create audio input provider.

    Args:
        source: "microphone" or file path
        config: Audio configuration
        **kwargs: Additional provider-specific arguments

    Returns:
        AudioInputProvider instance
    """
    if source == "microphone":
        return MicrophoneProvider(config, **kwargs)
    else:
        return FileProvider(source, config)
