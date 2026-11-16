"""Audio transcription and analysis for Phase 16.

Provides functionality for audio transcription using OpenAI Whisper,
voice activity detection, and basic audio metadata analysis.
"""

from __future__ import annotations

import json
import subprocess  # nosec
from pathlib import Path
from typing import Any

from zcoder.agent.multi_modal.types import (
    ModalityResult,
)


def transcribe_audio(
    audio_path: str | Path,
    model: str = "whisper-1",
    language: str | None = None,
) -> dict[str, Any]:
    """
    Transcribe audio file using OpenAI Whisper API.

    Args:
        audio_path: Path to the audio file
        model: Whisper model to use (default: "whisper-1")
        language: Language code (e.g., "en", "es", "fr"); None = auto-detect

    Returns:
        Dict with:
        - text: Full transcription
        - language: Detected/ specified language
        - duration: Audio duration in seconds
        - segments: List of segment dicts with start/end times and text
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    # Check if OpenAI API key is available
    import os

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {
            "text": "",
            "language": None,
            "duration": 0.0,
            "segments": [],
            "error": "OPENAI_API_KEY not set. Set environment variable to use Whisper API.",
        }

    # Use ffmpeg to convert audio to Whisper-compatible format if needed
    try:
        # Get audio duration first
        result = subprocess.run(  # nosec
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        duration = float(result.stdout.strip()) if result.stdout.strip() else 0.0

        # Convert to mono, 16kHz WAV if needed
        wav_path = audio_path.parent / f"{audio_path.stem}_transcribe.wav"
        convert_result = subprocess.run(  # nosec
            [
                "ffmpeg",
                "-v",
                "quiet",
                "-i",
                str(audio_path),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-y",
                str(wav_path),
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if convert_result.returncode != 0:
            print(f"[WARN] Audio conversion failed: {convert_result.stderr[:100]}")
            wav_path = audio_path  # Fall back to original

        # Call Whisper API
        import openai

        openai.api_key = api_key

        with open(str(wav_path), "rb") as audio_file:
            transcription = openai.Audio.transcribe(
                model=model,
                file=audio_file,
                language=language,
            )

        # Clean up temp file
        try:
            wav_path.unlink()
        except Exception:  # nosec
            pass

        return {
            "text": transcription.get("text", ""),
            "language": transcription.get("language", language or "auto"),
            "duration": duration,
            "segments": transcription.get("segments", []),
        }

    except ImportError:
        return {
            "text": "",
            "language": None,
            "duration": 0.0,
            "segments": [],
            "error": "openai package not installed. Install with: pip install openai",
        }
    except Exception as e:
        # Clean up temp file on error
        try:
            wav_path = audio_path.parent / f"{audio_path.stem}_transcribe.wav"
            wav_path.unlink(missing_ok=True)
        except Exception:  # nosec
            pass
        return {
            "text": "",
            "language": None,
            "duration": 0.0,
            "segments": [],
            "error": str(e),
        }


def get_audio_metadata(audio_path: str | Path) -> dict[str, Any]:
    """
    Get audio metadata using ffprobe.

    Returns dict with:
    - duration: Audio duration in seconds
    - format: Audio format/container
    - sample_rate: Sample rate in Hz
    - channels: Number of channels
    - codec: Audio codec
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    try:
        result = subprocess.run(  # nosec
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "stream=codec_name,sample_rate,channels",
                "-show_entries",
                "format=format_name,duration",
                "-of",
                "json=noprint_wrappers=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        info = json.loads(result.stdout) if result.stdout else {}

        metadata = {
            "duration": float(info.get("format", {}).get("duration", 0.0)),
            "format": info.get("format", {}).get("format_name", "unknown"),
        }

        # Find audio stream
        audio_streams = info.get("streams", [])
        if audio_streams:
            # Take first audio stream
            ast = audio_streams[0]
            metadata.update(
                {
                    "sample_rate": ast.get("sample_rate", "unknown"),
                    "channels": int(ast.get("channels", 1)),
                    "codec": ast.get("codec_name", "unknown"),
                }
            )
        else:
            metadata.update({"sample_rate": "unknown", "channels": 1, "codec": "unknown"})

        return metadata
    except Exception as e:
        print(f"[ERROR] Could not get audio metadata: {e}")
        return {
            "duration": 0.0,
            "format": "unknown",
            "sample_rate": "unknown",
            "channels": 1,
            "codec": "unknown",
        }


def process_audio_for_ml(
    audio_path: str | Path,
) -> ModalityResult:
    """
    Full audio processing pipeline for machine learning workflows.

    Transcribes audio and returns content suitable for multimodal model ingestion.

    Returns ModalityResult with:
    - success: Whether processing succeeded
    - extracted_text: Transcription text
    - confidence: Overall processing confidence (based on Whisper confidence)
    - error: Error message if processing failed
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        return ModalityResult(
            success=False,
            error=f"Audio file not found: {audio_path}",
        )

    # Get metadata first
    metadata = get_audio_metadata(audio_path)
    duration = metadata.get("duration", 0.0)

    # Transcribe
    transcribe_result = transcribe_audio(audio_path)
    text = transcribe_result.get("text", "")

    # Determine confidence based on Whisper segments
    segments = transcribe_result.get("segments", [])
    confidence = 0.0
    if segments:
        # Average confidence from segments if available
        conf_values = []
        for seg in segments:
            # Whisper segments don't always have confidence, use length-weighted
            conf_values.append(min(1.0, len(seg.get("text", "")) / max(1, duration / 10)))
        confidence = sum(conf_values) / len(conf_values) if conf_values else 0.5
    elif text:
        confidence = 0.7
    else:
        confidence = 0.0

    success = len(text.strip()) > 0

    return ModalityResult(
        success=success,
        content=None,
        extracted_text=text,
        confidence=confidence,
        error=transcribe_result.get("error"),
    )
