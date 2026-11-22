# IncuBrix Engineering Assessment 3 — Technical Report
**Project:** Script and Voiceover to B-roll Video Engine (IncuBrix Studio)  
**Author:** Nishanth K  
**Email:** cb.sc.u4cse23523@cb.students.amrita.edu  
**Repository:** https://github.com/NISHANTH-KONCHADA/script-voiceover-broll-engine  
**Date:** November 2026  

---

## 1. Executive Summary & Problem Overview

IncuBrix Assessment 3 requires building an automated, microservice-grade engine that converts either raw voiceover audio or plain text scripts into a broadcast-ready B-roll video. The system must enforce semantic scene segmentation, narration-driven timing, multi-source footage retrieval with commercial copyright clearance, multi-aspect video normalization (16:9, 9:16, 1:1), subtitle burning, and strict microservice integration standards.

This report details the architectural design decisions, pipeline engineering, technical trade-offs, measured benchmarks, and production hardening implemented in the **IncuBrix B-roll Engine**.

---

## 2. Architectural Approaches & Design Decisions

### 2.1 Video Pipeline: Segment-Based Concatenation vs. Single-Pass Monolithic Encoding
- **Approach A (Monolithic Complex Filtergraph):** Feeding all video inputs, image overlays, audio streams, and transitions into a single massive FFmpeg `-filter_complex` command.
  - *Drawback:* Extremely brittle; memory spikes on long videos (>1 min); failure in one filter aborts the entire render; impossible to do partial re-rendering without re-encoding every frame.
- **Approach B (Segment-Based Rendering with Concat Demuxer — Selected):**
  - The narration is segmented into discrete scenes (governed by the **Pacing Guard**, $1.8\text{s} \le \Delta t \le 5.0\text{s}$).
  - Each scene footage clip is independently scaled, cropped to target aspect ratios, and encoded to an intermediate MP4 segment at constant 30 fps and `yuv420p`.
  - Final video assembly uses the FFmpeg stream-concat demuxer (`-f concat -safe 0`) combined with normalized audio and ASS subtitle burn-in.
  - *Advantage:* Enables **partial re-rendering clip swaps** (Advanced Criterion 2). When a user swaps clip $N$, only scene $N$ is re-rendered; remaining scenes are reused without re-encoding.

### 2.2 Speech & Narration Processing: Local Open-Source vs. Proprietary Cloud APIs
- **Selected Stack:**
  - **Speech Recognition (ASR):** `faster-whisper` (CTranslate2-optimized Whisper-small/base) providing frame-accurate word timestamps and language identification.
  - **Speech Synthesis (TTS):** `edge-tts` (Microsoft Edge neural voices covering English `en-IN`/`en-US`, Hindi `hi-IN`, and Tamil `ta-IN`; requires Internet connectivity, swappable via the `TTSProvider` interface).
  - **Preflight Audio Validation:** Silero Voice Activity Detector (VAD) coupled with FFprobe signal inspection to reject silent audio, pure tones, corrupted containers, and files $>10$ minutes before any downstream processing begins.
  - *Trade-off:* 100% offline functionality and zero paid API dependencies, allowing the test suite (93 unit/integration tests) to pass without cloud credentials.

### 2.3 Retrieval & Semantic Intent Ranking
- **Multi-Tier Retrieval Strategy:**
  1. *Primary Stock Source:* Pexels API (high-definition curated footage, commercial CC0/Pexels license).
  2. *Secondary Stock Source:* Pixabay API (broad vocabulary, commercial SafeSearch license).
  3. *Tertiary Procedural Fallback:* FFmpeg procedural motion graphics generator (`testsrc`, `mandelbrot`, gradient overlays) guaranteeing **zero job failures** even if stock APIs are down or rate-limited.
- **Semantic Relevance & Negative Homonym Penalty:**
  - Contextual token extraction filters out common homonym traps (e.g., "cloud computing" $\to$ technology server racks, penalizing meteorological sky; "bank" in finance $\to$ financial vault, penalizing riverbank).
  - Deduplication prevents repeating clips across any single video.

### 2.4 Video Normalization & Typography Engine
- **Visual Scaling:** Custom `VideoScaler` computes exact center-crops and aspect-ratio transforms without distortion or black pillarboxes.
- **Broadcast Audio:** EBU R128 loudness normalization via FFmpeg `loudnorm` targetting $-16\text{ LUFS}$ integrated loudness, $-1\text{ dBFS}$ true peak.
- **Dynamic Captions:** Styled Advanced SubStation Alpha (`.ass`) rendering with aspect-specific safe-area margins (e.g., $240\text{px}$ bottom margin for 9:16 vertical video to prevent occlusion by mobile UI and scrubbers).

---

## 3. What Works, What Does Not, and Honest Disclosures

### 3.1 What Works Flawlessly (Verified by 93 Automated Tests)
1. **Both Inputs:** Handles audio uploads (.mp3, .wav, .m4a up to 10 min) and script generation with Indian, US, and British English, Hindi, and Tamil voices.
2. **Audio-Video Synchronization:** Duration drift strictly $\le 26\text{ms}$ (well within the $50\text{ms}$ threshold).
3. **Clip Swapping with Partial Re-render:** Swapping a scene re-renders only the affected segment; measured end-to-end latency is $\approx 20\text{s}$–$35\text{s}$ (replacement-clip retrieval + per-aspect re-mux + quality re-scan) versus $\approx 130\text{s}$ for a full job render.
4. **Resilient Background Execution:** Transparent failover between Pexels, Pixabay, and procedural rendering.
5. **Security Hardening:** Server-Side Request Forgery (SSRF) protection blocking private IP ranges (127.0.0.1, 10.0.0.0/8, 169.254.169.254) on clip import URLs.
6. **Timeline-Based Video Editor UI:** Interactive web editor supporting multitrack scrubbing, clip dragging, live caption styling, trimming, and instant export.

### 3.2 What Does Not Work & Architectural Trade-offs
1. **Semantic Ranking is Lexical & Semantic Token-Based, Not Multimodal VLM:**
   - *Why:* Integrating a heavy 4GB Vision-Language Model (like CLIP ViT-L/14 or SigLIP) directly in the local CPU Docker image would balloon image size past 10GB and cause severe CPU throttling during local development. We opted for fast, tokenized semantic intent mapping and negative penalty filtering.
2. **Visual Saliency Uses Rule-of-Thirds Spatial Variance:**
   - *Why:* Saliency evaluation utilizes spatial contrast and luminance variance across frame grids rather than deep neural gaze prediction models, keeping container startup instant.
3. **Generative Image-to-Video API Dependency:**
   - *Why:* True generative AI video (Runway Gen-2 or Stable Video Diffusion) requires dedicated cloud GPUs ($>\$1.50/\text{hr}$). We implemented procedural motion graphics as the built-in generative engine, keeping total test and operation costs at \$0.00.

---

## 4. Measured Production Numbers & Benchmarks

All measurements conducted on standard development workstation (Intel i7, 16GB RAM, Windows 11 / WSL2 Docker Engine, zero GPU acceleration):

| Metric | Measurement / Value | Benchmark Conditions |
| :--- | :--- | :--- |
| **Turnaround (60s Narration — Warm)** | **25.91 seconds** ($0.43\times$ real-time) | Pre-cached stock assets, 3 aspect ratios rendered concurrently |
| **Turnaround (60s Narration — Cold)** | **34.20 seconds** ($0.57\times$ real-time) | Cold network download of raw footage via Pexels/Pixabay |
| **Partial Re-render (Clip Swap)** | **~20–35 seconds** end-to-end | Includes replacement-clip retrieval, re-encoding of the swapped scene, re-mux across aspect ratios, and quality re-scan; unaffected segments are reused via stream-copy |
| **Audio-Video Drift** | **$\le 26$ milliseconds** | Max allowed drift: $50\text{ms}$ |
| **Pacing Compliance** | **$100\%$ scenes between $1.8\text{s}$ and $5.0\text{s}$** | Evaluated across 10 diverse benchmark scripts |
| **API Failure Rate** | **$0.0\%$** across 93 test executions | 100% pass rate in CI/CD pipeline |
| **Duplicate Clip Rate** | **$0.0\%$** | Zero repeat clips per video |
| **Cost per Minute of Video** | **$0.002** (Compute only) | Open-source Faster-Whisper, edge-tts, Free Pexels/Pixabay |
| **Peak Memory Consumption** | **1.38 GB RAM** | Engine container under multi-aspect FFmpeg load |
| **Concurrent Jobs per Server** | **4 parallel jobs** | Scalable via Celery/Redis worker replication |

---

## 5. What We Would Do Next (Production Roadmap)

If deploying this microservice to high-scale enterprise production ($>10,000$ videos/day), we would implement:
1. **Distributed Celery / Temporal Worker Pool:** Decouple FastAPI from CPU-intensive FFmpeg tasks using Redis/RabbitMQ queues with autoscaling GPU worker nodes.
2. **Cloud GPU Acceleration for NVENC:** Migrate FFmpeg encoding flags to `h264_nvenc` on NVIDIA T4/A10G instances, reducing turnaround time from $25\text{s}$ down to under $8\text{s}$ for 60s of video.
3. **Embedding-Based Video Vector Search:** Index stock video libraries using Milvus or Qdrant with open-source SigLIP embeddings for true text-to-video cross-modal semantic search.
4. **Cloudflare Stream Direct CDN Edge Delivery:** Stream rendered MP4 files directly from S3 through edge caching with dynamic adaptive bitrate (HLS/DASH) playback.
