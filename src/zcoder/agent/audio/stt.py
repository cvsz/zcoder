"""
Speech-to-Text (STT) adapters for ZCoder.

Provides STT adapters for various providers including Whisper and OpenAI Whisper API.
"""

from __future__ import annotations

import abc
import os
import tempfile
from dataclasses import dataclass

import numpy as np


@dataclass
class STTResult:
    """Result of speech-to-text transcription."""

    text: str
    language: str | None = None
    confidence: float | None = None
    segments: list[dict] | None = None
    language_probability: float | None = None
    duration: float | None = None


class STTAdapter(abc.ABC):
    """Abstract base class for STT adapters."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Adapter name."""
        pass

    @abc.abstractmethod
    def transcribe(self, audio_data: np.ndarray, sample_rate: int, **kwargs) -> STTResult:
        """Transcribe audio data to text.

        Args:
            audio_data: Audio data as numpy array
            sample_rate: Sample rate in Hz
            **kwargs: Additional provider-specific arguments

        Returns:
            STTResult with transcription
        """
        pass

    @abc.abstractmethod
    def transcribe_file(self, file_path: str, **kwargs) -> STTResult:
        """Transcribe audio file to text.

        Args:
            file_path: Path to audio file
            **kwargs: Additional provider-specific arguments

        Returns:
            STTResult with transcription
        """
        pass

    @abc.abstractmethod
    def get_supported_languages(self) -> list[str]:
        """Get list of supported languages."""
        pass


class WhisperSTT(STTAdapter):
    """Whisper STT using local whisper.cpp or faster-whisper."""

    def __init__(self, model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
        self._model_name = model_size

        # Try to import faster-whisper or whisper
        self._whisper = None
        try:
            from faster_whisper import WhisperModel

            self._whisper_model_class = WhisperModel
            self._backend = "faster-whisper"
        except ImportError:
            try:
                import whisper

                self._whisper = whisper
                self._backend = "whisper"
            except ImportError:
                self._backend = None

    @property
    def name(self) -> str:
        return f"whisper-{self.model_size}"

    def _load_model(self):
        """Lazy load the model."""
        if self._model is None:
            if self._backend == "faster-whisper":
                self._model = self._whisper_model_class(
                    self.model_size,
                    device=self.device,
                    compute_type="int8" if self.device == "cpu" else "float16",
                )
            elif self._backend == "whisper":
                self._model = self._whisper.load_model(self.model_size)
            else:
                raise RuntimeError("No Whisper backend available. Install faster-whisper or whisper.")

    def transcribe(self, audio_data: np.ndarray, sample_rate: int, **kwargs) -> STTResult:
        self._load_model()

        # Convert to float32 if needed
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32) / 32768.0

        # Save to temp file for whisper
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            import wave

            # Write WAV file
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                # Convert float32 to int16
                wf.writeframes((audio_data * 32767).astype(np.int16).tobytes())

            tmp_path = tmp.name

        try:
            return self.transcribe_file(tmp.name)
        finally:
            os.unlink(tmp_path)

    def transcribe_file(self, file_path: str, **kwargs) -> STTResult:
        self._load_model()

        language = kwargs.get("language")
        beam_size = kwargs.get("beam_size", 5)

        if self._backend == "faster-whisper":
            segments, info = self._model.transcribe(
                file_path,
                language=kwargs.get("language"),
                beam_size=beam_size,
                vad_filter=kwargs.get("vad_filter", True),
                vad_parameters=kwargs.get("vad_parameters"),
            )

            segments_list = []
            text_parts = []
            for segment in segments:
                segments_list.append(
                    {
                        "start": segment.start,
                        "end": segment.end,
                        "text": segment.text,
                    }
                )
                text_parts.append(segment.text)

            return STTResult(
                text=" ".join(text_parts),
                language=info.language,
                confidence=info.language_probability,
                segments=segments_list,
                language_probability=info.language_probability,
                duration=info.duration,
            )

        elif self._backend == "whisper":
            result = self._model.transcribe(
                file_path,
                language=language,
                fp16=False,
            )

            segments_list = []
            for segment in result.get("segments", []):
                segments_list.append(
                    {
                        "start": segment["start"],
                        "end": segment["end"],
                        "text": segment["text"],
                    }
                )

            return STTResult(
                text=result["text"],
                language=result.get("language"),
                segments=segments_list,
            )

        raise RuntimeError("No Whisper backend available")

    def get_supported_languages(self) -> list[str]:
        return [
            "en",
            "zh",
            "de",
            "es",
            "ru",
            "ko",
            "fr",
            "ja",
            "pt",
            "tr",
            "pl",
            "ca",
            "nl",
            "ar",
            "sv",
            "it",
            "id",
            "hi",
            "fi",
            "vi",
            "he",
            "uk",
            "el",
            "ms",
            "cs",
            "ro",
            "da",
            "hu",
            "ta",
            "no",
            "th",
            "ur",
            "hr",
            "bg",
            "lt",
            "la",
            "mi",
            "ml",
            "cy",
            "sk",
            "te",
            "fa",
            "lv",
            "bn",
            "sr",
            "az",
            "sl",
            "kn",
            "et",
            "mk",
            "br",
            "eu",
            "is",
            "hy",
            "ne",
            "mn",
            "bs",
            "kk",
            "sq",
            "sw",
            "gl",
            "mr",
            "pa",
            "si",
            "km",
            "sn",
            "yo",
            "so",
            "af",
            "oc",
            "ka",
            "be",
            "tg",
            "sd",
            "gu",
            "am",
            "yi",
            "lo",
            "uz",
            "fo",
            "ht",
            "ps",
            "tk",
            "nn",
            "mt",
            "sa",
            "lb",
            "my",
            "bo",
            "tl",
            "mg",
            "as",
            "tt",
            "haw",
            "ln",
            "ha",
            "ba",
            "jw",
            "su",
        ]


class OpenAIWhisperSTT(STTAdapter):
    """OpenAI Whisper API STT adapter."""

    def __init__(self, api_key: str, model: str = "whisper-1"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1/audio/transcriptions"

    @property
    def name(self) -> str:
        return f"openai-whisper-{self.model}"

    def transcribe(self, audio_data: np.ndarray, sample_rate: int, **kwargs) -> STTResult:
        # Save to temp file
        import tempfile
        import wave

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            import wave

            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes((audio_data * 32767).astype(np.int16).tobytes())

            tmp_path = tmp.name

        try:
            return self.transcribe_file(tmp_path)
        finally:
            os.unlink(tmp_path)

    def transcribe_file(self, file_path: str, **kwargs) -> STTResult:
        import requests

        with open(file_path, "rb") as f:
            files = {"file": (os.path.basename(file_path), f, "audio/wav")}
            data = {
                "model": self.model,
                "language": kwargs.get("language"),
                "response_format": kwargs.get("response_format", "verbose_json"),
                "temperature": kwargs.get("temperature", 0.0),
            }

            headers = {"Authorization": f"Bearer {self.api_key}"}

            response = requests.post(
                self.base_url,
                headers=headers,
                files=files,
                data=data,
                timeout=60,
            )

            response.raise_for_status()
            result = response.json()

            segments_list = None
            if "segments" in result:
                segments_list = []
                for seg in result["segments"]:
                    segments_list.append(
                        {
                            "start": seg["start"],
                            "end": seg["end"],
                            "text": seg["text"],
                        }
                    )

            return STTResult(
                text=result.get("text", ""),
                language=result.get("language"),
                segments=segments_list,
            )

    def get_supported_languages(self) -> list[str]:
        return [
            "en",
            "zh",
            "de",
            "es",
            "ru",
            "ko",
            "fr",
            "ja",
            "pt",
            "tr",
            "pl",
            "ca",
            "nl",
            "ar",
            "sv",
            "it",
            "id",
            "hi",
            "fi",
            "vi",
            "he",
            "uk",
            "el",
            "ms",
            "cs",
            "ro",
            "da",
            "hu",
            "ta",
            "no",
            "th",
            "ur",
            "hr",
            "bg",
            "lt",
            "la",
            "mi",
            "ml",
            "cy",
            "sk",
        ]


def create_stt_adapter(adapter_type: str, **kwargs) -> STTAdapter:
    """Factory function to create STT adapter.

    Args:
        adapter_type: "whisper" or "openai-whisper"
        **kwargs: Adapter-specific arguments

    Returns:
        STTAdapter instance
    """
    if adapter_type == "whisper":
        return WhisperSTT(**kwargs)
    elif adapter_type == "openai-whisper":
        return OpenAIWhisperSTT(**kwargs)
    else:
        raise ValueError(f"Unknown STT adapter type: {adapter_type}")
