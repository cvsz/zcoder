"""Multi-modal orchestrator for Phase 16.

Integrates text, image, audio, and code modalities for mixed-modal reasoning.
Wires up existing extraction components (PDF, video, audio, image) into a
unified pipeline that can process combined modality requests.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from zcoder.agent.multi_modal.audio import process_audio_for_ml
from zcoder.agent.multi_modal.pdf import process_pdf_for_ml
from zcoder.agent.multi_modal.types import (
    ModalityResult,
    ModalityType,
    MultiModalContent,
    MultiModalRequest,
    MultiModalResponse,
    get_modality_info,
)
from zcoder.agent.multi_modal.video import process_video_for_ml
from zcoder.core.exceptions import ZCoderError

logger = logging.getLogger(__name__)


def orchestrate_multi_modal(
    request: MultiModalRequest,
    api_key: str = "",
    model: str = "claude-sonnet-5-5",
    timeout: int | None = None,
) -> MultiModalResponse:
    """Orchestrate mixed-modal reasoning across supported modalities.

    Process all enabled modalities in the request, extract relevant content
    (text, tables, transcriptions, descriptions), and combine them into a
    unified context for the model.

    Args:
        request: The multi-modal request specifying modalities, prompt, and content
        api_key: API key for model calls (optional, for local models)
        model: Model ID to use for the final reasoning step
        timeout: Optional timeout in seconds for processing

    Returns:
        MultiModalResponse with combined text, citations, and modality breakdown

    Raises:
        ZCoderError: If no supported modalities are found or processing fails
    """
    # Validate request
    if not request.modalities:
        raise ZCoderError("No modalities specified in the request")

    # Track processing results per modality
    modality_results: dict[ModalityType, ModalityResult] = {}
    enabled_modalities: list[ModalityType] = []

    # Process each requested modality
    for modality in request.modalities:
        info = get_modality_info(modality)
        if not info.supported:
            logger.warning(f"Modality {modality} is not supported, skipping")
            continue

        enabled_modalities.append(modality)
        result: ModalityResult | None = None

        # Route to the appropriate processor based on modality type
        try:
            if modality == ModalityType.TEXT:
                # Text is already in the request prompt
                result = ModalityResult(
                    success=True,
                    extracted_text=request.prompt,
                    confidence=1.0,
                )

            elif modality == ModalityType.IMAGE:
                # Image data should be in request.content
                image_content = next((c for c in request.content if c.modality == modality), None)
                if image_content and image_content.data:
                    # For now, mark as supported; actual image analysis
                    # would require a vision-enabled model
                    result = ModalityResult(
                        success=True,
                        extracted_text=f"[Image: {image_content.source or 'unknown'}]",
                        confidence=0.8,
                    )
                else:
                    logger.warning(f"No image data provided for modality {modality}")

            elif modality == ModalityType.AUDIO:
                audio_content = next((c for c in request.content if c.modality == modality), None)
                if audio_content and audio_content.data:
                    result = process_audio_for_ml(Path(audio_content.data))
                else:
                    logger.warning(f"No audio data provided for modality {modality}")

            elif modality == ModalityType.VIDEO:
                video_content = next((c for c in request.content if c.modality == modality), None)
                if video_content and video_content.data:
                    result = process_video_for_ml(Path(video_content.data))
                else:
                    logger.warning(f"No video data provided for modality {modality}")

            elif modality == ModalityType.PDF:
                pdf_content = next((c for c in request.content if c.modality == modality), None)
                if pdf_content and pdf_content.data:
                    result = process_pdf_for_ml(Path(pdf_content.data))
                else:
                    logger.warning(f"No PDF data provided for modality {modality}")

            elif modality == ModalityType.CODE:
                # Code is text-based; extract from prompt or content
                code_content = request.prompt or ""
                if request.content:
                    # Try to find code in content data
                    for content_item in request.content:
                        if content_item.modality == modality and content_item.data:
                            code_content = str(content_item.data)
                            break
                result = ModalityResult(
                    success=True,
                    extracted_text=code_content,
                    confidence=1.0,
                )

            else:
                logger.warning(f"Unknown modality type: {modality}")

        except Exception as e:
            logger.error(f"Error processing modality {modality}: {e}")
            result = ModalityResult(
                success=False,
                error=str(e),
                confidence=0.0,
            )

        if result is not None:
            modality_results[modality] = result

    # If no modalities processed successfully, raise error
    if not modality_results:
        raise ZCoderError("No modalities could be processed successfully")

    # Build combined context from all processed modalities
    combined_parts: list[str] = []
    citations: list[str] = []
    modality_breakdown: dict[ModalityType, bool] = {}

    for modality in enabled_modalities:
        if modality in modality_results:
            result = modality_results[modality]
            modality_breakdown[modality] = result.success

            if result.extracted_text and result.extracted_text.strip():
                # Prepend modality type marker for model awareness
                marker = {
                    ModalityType.TEXT: "",
                    ModalityType.IMAGE: "[IMAGE] ",
                    ModalityType.AUDIO: "[AUDIO] ",
                    ModalityType.VIDEO: "[VIDEO] ",
                    ModalityType.PDF: "[PDF] ",
                    ModalityType.CODE: "[CODE] ",
                }.get(modality, "")
                text_prefix = f"{marker}{result.extracted_text.strip()}"
                combined_parts.append(text_prefix)

            # Collect citations from PDF and other structured results
            if result.error is None and result.success:
                if modality == ModalityType.PDF:
                    # PDF structure can provide heading citations
                    citations.append(f"[PDF: {result.source or 'unknown'}]")

        else:
            modality_breakdown[modality] = False

    # Combine all extracted text
    combined_text = "\n\n---\n\n".join(combined_parts) if combined_parts else ""

    # Build the final response
    response = MultiModalResponse(
        text=combined_text or "[No extractable content from specified modalities]",
        citations=citations if citations else None,
        modality_breakdown=modality_breakdown,
        token_usage={},
        cost_usd=0.0,
    )

    logger.info(
        f"Multi-modal orchestration complete: {len(modality_results)} modalities "
        f"processed, combined text length: {len(combined_text)}"
    )

    return response


def cmd_multi_modal(
    modalities: str,
    prompt: str,
    files: list[str] | None = None,
    api_key: str = "",
    model: str = "claude-sonnet-5-5",
) -> MultiModalResponse:
    """CLI command for multi-modal processing.

    Accepts a comma-separated list of modalities and optional file paths,
    then orchestrates mixed-modal reasoning.

    Supported modalities: text, image, audio, video, pdf, code

    Args:
        modalities: Comma-separated list of modality types (e.g., "text,image,audio")
        prompt: The main prompt/query for the model
        files: Optional list of file paths to process
        api_key: API key for model calls
        model: Model ID to use

    Returns:
        MultiModalResponse with combined results
    """
    modality_list = [ModalityType(m.strip()) for m in modalities.split(",") if m.strip()]

    # Build content from files if provided
    content: list[MultiModalContent] = []
    if files:
        for fp in files:
            path = Path(fp)
            if not path.exists():
                logger.warning(f"File not found: {fp}")
                continue

            ext = path.suffix.lower()
            # Determine modality from file extension
            modality = ModalityType.TEXT  # default
            if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tiff"}:
                modality = ModalityType.IMAGE
            elif ext in {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".oga"}:
                modality = ModalityType.AUDIO
            elif ext in {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}:
                modality = ModalityType.VIDEO
            elif ext == ".pdf":
                modality = ModalityType.PDF
            elif ext in {".py", ".js", ".ts", ".go", ".java", ".rs", ".c", ".cpp", ".h"}:
                modality = ModalityType.CODE

            content.append(
                MultiModalContent(
                    modality=modality,
                    data=str(path),  # Path reference; actual data loading happens in processor
                    mime_type=f"image/{path.suffix.lstrip('.')}" if modality == ModalityType.IMAGE else None,
                    source=str(path),
                )
            )

    request = MultiModalRequest(
        modalities=modality_list,
        prompt=prompt,
        content=content,
    )

    return orchestrate_multi_modal(request, api_key=api_key, model=model)


# ── CLI entry point ──────────────────────────────────────────────────────


def main_cli() -> None:
    """CLI entry point for multi-modal orchestration."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: zcoder multimodal <modalities>:<prompt> [file1] [file2] ...")
        print("Supported modalities: text, image, audio, video, pdf, code")
        print()
        print("Examples:")
        print("  zcoder multimodal text:'Analyze this code' code.py")
        print("  zcoder multimodal text,image:'Describe this image' photo.jpg")
        print("  zcoder multimodal text,audio:'Transcribe this audio' recording.wav")
        sys.exit(1)

    # Parse arguments: modalities:prompt [file1] [file2] ...
    arg = sys.argv[1]
    if ":" in arg:
        modalities_part, prompt_part = arg.split(":", 1)
        modalities = [m.strip() for m in modalities_part.split(",")]
        prompt = prompt_part
    else:
        print("Error: Expected format 'modalities:prompt'")
        sys.exit(1)

    # Remaining args are file paths
    files = sys.argv[2:] if len(sys.argv) > 2 else []

    # Determine API key from env or default
    api_key = os.getenv("ANTHROPIC_API_KEY", "")

    try:
        response = cmd_multi_modal(
            modalities=",".join(modalities),
            prompt=prompt,
            files=files,
            api_key=api_key,
        )

        print("\n=== Multi-Modal Reasoning Result ===\n")
        print(f"Modality breakdown: {response.modality_breakdown}")
        if response.citations:
            print(f"\nCitations: {response.citations}")
        print(f"\nExtracted text:\n{response.text}")
        if response.cost_usd > 0:
            print(f"\nCost: \${response.cost_usd:.4f}")

    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)
