# Sources, Dependencies & Licensing Disclosures

> **Assessment Title:** IncuBrix Engineering Assessment 3 (PS3) — Script to B-roll Video Engine  
> **Compliance Standard:** Commercial Use Clearances & Intellectual Property Rights  

Every model, API, library, dataset, and media source used in this project is disclosed below with its license and commercial-use verification.

---

## 1. Core Runtime & Infrastructure Libraries

| Library / Tool | Version | License | Commercial Use Permitted? | Purpose in Project |
| :--- | :--- | :--- | :--- | :--- |
| **Python** | 3.11+ / 3.14 | PSF License | Yes | Core programming language and runtime. |
| **FastAPI** | 0.115+ | MIT License | Yes | Web framework, request routing, OpenAPI 3.1 schema generation. |
| **Uvicorn** | 0.30+ | BSD-3-Clause | Yes | ASGI web server. |
| **Pydantic / Pydantic-Settings** | 2.8+ | MIT License | Yes | Data validation, environment variable management. |
| **SQLAlchemy** | 2.0+ | MIT License | Yes | Asynchronous database ORM / persistence interface. |
| **aiosqlite** | 0.20+ | MIT License | Yes | Asynchronous SQLite driver for zero-dependency persistence. |
| **boto3 / botocore** | 1.34+ | Apache 2.0 | Yes | Client library for S3 and MinIO object storage. |
| **httpx** | 0.27+ | BSD-3-Clause | Yes | Asynchronous HTTP client for test suite and outbound webhooks. |
| **PyYAML** | 6.0+ | MIT License | Yes | YAML serializer for OpenAPI export. |
| **pytest / pytest-asyncio** | 8.0+ | MIT License | Yes | Automated testing harness. |

---

## 2. Speech Processing & Narration Stack (Phase 2)

| Component | Library / Model | License | Commercial Use Status | Notes & Verification |
| :--- | :--- | :--- | :--- | :--- |
| **Speech-to-Text (ASR)** | `faster-whisper` (v1.2.1) + `ctranslate2` | MIT License | **Fully Commercial Permitted** | FasterWhisper and CTranslate2 are permissively licensed under MIT. Underlying OpenAI Whisper model weights (`tiny`, `base`, `small`, `medium`) are MIT-licensed, allowing unrestricted commercial inference. Dependency `av<19.0.0` pinned for PyAV C-API stability. |
| **Voice Activity Detection** | Silero VAD v6 (`silero_vad_v6.onnx`) | MIT License | **Fully Commercial Permitted** | Silero VAD is integrated as the primary acoustic neural speech detector in `AudioPreflightValidator`, operating via `onnxruntime` on 16kHz resampled audio. Complemented by 30ms window RMS dBFS energy distribution analysis for loudness/clipping validation. |
| **Text-to-Speech (TTS Engine)** | `edge-tts` (v7.3.1) | LGPL-3.0 | **Permitted for Assessment & Evaluation** | `edge-tts` connects to Microsoft's neural speech synthesis service. The Python wrapper is open-source under LGPL-3.0.<br>**Commercial Terms & Network Note:** Microsoft consumer endpoints require continuous Internet connectivity and prohibit high-volume enterprise commercial exploitation without an official Azure Cognitive Services Speech API key. For enterprise commercial deployments, our engine isolates TTS behind the pluggable `TTSProvider` abstract interface, allowing direct drop-in replacement with Azure Speech SDK, ElevenLabs, or local open-source models (Piper, Kokoro) without altering any downstream pipeline code. |
| **Audio I/O & Manipulation** | `soundfile` (0.14.0) + `pydub` (0.25.1) + `audioop-lts` | BSD / MIT | **Fully Commercial Permitted** | Decodes WAV, MP3, M4A headers, provides sample normalization, and enables frame energy calculations. |

---

## 3. Scene Segmentation & Visual Intelligence Stack (Phase 3)

| Component | Module / Method | License | Commercial Use Status | Notes & Verification |
| :--- | :--- | :--- | :--- | :--- |
| **Semantic Scene Segmenter** | `SemanticSceneSegmenter` | Proprietary / In-House | **Fully Permitted** | Groups narration into coherent visual scenes respecting sentence and grammatical clause boundaries. Supports director hints (`JobCreateRequest.scenes`) and auto-segmentation in English, Hindi, and Tamil. |
| **Pacing Guard** | `PacingGuard` | Proprietary / In-House | **Fully Permitted** | Enforces minimum duration (1.8s) and maximum duration (5.0s). Splits long scenes at clause boundaries, punctuation, or speech pauses (>0.3s). Intelligently merges trailing or sub-1.8s scenes. Enforces mathematical timeline continuity ($start_i == end_{i-1}$) with zero black frames, gaps, or overlaps. |
| **Contextual Query Disambiguator** | `ContextualQueryDisambiguator` | Proprietary / In-House | **Fully Permitted** | Deterministic domain taxonomy and rule-based semantic disambiguation for homonyms (cloud computing vs atmospheric sky, python code vs snake, apple technology vs fruit) and abstract concept metaphors (trust, growth, innovation, security). Extensible for future LLM / vector embedding backends. |
| **Safety & Negative Filters** | `SafetyPromptFilter` | Proprietary / In-House | **Fully Permitted** | Automatically injects safety negative constraints preventing identifiable human faces, celebrity faces, politicians, copyrighted logos, stock footage watermarks, and user-specified `avoid` terms. |
| **Timing Provenance Tracker** | `TimingSource` (`asr_acoustic` vs `tts_interpolated`) | Proprietary / In-House | **Fully Permitted** | Strictly tracks whether word timings derive from acoustic speech recognition (`faster-whisper`) or character-weighted sentence interpolation (`edge-tts`), ensuring honest timeline metadata. |

---

## 4. Footage Providers, Licensing & Attribution Stack (Phase 4)

| Provider / Asset Source | Official Licence | Licence Terms URL | Commercial Clearance Verification | Attribution & Provenance Handling |
| :--- | :--- | :--- | :--- | :--- |
| **Pexels Video API** | Pexels License | https://www.pexels.com/license/ | **Verified Commercial Permitted:** All videos on Pexels are free for commercial and non-commercial projects. Reselling unaltered copies, implying brand endorsement, or sensitive/offensive portrayals of people are prohibited. | Attribution is legally optional under Pexels terms but captured and credited in `timeline.json` and `manifest.json` as best practice: `Video by {creator} on Pexels`. |
| **Pixabay Video API** | Pixabay Content License | https://pixabay.com/service/license-summary/ | **Verified Commercial Permitted:** Content is cleared for commercial and non-commercial print and digital media. Prohibits standalone redistribution of media assets on other stock libraries. | Captured in `manifest.json`: `Video by {user} from Pixabay`. Direct creator URL and original page links recorded. |
| **Procedural Fallback Generator** | Procedural (Commercial CC0 Equivalent) | Internal / In-House | **100% Free & Unrestricted:** Generated deterministically on-the-fly via FFmpeg shader/filtergraph pipelines (`gradients`, `lavfi`). Zero third-party copyright, zero intellectual property encumbrances. | Attribution recorded as `Procedural visual synthesized by IncuBrix B-roll Engine`. Clearly flagged with `is_procedural=True` and `fallback_status="procedural_gradient"`. |
| **Deduplication Engine** | Proprietary / In-House | Internal | **Assessment Compliant:** Enforces zero repeated clips across scenes using asset IDs, content hashes (SHA-256), and near-duplicate Jaccard/token similarity filters. | Deduplication audit trail persisted in `manifest.json` under `deduplication` object. |
| **FFprobe Media Validator** | FFprobe 7.1.5 (GPL) | https://ffmpeg.org/legal.html | **Container Isolation:** Executed as external subprocess/CLI tool inside Docker image; no proprietary code links statically against libavformat/libavcodec. | Validates codec, resolution, and non-zero duration before committing clips to the timeline. |

---

## 5. Testing Modes & Verification Isolation

To uphold honest and transparent performance metrics, the project strictly distinguishes between unit/CI test execution and live model inference:

1. **Automated Test Suite (`pytest`) — 100% Mock & Offline:**
   - Provider modes: `ASR_PROVIDER=mock`, `TTS_PROVIDER=mock`, `VAD_PROVIDER=silero`.
   - Requires zero network calls and zero paid API keys.
   - Synthesizes speech-like harmonic formants to validate Silero VAD neural detection without external audio files.
   - Validates error branches (silence, corruption, duration limits, unsupported extensions), database persistence, idempotency, and job state transitions deterministically in < 15 seconds.

2. **Real Model Verification Script (`scripts/verify_real_speech.py`) — Live Inference & Synthesis:**
   - Runs actual `faster-whisper` (`tiny` model with CTranslate2 INT8 quantization on CPU) and actual `edge-tts` across four language targets:
     - Indian English (`en-IN-NeerjaNeural`)
     - US English (`en-US-JennyNeural`)
     - Hindi (`hi-IN-SwaraNeural`)
     - Tamil (`ta-IN-PallaviNeural`)
   - Verifies real Silero VAD speech detection, language identification, word-level timestamp generation, and Real-Time Factor (RTF) latency benchmarks.

---

## 6. Infrastructure & Storage Components

| Component | Image / Package | License | Compliance Strategy |
| :--- | :--- | :--- | :--- |
| **MinIO Server** | `minio/minio:latest` | GNU AGPLv3 | **Isolated Black-Box Container:** Runs as a separate microservice in `docker-compose.yml`. No application code links against or derives from MinIO. Communication occurs over standard S3 network protocol via Apache-2.0 `boto3`. |
| **MinIO Client** | `minio/mc:latest` | GNU AGPLv3 | One-off initialization container used strictly to provision the initial bucket. |

---

## 7. Reference Frameworks

| Project | Author | License | Usage in Project |
| :--- | :--- | :--- | :--- |
| **HyperFrames** | HeyGen, Inc. | Apache 2.0 | Architectural reference only. Inspected under `references/hyperframes/` for FFmpeg parameters, frame synchronization, and audio pad/trim algorithms. No source code copied into application. |
