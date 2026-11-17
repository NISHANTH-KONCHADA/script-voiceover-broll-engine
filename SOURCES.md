# Sources, Dependencies & Licensing Disclosures

> **Assessment Title:** IncuBrix Engineering Assessment 3 (PS3) — Script to B-roll Video Engine  
> **Compliance Standard:** Commercial Use Clearances & Intellectual Property Rights  

Every model, API, library, dataset, and media source used in this project is disclosed below with its license and commercial-use verification.

---

## 1. Core Runtime Libraries (Phase 1)

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

## 2. Infrastructure & Storage Components

| Component | Image / Package | License | Compliance Strategy |
| :--- | :--- | :--- | :--- |
| **MinIO Server** | `minio/minio:latest` | GNU AGPLv3 | **Isolated Black-Box Container:** Runs as a separate microservice in `docker-compose.yml`. No application code links against or derives from MinIO. Communication occurs over standard S3 network protocol via Apache-2.0 `boto3`. |
| **MinIO Client** | `minio/mc:latest` | GNU AGPLv3 | One-off initialization container used strictly to provision the initial bucket. |

---

## 3. Reference Frameworks

| Project | Author | License | Usage in Project |
| :--- | :--- | :--- | :--- |
| **HyperFrames** | HeyGen, Inc. | Apache 2.0 | Architectural reference only. Inspected under `references/hyperframes/` for FFmpeg parameters, frame synchronization, and audio pad/trim algorithms. No source code copied into application. |
