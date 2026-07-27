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


@dataclass
class TranscriptionResult:
    segments: list[Segment]
    speaker_embeddings: dict[str, list[float]]


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
        self._align_models: dict[str, tuple] = {}
        self._diarize_model = None
        self._models_ready = False
        self._last_error: str | None = None
        self._model_loader_available = True

    @staticmethod
    def _resolve_device(device: str) -> str:
        if device == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        return device

    def _ensure_models(self) -> None:
        import whisperx

        if self._whisper_model is None:
            try:
                logger.info("Loading WhisperX model %s on %s", self._model_size, self._device)
                compute_type = "float16" if self._device == "cuda" else "int8"
                self._whisper_model = whisperx.load_model(
                    self._model_size,
                    self._device,
                    compute_type=compute_type,
                    use_auth_token=self._hf_token,
                )
            except Exception as exc:
                self._last_error = str(exc)
                self._models_ready = False
                logger.error("Whisper model loading failed: %s", exc)
                raise

        if self._diarize_model is None:
            try:
                logger.info("Loading diarization model...")
                from whisperx.diarize import DiarizationPipeline

                self._diarize_model = DiarizationPipeline(token=self._hf_token, device=self._device)
            except Exception as exc:
                self._last_error = str(exc)
                self._models_ready = False
                logger.error("Diarization model loading failed: %s", exc)
                raise

        self._models_ready = True
        self._last_error = None

    def _get_align_model(self, language_code: str) -> tuple:
        if language_code not in self._align_models:
            try:
                from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
                from whisperx.alignment import (
                    DEFAULT_ALIGN_MODELS_HF,
                    DEFAULT_ALIGN_MODELS_TORCH,
                )
                from whisperx.alignment import (
                    load_align_model as _wx_load_align,
                )

                logger.info("Loading alignment model for language: %s", language_code)

                if language_code in DEFAULT_ALIGN_MODELS_TORCH:
                    model_a, metadata = _wx_load_align(
                        language_code=language_code, device=self._device
                    )
                elif language_code in DEFAULT_ALIGN_MODELS_HF:
                    model_name = DEFAULT_ALIGN_MODELS_HF[language_code]
                    processor = Wav2Vec2Processor.from_pretrained(model_name, token=self._hf_token)
                    align_model = Wav2Vec2ForCTC.from_pretrained(model_name, token=self._hf_token)
                    align_model = align_model.to(self._device)
                    vocab = processor.tokenizer.get_vocab()
                    align_dictionary = {c.lower(): i for i, c in vocab.items()}
                    metadata = {
                        "language": language_code,
                        "dictionary": align_dictionary,
                        "type": "huggingface",
                    }
                    model_a = align_model
                else:
                    model_a, metadata = _wx_load_align(
                        language_code=language_code, device=self._device
                    )

                self._align_models[language_code] = (model_a, metadata)
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
                logger.error("Alignment model loading failed for %s: %s", language_code, exc)
                raise
        return self._align_models[language_code]

    def unload(self) -> None:
        self._whisper_model = None
        self._diarize_model = None
        # Keep _models_ready = True if models were ever loaded successfully
        gc.collect()
        if self._device == "cuda":
            torch.cuda.empty_cache()
        logger.info("Models unloaded and VRAM freed")

    def health_check(self) -> dict:
        """Return engine status with 3-state model info: untested / loaded / failed."""
        gpu_info = None
        if torch.cuda.is_available():
            gpu_info = {
                "name": torch.cuda.get_device_name(0),
                "vram_total_mb": round(torch.cuda.get_device_properties(0).total_memory / 1048576),
                "vram_used_mb": round(torch.cuda.memory_allocated(0) / 1048576),
                "vram_free_mb": round(torch.cuda.memory_reserved(0) / 1048576),
            }

        # Determine 3-state: untested / loaded / failed
        if self._whisper_model is not None:
            model_state = "loaded"
        elif self._last_error:
            model_state = "failed"
        else:
            model_state = "untested"

        if self._diarize_model is not None:
            diarize_state = "loaded"
        elif self._last_error:
            diarize_state = "failed"
        else:
            diarize_state = "untested"

        if self._align_models:
            align_state = "loaded"
        elif self._last_error:
            align_state = "failed"
        else:
            align_state = "untested"

        return {
            "whisper_model": {
                "name": self._model_size,
                "state": model_state,
                "loaded": self._whisper_model is not None,
            },
            "diarization_model": {
                "state": diarize_state,
                "loaded": self._diarize_model is not None,
            },
            "alignment_models": {
                "state": align_state,
                "loaded_languages": list(self._align_models.keys()),
                "count": len(self._align_models),
            },
            "device": self._device,
            "gpu": gpu_info,
            "hf_token_configured": bool(self._hf_token),
            "last_error": self._last_error,
        }

    def preload(self) -> dict:
        """Attempt to load all models. Returns success or error."""
        try:
            self._ensure_models()
            if "en" not in self._align_models:
                self._get_align_model("en")
            return {"ok": True, "message": "All models loaded successfully"}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def transcribe(
        self,
        audio_path: str | Path,
        *,
        language: str | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        progress_callback: callable | None = None,
        custom_vocabulary: str | None = None,
        hotwords: str | None = None,
    ) -> TranscriptionResult:
        """Run full pipeline: transcribe -> align -> diarize.

        Accepts optional vocabulary strings.  *hotwords* is the preferred
        mechanism for keyword biasing (placed in the model's ``sot_prev``
        prompt).  *custom_vocabulary* is kept for backward-compatibility and
        merged with hotwords when both are provided.

        Returns a TranscriptionResult with segments and per-speaker
        centroid embeddings for cross-session speaker recognition.
        """
        import whisperx

        self._ensure_models()
        audio_path = str(audio_path)

        if progress_callback:
            progress_callback(0.1)

        # Merge vocabulary sources and set hotwords on the loaded pipeline
        merged_vocab = " ".join(filter(None, [hotwords, custom_vocabulary])).strip()
        if merged_vocab:
            self._whisper_model.options.hotwords = merged_vocab
        elif self._whisper_model.options.hotwords:
            self._whisper_model.options.hotwords = None

        # 1. Transcribe
        logger.info("Transcribing %s", audio_path)
        kwargs = {"batch_size": 16, "language": language}
        result = self._whisper_model.transcribe(audio_path, **kwargs)
        if progress_callback:
            progress_callback(0.4)

        # 2. Align (load alignment model for detected language)
        detected_lang = result.get("language", "en")
        logger.info("Aligning transcript (language: %s)...", detected_lang)
        align_model, metadata = self._get_align_model(detected_lang)
        result = whisperx.align(result["segments"], align_model, metadata, audio_path, self._device)
        if progress_callback:
            progress_callback(0.6)

        # 3. Diarize (with speaker embeddings for cross-session recognition)
        logger.info("Running diarization...")
        diarize_result = self._diarize_model(
            audio_path,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            return_embeddings=True,
        )
        diarize_segments, speaker_embeddings_raw = diarize_result
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

        # 5. Normalise speaker embeddings into a label-keyed dict
        embeddings: dict[str, list[float]] = {}
        if isinstance(speaker_embeddings_raw, dict):
            for label, emb in speaker_embeddings_raw.items():
                if isinstance(emb, (list, tuple)):
                    embeddings[label] = list(emb)

        if progress_callback:
            progress_callback(1.0)

        return TranscriptionResult(segments=segments, speaker_embeddings=embeddings)
