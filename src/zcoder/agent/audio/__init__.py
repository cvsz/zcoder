"""
Audio subsystem for ZCoder.

Provides:
- Audio input providers (microphone, file)
- Speech-to-Text (STT) adapters
- Voice Activity Detection (VAD)
- Audio streaming contracts
- Model lifecycle hooks
"""

from .providers import (
    AudioConfig,
    AudioFrame,
    AudioInputProvider,
    FileProvider,
    MicrophoneProvider,
    create_audio_provider,
)
from .streaming import (
    AudioChunk,
    AudioStream,
    AudioStreamConfig,
    AudioStreamMixer,
    CallbackAudioStream,
    MemoryAudioStream,
    ThreadedAudioStream,
    create_audio_stream,
)
from .stt import (
    OpenAIWhisperSTT,
    STTAdapter,
    STTResult,
    WhisperSTT,
    create_stt_adapter,
)
from .vad import (
    VAD,
    SileroVAD,
    VADResult,
    VADSegment,
    WebRTCVAD,
    create_vad,
)

__all__ = [
    "AudioInputProvider",
    "MicrophoneProvider",
    "FileProvider",
    "AudioConfig",
    "AudioFrame",
    "create_audio_provider",
    "STTAdapter",
    "WhisperSTT",
    "OpenAIWhisperSTT",
    "STTResult",
    "create_stt_adapter",
    "VAD",
    "SileroVAD",
    "WebRTCVAD",
    "VADResult",
    "VADSegment",
    "create_vad",
    "AudioStream",
    "AudioStreamConfig",
    "AudioChunk",
    "MemoryAudioStream",
    "CallbackAudioStream",
    "ThreadedAudioStream",
    "AudioStreamMixer",
    "create_audio_stream",
]
