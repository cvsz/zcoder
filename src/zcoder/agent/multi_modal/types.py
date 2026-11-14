"""Multi-modal type definitions for Phase 16.

Defines the data structures for representing different modalities
(text, image, audio, video) and their integration in the ZCoder system.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class ModalityType(Enum):
    """Types of modalities supported."""

    TEXT = auto()
    IMAGE = auto()
    AUDIO = auto()
    VIDEO = auto()
    PDF = auto()
    CODE = auto()


@dataclass
class ModalityInfo:
    """Metadata about a modality's capabilities."""

    type: ModalityType
    supported: bool = True
    description: str = ""
    file_extensions: list[str] = field(default_factory=list)


@dataclass
class MultiModalContent:
    """Container for multi-modal content with associated metadata."""

    modality: ModalityType
    data: bytes | str | None = None  # Raw data or path reference
    mime_type: str | None = None
    source: str | None = None  # Source file path or URL
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModalityResult:
    """Result from processing a modality."""

    success: bool
    content: MultiModalContent | None = None
    extracted_text: str | None = None  # Text extracted from non-text modalities
    confidence: float = 0.0
    error: str | None = None


@dataclass
class MultiModalRequest:
    """Request for multi-modal processing."""

    modalities: list[ModalityType]
    prompt: str
    content: list[MultiModalContent]
    model_preferences: list[str] | None = None
    temperature: float = 0.7
    max_tokens: int | None = None


@dataclass
class MultiModalResponse:
    """Response from multi-modal processing."""

    text: str
    citations: list[str] = field(default_factory=list)
    modality_breakdown: dict[ModalityType, bool] = field(default_factory=dict)
    token_usage: dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0


# Predefined modality information
MODALITY_INFO: dict[ModalityType, ModalityInfo] = {
    ModalityType.TEXT: ModalityInfo(
        type=ModalityType.TEXT,
        supported=True,
        description="Pure text input/output",
        file_extensions=[".txt", ".md", ".py", ".js", ".ts", ".mdx"],
    ),
    ModalityType.IMAGE: ModalityInfo(
        type=ModalityType.IMAGE,
        supported=True,
        description="Image input (supports analysis, description, OCR)",
        file_extensions=[".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"],
    ),
    ModalityType.AUDIO: ModalityInfo(
        type=ModalityType.AUDIO,
        supported=True,
        description="Audio input (speech-to-text, analysis)",
        file_extensions=[".wav", ".mp3", ".m4a", ".flac", ".ogg", ".oga"],
    ),
    ModalityType.VIDEO: ModalityInfo(
        type=ModalityType.VIDEO,
        supported=True,
        description="Video input (frame extraction, analysis, transcription)",
        file_extensions=[".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"],
    ),
    ModalityType.PDF: ModalityInfo(
        type=ModalityType.PDF,
        supported=True,
        description="PDF document understanding (text extraction, tables, forms)",
        file_extensions=[".pdf"],
    ),
    ModalityType.CODE: ModalityInfo(
        type=ModalityType.CODE,
        supported=True,
        description="Code analysis, refactoring, generation",
        file_extensions=[".py", ".js", ".ts", ".go", ".java", ".rs", ".c", ".cpp", ".h"],
    ),
}


def get_modality_info(modality: ModalityType) -> ModalityInfo:
    """Get information about a specific modality type."""
    return MODALITY_INFO.get(modality, ModalityInfo(type=modality))


def is_modality_supported(modality: ModalityType) -> bool:
    """Check if a modality is supported."""
    return MODALITY_INFO.get(modality, ModalityInfo(type=modality)).supported
