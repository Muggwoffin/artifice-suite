from __future__ import annotations

import gc
import logging
from dataclasses import dataclass
from pathlib import Path

import torch

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    speaker: str
    start: float
    end: float
    text: str


class TranscriptionEngine:
    """Wraps WhisperX for transcription, alignment, and diarization.

    On first use the models are lazy-loaded and cached on the instance.
    Calling `unload()` frees VRAM explicitly.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        hf_token: str = "",
    ):
        self._model_size = model_size
        self._device = self._resolve_device(device)
        self._hf_token = hf_token

        self._whisper_model = None
        self._align_model = None
        self._diarize_model = None

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    def _ensure_models(self) -> None:
        if self._whisper_model is not None:
            return

        import whisperx

        logger.info("Loading WhisperX model %s on %s", self._model_size, self._device)
        self._whisper_model = whisperx.load_model(
            self._model_size, self._device, compute_type="float16" if self._device == "cuda" else "int8"
        )

        logger.info("Loading alignment model...")
        model_a, metadata = whisperx.load_align_model(
            language_code="en", device=self._device
        )
        self._align_model = (model_a, metadata)

        logger.info("Loading diarization model...")
        self._diarize_model = whisperx.DiarizationPipeline(
            use_auth_token=self._hf_token, device=self._device
        )

    def unload(self) -> None:
        self._whisper_model = None
        self._align_model = None
        self._diarize_model = None
        gc.collect()
        if self._device == "cuda":
            torch.cuda.empty_cache()
        logger.info("Models unloaded and VRAM freed")

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        language: str | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        progress_callback: "callable | None" = None,
    ) -> list[Segment]:
        """Run full pipeline: transcribe -> align -> diarize.

        Returns a list of Segment dataclasses ordered by start time.
        """
        import whisperx

        self._ensure_models()
        audio_path = str(audio_path)

        if progress_callback:
            progress_callback(0.1)

        # 1. Transcribe
        logger.info("Transcribing %s", audio_path)
        result = self._whisper_model.transcribe(audio_path, batch_size=16, language=language)
        if progress_callback:
            progress_callback(0.4)

        # 2. Align
        logger.info("Aligning transcript...")
        align_model, metadata = self._align_model
        result = whisperx.align(
            result["segments"], align_model, metadata, audio_path, self._device
        )
        if progress_callback:
            progress_callback(0.6)

        # 3. Diarize
        logger.info("Running diarization...")
        diarize_segments = self._diarize_model(
            audio_path,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        result = whisperx.assign_word_speakers(diarize_segments, result)
        if progress_callback:
            progress_callback(0.9)

        # 4. Build segments
        segments: list[Segment] = []
        for seg in result.get("segments", []):
            segments.append(
                Segment(
                    speaker=seg.get("speaker", "SPEAKER_00"),
                    start=seg.get("start", 0.0),
                    end=seg.get("end", 0.0),
                    text=seg.get("text", "").strip(),
                )
            )

        segments.sort(key=lambda s: s.start)

        if progress_callback:
            progress_callback(1.0)

        return segments
