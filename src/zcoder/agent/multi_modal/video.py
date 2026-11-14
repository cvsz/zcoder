"""Video frame extraction and analysis for Phase 16.

Provides functionality to extract frames from video files,
generate thumbnails, and perform basic video metadata analysis.
Uses FFmpeg under the hood for frame extraction.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from zcoder.agent.multi_modal.types import (
    ModalityResult,
    ModalityType,
    MultiModalContent,
)


def extract_frames(
    video_path: str | Path,
    num_frames: int = 8,
    min_duration: float = 0.0,
    max_duration: float | None = None,
) -> list[dict[str, Any]]:
    """
    Extract key frames from a video file.

    Args:
        video_path: Path to the video file
        num_frames: Number of frames to extract (default: 8, evenly spaced)
        min_duration: Minimum video duration to consider (seconds)
        max_duration: Maximum video duration to process (seconds); None = full video

    Returns:
        List of dicts with frame metadata:
        - frame_number: Frame number (1-indexed)
        - timestamp: Timestamp in seconds
        - filepath: Path to saved frame image
        - width: Frame width in pixels
        - height: Frame height in pixels
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    # Get video duration using ffprobe
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0.0
    except (FileNotFoundError, ValueError):
        duration = 0.0
        print("[WARN] ffprobe not available; cannot determine video duration")

    # Apply duration bounds
    if max_duration is None:
        max_duration = duration
    if min_duration > 0 and duration > 0:
        max_duration = min(max_duration, duration)

    if duration <= 0:
        print("[WARN] Could not determine video duration; extracting from beginning")

    # Calculate timestamps for even frame spacing
    effective_duration = max(max_duration - min_duration, 1.0)
    timestamps = []
    for i in range(num_frames):
        t = min(min_duration + (i / (num_frames - 1)) * effective_duration, max_duration - 0.1)
        timestamps.append(t)

    # Extract frames using ffmpeg
    frame_paths: list[dict[str, Any]] = []
    frame_dir = video_path.parent / f"{video_path.stem}_frames"
    frame_dir.mkdir(parents=True, exist_ok=True)

    for i, timestamp in enumerate(timestamps):
        frame_path = frame_dir / f"frame_{i:03d}_{timestamp:.2f}s.jpg"
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "quiet",
                    "-ss",
                    f"{timestamp}",
                    "-i",
                    str(video_path),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=800:600",
                    "-q:v",
                    "2",
                    str(frame_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0 and frame_path.exists():
                # Get frame dimensions using ffprobe
                try:
                    probe2 = subprocess.run(
                        [
                            "ffprobe",
                            "-v",
                            "quiet",
                            "-show_entries",
                            "image_width,height",
                            "-of",
                            "default=noprint_wrappers=1",
                            str(frame_path),
                        ],
                        capture_output=True,
                        text=True,
                        timeout=15,
                    )
                    dimensions = {}
                    for line in probe2.stdout.strip().split("\n"):
                        if "=" in line:
                            key, val = line.split("=", 1)
                            dimensions[key] = int(val)
                    width = dimensions.get("width", 0)
                    height = dimensions.get("height", 0)
                except Exception:
                    width, height = 800, 600  # default

                frame_paths.append(
                    {
                        "frame_number": i + 1,
                        "timestamp": round(timestamp, 2),
                        "filepath": str(frame_path),
                        "width": width,
                        "height": height,
                    }
                )
            else:
                print(f"[WARN] Failed to extract frame at {timestamp}s: {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            print(f"[ERROR] FFmpeg timed out at {timestamp}s")
        except Exception as e:
            print(f"[ERROR] Frame extraction error at {timestamp}s: {e}")

    return frame_paths


def get_video_metadata(video_path: str | Path) -> dict[str, Any]:
    """
    Get video metadata using ffprobe.

    Returns dict with:
    - duration: Video duration in seconds
    - width: Video width in pixels
    - height: Video height in pixels
    - fps: Frames per second
    - format: Container format
    - codec: Video codec
    """
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")

    try:
        # Get stream information
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "stream=codec_type,codec_name,r_frame_rate",
                "-of",
                "json=noprint_wrappers=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        stream_info = json.loads(result.stdout) if result.stdout else {}

        # Get format information
        format_result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "quiet",
                "-show_entries",
                "format=duration,format_name",
                "-of",
                "json=noprint_wrappers=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        format_info = json.loads(format_result.stdout) if format_result.stdout else {}

        metadata = {
            "duration": format_info.get("format", {}).get("duration", 0.0),
            "format": format_info.get("format", {}).get("format_name", "unknown"),
        }

        # Add stream info for video streams
        video_streams = [s for s in stream_info.get("streams", []) if s.get("codec_type") == "video"]
        if video_streams:
            vs = video_streams[0]  # Take first video stream
            metadata.update(
                {
                    "width": int(vs.get("width", 0)),
                    "height": int(vs.get("height", 0)),
                    "fps": _parse_fps(vs.get("r_frame_rate", "0/0")),
                    "codec": vs.get("codec_name", "unknown"),
                }
            )
        else:
            metadata.update({"width": 0, "height": 0, "fps": 0.0, "codec": "unknown"})

        return metadata
    except Exception as e:
        print(f"[ERROR] Could not get video metadata: {e}")
        return {"duration": 0.0, "width": 0, "height": 0, "fps": 0.0, "format": "unknown", "codec": "unknown"}


def _parse_fps(rate_str: str) -> float:
    """Parse fps string like '30/1' or '30' to float."""
    try:
        if "/" in rate_str:
            num, den = rate_str.split("/")
            return float(num) / float(den)
        return float(rate_str)
    except (ValueError, ZeroDivisionError):
        return 0.0


def process_video_for_ml(
    video_path: str | Path,
    output_dir: str | Path | None = None,
) -> ModalityResult:
    """
    Full video processing pipeline for machine learning workflows.

    Extracts frames, generates metadata, and returns content suitable
    for multimodal model ingestion.

    Returns ModalityResult with:
    - success: Whether processing succeeded
    - extracted_text: Combined text from any OCR'd frames (currently empty)
    - confidence: Overall processing confidence
    - error: Error message if processing failed
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return ModalityResult(
            success=False,
            error=f"Video file not found: {video_path}",
        )

    # Get video metadata
    metadata = get_video_metadata(video_path)
    duration = metadata.get("duration", 0.0)

    # Extract frames
    frames = extract_frames(video_path, num_frames=min(8, int(duration) + 1) if duration > 0 else 1)

    # Build multi-modal content
    contents: list[MultiModalContent] = []
    for frame_info in frames:
        frame_path = Path(frame_info["filepath"])
        if frame_path.exists():
            try:
                with open(frame_path, "rb") as f:
                    image_data = f.read()
                contents.append(
                    MultiModalContent(
                        modality=ModalityType.IMAGE,
                        data=image_data,
                        mime_type="image/jpeg",
                        source=str(frame_path),
                        metadata={
                            "frame_number": frame_info["frame_number"],
                            "timestamp": frame_info["timestamp"],
                            "width": frame_info.get("width", 0),
                            "height": frame_info.get("height", 0),
                        },
                    )
                )
            except Exception as e:
                print(f"[WARN] Could not read frame {frame_info['frame_number']}: {e}")

    # Determine overall success
    success = len(frames) > 0 and len(contents) > 0

    return ModalityResult(
        success=success,
        content=MultiModalContent(
            modality=ModalityType.VIDEO,
            data=b"",  # Placeholder - actual video data not stored
            metadata={
                "duration": duration,
                "frame_count": len(frames),
                "extracted_frame_count": len(contents),
            },
        ),
        extracted_text="",  # OCR not implemented at this level
        confidence=0.9 if success else 0.0,
        error=None if success else "No frames could be extracted from the video",
    )
