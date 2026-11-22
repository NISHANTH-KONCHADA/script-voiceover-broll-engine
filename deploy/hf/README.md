---
title: IncuBrix B-roll Video Engine
emoji: 🎬
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# IncuBrix B-roll Video Engine — Live Demo

Script/Voiceover → B-roll video engine (IncuBrix Assessment 3 / PS3).

**API docs:** `/docs` (Swagger UI)

**Try it:** `POST /api/v1/broll/jobs` with `{"script": "Your narration text", "aspect_ratios": ["16:9"]}` — then poll `GET /api/v1/jobs/{job_id}` for progress and stream outputs via `GET /api/v1/jobs/{job_id}/video?aspect=16:9`.

Rate-limited to 30 job submissions/minute per IP. Full source: https://github.com/NISHANTH-KONCHADA/script-voiceover-broll-engine
