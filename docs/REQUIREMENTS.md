# IncuBrix PS3 — Complete Assessment Requirements Checklist & Specification

> **Assessment Title:** Script and Voiceover to B-roll Video Engine (Assessment 3)  
> **Target Evaluation:** IncuBrix Engineering Assessment 2027  
> **Status:** Research & Architecture Phase  
> **Source Documents Analyzed:**  
> - `assessment/IncuBrix_Assessment_3_Script_to_Broll_Video_Engine_Brief.pdf` (7 pages)  
> - `assessment/IncuBrix_Assessment_3_Script_to_Broll_Video_Engine_Submission_Form.xlsx` (8 sheets)  

---

## 1. Executive Summary & Scoring Architecture

The goal of IncuBrix Assessment 3 (PS3) is to build an automated, containerized engine that takes either a script (text) or a recorded voiceover (audio) and turns it into a finished, commercially clean B-roll video. The video must have narration-driven timing, relevant footage for every sentence/phrase boundary, captions (SRT + optional burn-in), normalized aspect ratios (16:9, 9:16, 1:1), zero audio drift or frozen frames, complete provenance/attribution records, and follow strict enterprise integration standards.

### Scoring Breakdown (100 Marks Total)

| Evaluation Stage | Component | Marks | Pass / Cutoff Criteria |
| :--- | :--- | :--- | :--- |
| **Stage 1 & 2: Screening** | **Must-haves (8 criteria)** | **Pass / Fail** | **All 8 must pass.** A single failure results in immediate disqualification. |
| | **Capability Levels** | **40 Marks** | Core (15) + Advanced (15) + Outstanding (10). Cumulative; requires all previous levels. |
| | **Integration Standard** | **20 Marks** | 10 requirements @ 2 marks each (2 = Yes, 1 = Partial, 0 = No). |
| | **Hidden Tests** | **20 Marks** | 5 automated tests @ 4 marks each (4 = Correct, 2 = Flaw, 0 = Crash/Fail). |
| **Stage 3: Live Session** | **Live Engineering Interview** | **20 Marks** | 4 sections @ 5 marks each (Walkthrough, Predict & Run, Debugging, Live Change). |
| **Total** | | **100 Marks** | **Top Pick (Hire): 85+ & Outstanding verified & >=14 in live session.**<br>**Shortlist (Hire): 75+ & >=14 in live session.**<br>**Screening cutoff for live session: 60/80.** |

---

## 2. The 8 Must-Haves (Pass / Fail Checklist)

Every must-have is verified during screening. Missing evidence or non-compliance is an immediate rejection.

| # | Must-Have Title | Formal Requirement | Verification Method | Target Evidence Link |
| :- | :--- | :--- | :--- | :--- |
| **MH-1** | **Both Inputs Work** | Accept raw audio (`.mp3`, `.wav`, `.m4a`, up to 10 minutes) OR text script (generating narration via TTS). | Reviewers submit both audio and text jobs on the live demo. | `tests/test_inputs.py`, live demo URL, sample audio & text outputs in `outputs/` |
| **MH-2** | **Scenes by Meaning, Timed to Voice** | Scene boundaries fall on grammatical/semantic sentence or phrase boundaries. Every second of narration is covered by video (zero black frames). **Narration sets the timing, not the stock clips.** | Reviewers compare `timeline.json` timestamps against the audio transcript and inspect output videos. | `timeline.json`, `tests/test_scene_segmentation.py`, waveform alignment logs |
| **MH-3** | **Licence-Clean & Attributed Footage** | Every clip used must have its source, license type, author attribution, and direct source URL recorded in `timeline.json`. All media must permit commercial use. No watermarked footage. AI-generated clips must be explicitly flagged (`is_ai_generated: true`). | Reviewers inspect every scene entry in `timeline.json` and verify source URLs. | `timeline.json`, `SOURCES.md`, license validation tests |
| **MH-4** | **Correct, Consistent Video Rendering** | All requested aspect ratios rendered (`16:9`, `9:16`, `1:1`). Every clip normalized to standard resolution (1080p-class), constant 30 fps, and pixel format `yuv420p`. **No black frames, frozen frames, or audio drift.** | Automated ffprobe/ffmpeg inspection script run across every output file. | `tests/test_video_normalizer.py`, ffprobe logs, QC audit report |
| **MH-5** | **No Repeats & No Nonsense Matches** | **Zero duplicate clips** within a single video. Footage matches semantic context (e.g. "value" must not default to cash piles, "cloud computing" must not show clouds). | Reviewers watch all scenes and evaluate visual relevance on a 1–5 scale. | `tests/test_dedup.py`, deduplication hash logs, CLIP relevance scores |
| **MH-6** | **Safe Output Guardrails** | No AI-generated realistic faces of real people. No invented brand logos. Respectful, non-sensational footage for sensitive topics (e.g., tragedy, grief, medical news). | Tested with hard-case prompts containing named public figures, brands, and sensitive news. | `tests/test_safety_filters.py`, `timeline.json` safety flags, hard case outputs |
| **MH-7** | **Resilient Background Jobs** | Jobs run asynchronously in background with 0–100% progress. **Fault-tolerant retrieval:** if primary footage provider fails or rate-limits, system transparently fails over to secondary provider or procedural fallback. | Reviewers disable a footage API mid-job; verify the job still completes successfully. | `tests/test_resilience.py`, worker retry logs, fallback test run |
| **MH-8** | **Integration Standard Compliance & Uptime** | Complete compliance with all 10 points of the IncuBrix Integration Standard. Live demo must remain active and accessible throughout the entire review period. | Reviewers inspect endpoints, run automated contract tests, and monitor demo availability. | `openapi.yaml`, `/health`, `/ready`, live demo URL |

---

## 3. Capability Levels (40 Marks Breakdown)

Levels are strictly progressive: **Core is required (15 pts)**. Advanced (15 pts) requires all Core items. Outstanding (10 pts) requires all Advanced items.

```mermaid
flowchart LR
    MH[8 Must-Haves\nPass/Fail Gate] --> Core[Core Level\n15 Marks]
    Core --> Adv[Advanced Level\n+15 Marks = 30 Marks]
    Adv --> Out[Outstanding Level\n+10 Marks = 40 Marks]
```

### 3.1 Core Level (15 Marks)
*All items must be marked Yes and verified.*
1. **Must-Haves Verified:** All 8 must-haves pass without exception.
2. **10 Varied Test Inputs:** 10 diverse test inputs successfully generate high-quality videos:
   - Includes tutorials, news summaries, product promos, personal narratives.
   - Varied accents (Indian English, US English, British English).
   - Durations ranging from 20 seconds to 5 minutes.
3. **High Human Relevance:** Average relevance rating of **at least 3.5 out of 5** across all scenes in the 10 test videos as evaluated by IncuBrix reviewers.

### 3.2 Advanced Level (15 Marks)
*Requires Core. All 4 items must be verified.*
1. **Dual Footage Sources with Written Decision Rules:**
   - At least two footage sources integrated (e.g., Stock API like Pexels/Pixabay AND generative AI video / procedural graphics).
   - Clear, measurable rule engine deciding which source to query (e.g., abstract concepts, specific animations, fallback).
   - The exact reason for selecting each source recorded per scene in `timeline.json`.
2. **Clip Swapping with Partial Re-rendering:**
   - Endpoint/capability to replace a single clip in a finished video: `POST /api/v1/broll/jobs/{id}/swap-clip`.
   - Re-renders **only the affected scene** and re-muxes/re-assembles the final container, completing in **clearly less time than a full render**.
3. **Visual Cohesion & Pacing:**
   - Cross-clip visual normalization: automatic color and brightness grading (gamma/contrast alignment) across diverse sources.
   - Sensible pacing: minimum clip duration enforced (e.g. $\ge 1.5$–$2.0$ seconds) to avoid jarring 0.5-second rapid flashes.
4. **IncuBrix Scene List Input:**
   - API accepts pre-segmented IncuBrix scene lists: `scenes: [{"text": "...", "visual_hint": "..."}]`, honoring explicit director hints.

### 3.3 Outstanding Level (10 Marks)
*Requires Advanced. All 4 items must be verified.*
1. **Automated Vision-Language Model (VLM) Relevance Scoring:**
   - An independent vision-language model (e.g., CLIP / SigLIP or Gemini/GPT-4V) scores frame-to-narration semantic alignment.
   - Empirical validation showing statistical correlation (Pearson/Spearman $r$) between automated scores and human ratings.
2. **Multilingual Narration (Hindi & Tamil):**
   - Seamless end-to-end processing of Hindi (`hi-IN`) and Tamil (`ta-IN`) voiceovers and scripts alongside English.
   - Accurate multilingual speech recognition, script-to-speech generation, phonetic word alignment, and localized B-roll concept extraction.
3. **Rigorous Production Metrics:**
   - Detailed benchmarks on render turnaround time, cost per minute of finished video, GPU/CPU utilization, and maximum concurrent jobs per server instance.
4. **Outstanding Scene Relevance:**
   - **At least 85% of scenes** rated **4 or 5 out of 5** by reviewers.

---

## 4. Integration Standard (20 Marks — 10 Points @ 2 Marks Each)

The engine must plug directly into IncuBrix's microservices ecosystem over HTTP.

| # | Standard Point | Specification & Acceptance Test |
| :- | :--- | :--- |
| **1** | **One-command Start & Test** | `docker compose up` starts API, worker, database, and local MinIO storage. A single command (`pytest` or `docker compose run test`) executes unit, integration, and at least one end-to-end test **with zero external paid API keys required** (using mock adapters). `.env.example` documents all keys. |
| **2** | **Documented HTTP API** | Valid OpenAPI 3.1 specification (`openapi.yaml`) accurately reflecting all endpoints. All service routes prefixed with `/api/v1/`. |
| **3** | **Background Jobs Architecture** | Any request taking $>2$ seconds returns `HTTP 202 Accepted` with a unique `job_id`. `GET /api/v1/jobs/{job_id}` returns status (`queued`, `running`, `succeeded`, `failed`), `progress` (0–100), timestamps, and output links. Supports optional `callback_url`, signed with HMAC-SHA256 in the `X-IncuBrix-Signature` header. |
| **4** | **Safe Retries & Idempotency** | Requires an `Idempotency-Key` header on all job submission `POST` requests. Submitting an identical key returns the original `job_id` and does not duplicate compute or media downloads. |
| **5** | **Clear, Structured Errors** | All error responses return RFC-compliant JSON: `{"error": {"code": "UPPER_SNAKE_CASE", "message": "...", "retryable": boolean, "details": {...}}}`. Error codes documented in `README.md`. |
| **6** | **Zero Hard-Coded Config** | All configurations, file paths, model weights, timeouts, and API keys are injected via environment variables or configuration files. |
| **7** | **Files In, Files Out** | Accepts media inputs via direct multipart upload OR remote URL. All generated output files stored in S3-compatible object storage (MinIO for local dev/Docker) and exposed as downloadable pre-signed/direct links. |
| **8** | **Structured Logging & Health Checks** | Logs emitted in structured JSON format including ISO timestamp, log level, `job_id`, and `X-Correlation-Id`. Health check endpoints provided: `GET /health` (liveness) and `GET /ready` (readiness check of dependencies). |
| **9** | **Comprehensive Output Manifest** | Every completed job outputs `manifest.json` detailing: engine version, models used, settings, random seed, execution timings per stage, estimated processing cost, warnings, and rights/licensing summary. |
| **10**| **CLI Batch Runner** | Standalone CLI script (`python -m engine.batch_runner` or `bin/batch-run`) that accepts a directory or manifest of test inputs, triggers jobs against the API, polls for completion, and writes all outputs to a specified folder. |

---

## 5. Required Input / Output Specifications

### 5.1 API Request Schema (`POST /api/v1/broll/jobs`)

```json
{
  "audio_url": "https://storage.example.com/voiceover.mp3", // OR "script": "..." OR "scenes": [...]
  "script": null,
  "scenes": null, // Optional IncuBrix scene list: [{"text": "...", "visual_hint": "..."}]
  "voice": "en-IN-female", // Used only when generating narration from text
  "aspect_ratios": ["16:9", "9:16"], // Any combination of "16:9", "9:16", "1:1"
  "style": "bright, modern, real-world footage",
  "avoid": ["people's faces", "alcohol"], // Negative content constraints
  "captions": {
    "burn_in": true,
    "srt": true
  }
}
```

### 5.2 Output Artifacts Bundle

For each job execution, the engine must produce:

1. **`video_{ratio}.mp4`** (e.g. `video_16x9.mp4`, `video_9x16.mp4`, `video_1x1.mp4`):
   - Codec: H.264 (High Profile, Level 4.1 or 4.2).
   - Audio: AAC-LC, stereo, 48 kHz, $\ge 192\text{ kbps}$, normalized to $-16\text{ to }-14\text{ LUFS}$.
   - Framerate: Constant 30 fps (`-fps_mode cfr` or `-r 30`).
   - Resolution: 1080p class (`1920x1080` for 16:9, `1080x1920` for 9:16, `1080x1080` for 1:1).
   - Pixel Format: `yuv420p`.
   - Structure: Web-optimized with `moov` atom at front (`+faststart`).
   - Timing: 100% narration coverage, zero black/frozen frames, zero audio-video drift.
2. **`captions.srt`**:
   - Standard SubRip format with frame-accurate timestamps matching the narration speech boundaries.
3. **`timeline.json`**:
   - Detailed array of scenes:
     ```json
     [
       {
         "scene_index": 0,
         "text": "Starting a business requires resilience and clear vision.",
         "start_time": 0.0,
         "end_time": 3.42,
         "duration": 3.42,
         "clip": {
           "clip_id": "px-1082910",
           "source": "pexels",
           "url": "https://www.pexels.com/video/1082910/",
           "download_url": "https://videos.pexels.com/video-files/1082910/1082910-hd_1920_1080_30fps.mp4",
           "license": "Pexels License (Commercial Use Allowed)",
           "attribution": "Video by Cottonbro Studio via Pexels",
           "is_ai_generated": false
         },
         "selection_reason": "High semantic score for entrepreneurial persistence; clear office setting.",
         "relevance_score": 4.6,
         "vlm_score": 4.5
       }
     ]
     ```
4. **`manifest.json`**:
   - Engine provenance record detailing system configuration, model identifiers, execution breakdown, costs, and warnings:
     ```json
     {
       "job_id": "broll_c8f2a1b9",
       "created_at": "2026-11-18T10:00:00Z",
       "completed_at": "2026-11-18T10:01:15Z",
       "settings": {
         "aspect_ratios": ["16:9", "9:16"],
         "voice": "en-IN-female",
         "style": "bright, modern, real-world footage",
         "avoid": ["people's faces", "alcohol"],
         "captions": {"burn_in": true, "srt": true}
       },
       "models_and_providers": {
         "asr": {"provider": "faster-whisper", "model": "medium"},
         "tts": {"provider": "edge-tts", "voice": "en-IN-NeerjaNeural"},
         "footage": ["pexels", "pixabay", "procedural_fallback"],
         "vlm_evaluator": {"provider": "siglip-base-patch16-384"}
       },
       "timings_ms": {
         "transcription_or_tts": 3200,
         "scene_segmentation": 850,
         "broll_retrieval_and_ranking": 5400,
         "media_normalization": 8100,
         "video_composition": 12400,
         "total": 29950
       },
       "cost_estimate_usd": {
         "footage_api": 0.0,
         "tts": 0.0,
         "compute": 0.012,
         "total": 0.012
       },
       "warnings": [],
       "licensing_summary": {
         "all_commercial_cleared": true,
         "watermarked_clips_detected": 0,
         "ai_generated_clips_count": 0
       }
     }
     ```

---

## 6. Hard Cases to Test & Handle (Workbook Sheet 6)

Reviewers will submit 5 hidden test cases based on these scenarios:

| # | Hard Case Situation | Expected System Behavior | Fallback / Safeguard Strategy |
| :- | :--- | :--- | :--- |
| **HC-1** | **Abstract lines ("trust is earned slowly") & numbers/statistics ("sales grew 40% in 2025")** | System does not perform literal naive keyword search (which fails). It extracts conceptual visual metaphors (e.g. handshake, bridge building, rising charts, financial trading screens). | Dual prompt expansion: literal entity extraction vs metaphor extraction. |
| **HC-2** | **Named real person or brand in narration** (e.g. "Elon Musk", "Nike") | Safety filter triggers: **Never** generate realistic AI faces of real people; **Never** invent brand logos. Choose generic metaphorical footage (e.g. electric vehicles, athletic running shoes). | Named Entity Recognition (NER) lookup against celebrity/brand blacklist; flag scene in `timeline.json`. |
| **HC-3** | **Words with double meanings** ("value", "bank", "cloud", "mouse", "python") | Disambiguate based on full sentence context (e.g. "cloud computing" $\rightarrow$ server racks/data center, NOT sky clouds; "python script" $\rightarrow$ code editor, NOT snake). | Context-aware LLM query generation and semantic vector reranking. |
| **HC-4** | **Sad or sensitive news story** (accidents, grief, poverty, natural disasters) | Detect emotional tone/sentiment. Avoid upbeat, comedic, or wildly inappropriate stock clips. Select muted, solemn, documentary-style footage. | Sentiment / safety classifier flags `sensitive_content: true`; activates solemn style profile. |
| **HC-5** | **9:16 vertical crop with subject at edge of 16:9 clip** | Naive center-crop cuts off the subject. System performs smart cropping: detects region of interest (visual saliency or face/body bounding box) and pans crop window or applies blurred letterbox padding. | Saliency detection or smart crop filter in ffmpeg pipeline. |
| **HC-6** | **Edge-case audio/script:** 5-minute voiceover; silent audio; music-only; wrong file type; empty script | Validate inputs before processing. Reject invalid types with clear structured errors. Detect silent or music-only audio and raise `NO_SPEECH_DETECTED`. Handle 5-min voiceover efficiently without memory spikes. | Input preflight validation; RMS volume & voice activity detection (VAD). |
| **HC-7** | **Infrastructure failure:** Provider down/empty; corrupted download; concurrent submissions | Transparent failover: if primary stock API returns 429/500 or 0 results, fall back to secondary stock source or local procedural assets. Handle concurrency via worker queue with isolated scratch directories. | Tenacity retries, multi-provider cascade, isolated worker temp dirs. |

---

## 7. Submission Deliverables & Required Files

| File Name | Mandatory Contents | Verified In Sheet |
| :--- | :--- | :--- |
| **`Assessment3_YourName.xlsx`** | Completed Excel workbook: details, all 8 must-haves, levels, 10 integration points, measured metrics, hard cases, and signed declaration. | All Sheets |
| **`README.md`** | System overview, architecture diagram, $<10$ command setup guide, test execution commands, batch runner usage, configuration reference, error codes table. | Sheet 1, Sheet 4 |
| **`openapi.yaml`** | OpenAPI 3.1 specification matching the running service routes. | Sheet 4 (Point 2) |
| **`REPORT.md`** | 2–4 pages: design alternatives considered & trade-offs, what works, what failed, measured benchmarks, cost breakdown, future roadmap. | Sheet 1 |
| **`SOURCES.md`** | Comprehensive disclosure of all models, APIs, libraries, datasets, and media sources used (with commercial license verifications). | Sheet 1, Sheet 7 |
| **`AI_USE.md`** | Disclosure of all AI coding assistants, models used during development, and what code they contributed to. | Sheet 1, Sheet 7 |
| **`Test Pack & Video Pack`** | All test inputs, generated videos (`16:9`, `9:16`, `1:1`), `timeline.json`, `captions.srt`, `manifest.json`, logs, and benchmark test records. | Sheet 1, Sheet 5, Sheet 6 |
| **`Demo Video`** | Unedited screen recording ($\le 8\text{ minutes}$): clean run, failure handling demonstration, test suite execution, code walkthrough. | Sheet 1 |
| **Live Demo URL** | Publicly accessible URL with API docs or web interface, with rate limiting and stated cold-start time. | Sheet 1 |

---

## 8. Requirements Traceability Matrix (Workbook to Brief)

| Workbook Sheet | Section | PDF Brief Section | Key Obligations |
| :--- | :--- | :--- | :--- |
| `0_Start_Here` | Instructions & Summary | At a glance, How you are selected | Understand 80-mark screening & 20-mark live session cutoffs. |
| `1_Your_Details` | Contact & Submission Links | What to send us (p. 6) | Provide demo URL, repo link, report link, compute specs, hours spent. |
| `2_Must_haves` | Must-haves #1 to #8 | Must-haves (p. 2) | All 8 pass/fail requirements must have working links to evidence. |
| `3_Levels` | Core, Advanced, Outstanding | Levels (p. 3), Marks (p. 5) | Core (15 pts), Advanced (15 pts), Outstanding (10 pts). Formula checks prior levels. |
| `4_Integration` | 10 Integration Standard points | Integration Standard (p. 3–4) | Docker compose, OpenAPI 3.1, background jobs, idempotency, structured logs, MinIO. |
| `5_Metrics` | Measured Numbers | Numbers you must report (p. 5) | Turnaround (s), Cost ($/min), Coverage (%), Relevance (1-5), Reliability (%), Resources. |
| `6_Hard_cases` | 7 Edge Case Scenarios | Hard cases we will test (p. 3) | Document system behavior and link test outputs for all 7 hard cases. |
| `7_Declaration` | Legal & Ethics Statements | Rules, rights and using your work (p. 7) | Confirm commercial clean rights, individual authorship, no deepfakes, no hard-coded secrets. |
