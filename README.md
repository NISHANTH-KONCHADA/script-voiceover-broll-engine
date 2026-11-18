# IncuBrix Script, Voiceover & B-roll Video Engine (PS3)

> **IncuBrix 2027 Software Engineer Assessment — Problem Statement 3 (PS3)**  
> **Status:** Phase 5 Complete (Audio Normalization, Subtitles & Multi-Aspect Video Assembly)  
> **API Version:** 0.1.0 (OpenAPI 3.1)  

---

## 1. System Overview

The **Script, Voiceover & B-roll Video Engine** is a containerized microservice that turns a voiceover audio recording or plain text script into a finished, commercially cleared, broadcast-ready B-roll video.

- **Phase 1 (Completed):** Enterprise foundation, FastAPI with OpenAPI 3.1, background jobs (HTTP 202), `Idempotency-Key` handling, SQLite persistence with WAL mode, MinIO S3 storage, structured JSON logging, and health probes.
- **Phase 2 (Completed):** Speech Processing & Narration Engine:
  - Audio preflight validation for MP3, WAV, M4A with 10-minute duration enforcement.
  - Silero VAD v6 neural speech activity detection and silence rejection (`NO_SPEECH_DETECTED`).
  - Modular Speech-to-Text (ASR) via `faster-whisper` with frame-accurate word-level timestamps.
  - Multilingual support for English, Hindi (`hi-IN`), and Tamil (`ta-IN`).
  - Modular Text-to-Speech (TTS) via `edge-tts` supporting Indian English, US English, Hindi, and Tamil voices with word boundary timings.
- **Phase 3 (Completed):** Semantic Scene Segmentation & Contextual Visual Intelligence:
  - Natural linguistic scene segmentation respecting sentence and clause boundaries in English, Hindi, and Tamil.
  - Pacing Guard strictly enforcing $1.8\text{ s} \le \text{scene duration} \le 5.0\text{ s}$, with intelligent sub-clause splitting, pause splitting, trailing-scene merging, and mathematically guaranteed gapless/overlap-free coverage ($start_i = end_{i-1}$).
  - Contextual query disambiguation resolving homonyms (e.g. cloud computing vs sky, python code vs animal, apple tech vs fruit) and grounding abstract concepts ("trust", "growth", "innovation", "security") into concrete visual search queries.
  - Safety constraints avoiding real identifiable human faces, celebrity faces, copyrighted logos, and watermarks, combined with custom user negative prompts (`avoid` list).
  - Explicit timing provenance tracking: distinct `asr_acoustic` vs `tts_interpolated` metadata.
  - Full output artifact generation: `scenes.json` and enriched `timeline.json` uploaded to S3/MinIO.
- **Phase 4 (Completed):** Footage Retrieval, Deduplication & Attribution Engine:
  - Multi-source stock footage retrieval integrating Pexels and Pixabay Video APIs.
  - Automatic provider failover, rate-limit backoff, and timeouts.
  - Deterministic procedural motion graphics fallback via FFmpeg (guaranteeing zero job failures).
  - Strict commercial-use licence verification (rejecting non-commercial or unclear rights).
  - Modular semantic relevance ranking with homonym conflict penalties.
  - Deduplication engine preventing repeated or near-duplicate clips across scenes.
  - Asynchronous download with disk caching and FFprobe media validation.
  - Full legal clearance, provenance, and attribution tracking in `manifest.json`.
- **Phase 5 (Completed):** Audio Normalization, Subtitles & Multi-Aspect Video Assembly:
  - EBU R128 audio loudness normalization to `-16.0 LUFS` at 48kHz stereo AAC.
  - Broadcast-ready SRT and styled ASS subtitle generation with timecodes (`00:00:00,000`).
  - Burn-in subtitle rendering with customizable typography, dark border, and shadow.
  - Multi-aspect ratio video rendering: `16:9` (1920x1080), `9:16` (1080x1920), and `1:1` (1080x1080).
  - FFmpeg concat demuxer assembly with zero black frames and zero frozen frames.
  - Frame-accurate audio-video synchronization ($\le 33\text{ ms}$ drift guarantee, zero audio drift).
  - Automated output verification via FFprobe (codec, dimensions, framerate, stream presence).

---

## 2. Architecture & Pipeline

```mermaid
flowchart TD
    subgraph Ingestion[Audio or Script Ingestion]
        AudioIn[Raw Audio: mp3, wav, m4a] --> Preflight[Audio Preflight & Silero VAD]
        ScriptIn[Script / IncuBrix Scenes] --> TTS[Neural TTS Engine\nen-IN, hi-IN, ta-IN, en-US]
    end

    subgraph SpeechProcessing[Speech Processing & Alignment]
        Preflight --> ASR[faster-whisper ASR]
        ASR --> WordTimings[Acoustic Word Timestamps]
        TTS --> WordTimingsTTS[Interpolated Word Timings]
        TTS --> MasterAudio[Master Audio Stream]
        Preflight --> MasterAudio
    end

    subgraph SceneIntelligence[Phase 3: Visual Intelligence & Segmentation]
        WordTimings --> Seg[Semantic Scene Segmenter]
        WordTimingsTTS --> Seg
        Seg --> Pacing[Pacing Guard: 1.8s - 5.0s\nZero Gaps & Overlaps]
        Pacing --> Disambig[Contextual Query Disambiguator\nHomonyms & Abstract Metaphors]
        Disambig --> Safety[Safety & Negative Constraints]
        Safety --> ScenesArtifact[scenes.json]
    end

    subgraph FootageEngine[Phase 4: Retrieval, Ranking & Dedup]
        ScenesArtifact --> Search[Multi-Source Search: Pexels / Pixabay]
        Search --> Failover[Provider Failover & Rate Limits]
        Failover --> Ranker[Semantic Relevance Ranker & Homonym Guard]
        Ranker --> Dedup[Clip Deduplicator & Near-Dup Prevention]
        Dedup --> Fallback[FFmpeg Procedural Motion Fallback]
        Dedup --> Download[Async Media Download & FFprobe Validation]
        Fallback --> Download
        Download --> TimelineArtifact[timeline.json & manifest.json Provenance]
    end

    subgraph VideoAssembly[Phase 5: Audio Normalization, Subtitles & Multi-Aspect Assembly]
        MasterAudio --> AudioNorm[Audio Normalizer: EBU R128 -16 LUFS / 48kHz]
        TimelineArtifact --> Subtitles[SRT & ASS Subtitle Styler]
        TimelineArtifact --> VideoScaler[Video Scaler & Crop: 16:9 / 9:16 / 1:1]
        VideoScaler --> Concat[FFmpeg Concat Demuxer]
        AudioNorm --> Muxer[Audio Muxer & Zero-Drift Sync Guard]
        Subtitles --> Muxer
        Concat --> Muxer
        Muxer --> Probe[FFprobe Media Validator]
    end

    subgraph Delivery[Artifact Storage & Job State]
        Probe --> S3[(MinIO / S3 Storage)]
        AudioNorm --> S3
        Subtitles --> S3
    end
```

---

## 3. Testing & Verification Modes

### Mode A: Automated Offline Test Suite (68 Tests, 100% Offline, Zero API Keys)

Runs unit, integration, and failure-recovery tests deterministically using mock providers and in-memory persistence:

```bash
# Run all 68 automated tests on host
pytest -v

# OR run all 68 automated tests inside isolated Docker container
docker compose run --rm test
```

### Mode B: Live Real-Model Speech Verification (faster-whisper + edge-tts)

Benchmarks real neural TTS synthesis and CTranslate2 Whisper ASR across English, Hindi, and Tamil:

```bash
# Runs real edge-tts voices, Silero VAD, and faster-whisper INT8 transcription
python scripts/verify_real_speech.py
```

### Mode C: Live Footage Retrieval Verification (Pexels, Pixabay, Procedural Fallback)

Validates footage retrieval providers, FFprobe media integrity, and procedural fallback:

```bash
# Runs live provider tests if API keys are set, or validates procedural engine offline
python scripts/verify_real_footage.py
```

---

## 4. Supported Neural Voices (Multilingual)

| Language | Accent / Locale | Voice Identifier | Voice Character |
| :--- | :--- | :--- | :--- |
| **English** | Indian (`en-IN`) | `en-IN-female` (`en-IN-NeerjaNeural`) | Professional, modern Indian female |
| **English** | Indian (`en-IN`) | `en-IN-male` (`en-IN-PrabhatNeural`) | Warm, clear Indian male |
| **English** | United States (`en-US`) | `en-US-female` (`en-US-JennyNeural`) | Conversational US female |
| **English** | United States (`en-US`) | `en-US-male` (`en-US-GuyNeural`) | Confident US male |
| **Hindi** | India (`hi-IN`) | `hi-IN-female` (`hi-IN-SwaraNeural`) | Natural Hindi female narration |
| **Hindi** | India (`hi-IN`) | `hi-IN-male` (`hi-IN-MadhurNeural`) | Resonant Hindi male narration |
| **Tamil** | India (`ta-IN`) | `ta-IN-female` (`ta-IN-PallaviNeural`) | Authentic Tamil female narration |
| **Tamil** | India (`ta-IN`) | `ta-IN-male` (`ta-IN-ValluvarNeural`) | Expressive Tamil male narration |

---

## 5. Standard Error Codes Reference

All error responses strictly follow the RFC-compliant schema defined in Integration Standard Point 5:

```json
{
  "error": {
    "code": "UPPER_SNAKE_CASE",
    "message": "Human-readable description",
    "retryable": false,
    "details": {}
  }
}
```

| Error Code | HTTP Status | Retryable? | Description |
| :--- | :--- | :--- | :--- |
| `VALIDATION_ERROR` | `422` | No | Request payload failed schema validation. |
| `JOB_NOT_FOUND` | `404` | No | Requested `job_id` does not exist. |
| `AUDIO_FILE_NOT_FOUND` | `400` | No | Specified audio file path does not exist. |
| `UNSUPPORTED_AUDIO_FORMAT` | `400` | No | Input format is not `.mp3`, `.wav`, or `.m4a`. |
| `CORRUPTED_AUDIO_FILE` | `400` | No | Audio header or data could not be decoded. |
| `AUDIO_EXCEEDS_MAX_DURATION` | `400` | No | Audio duration exceeds 10 minutes (600s). |
| `AUDIO_TOO_SHORT` | `400` | No | Audio duration is shorter than 0.5s. |
| `NO_SPEECH_DETECTED` | `400` | No | Audio is silent or contains background music only. |
| `RATE_LIMITED` | `429` | Yes | Rate limit reached. |
| `SERVICE_UNAVAILABLE` | `503` | Yes | Database or storage readiness check failed. |
| `INTERNAL_SERVER_ERROR` | `500` | Yes | Unexpected internal error. |

---

## 6. Configuration Reference (`.env.example`)

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `ASR_PROVIDER` | `mock` / `faster-whisper` | Speech-to-text provider (`mock` for fast CI). |
| `TTS_PROVIDER` | `mock` / `edge-tts` | Text-to-speech provider (`mock` for fast CI). |
| `WHISPER_MODEL_SIZE` | `small` | Model size: `tiny`, `base`, `small`, `medium`. |
| `MAX_AUDIO_DURATION_SECONDS` | `600.0` | Maximum audio duration in seconds (10 min). |
| `DATABASE_URL` | `sqlite+aiosqlite:///data/jobs.db` | Job persistence database URL. |
| `S3_ENDPOINT_URL` | `http://localhost:9000` | MinIO / S3 endpoint URL. |
| `WEBHOOK_SECRET` | `default-test-...` | HMAC secret for `X-IncuBrix-Signature`. |
