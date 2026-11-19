"""CLI Batch Runner for IncuBrix Script-to-B-roll Engine (Integration Standard Point 10).

Accepts a directory or manifest of test inputs, triggers jobs against the API,
polls for completion, and writes all outputs to a specified folder.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import httpx


class BatchRunnerError(Exception):
    """Raised on batch execution failures."""
    pass


class BatchRunner:
    """Manages concurrent execution of B-roll generation jobs from batch input directory."""

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        concurrency: int = 2,
        poll_interval: float = 2.0,
        job_timeout: float = 180.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.job_timeout = job_timeout

    async def check_api_health(self, client: httpx.AsyncClient) -> bool:
        """Verifies API liveness and readiness before starting batch."""
        try:
            resp = await client.get(f"{self.api_url}/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def submit_and_await_job(
        self,
        client: httpx.AsyncClient,
        payload: Dict[str, Any],
        item_name: str,
        output_dir: Path,
    ) -> Dict[str, Any]:
        """Submits a single job with Idempotency-Key, polls until done, and downloads artifacts."""
        idempotency_key = f"batch_{item_name}_{int(time.time() * 1000)}"
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "X-Correlation-Id": f"corr_batch_{item_name}",
        }

        start_time = time.time()
        print(f"[{item_name}] Submitting job to {self.api_url}/api/v1/broll/jobs...")
        sub_resp = await client.post(
            f"{self.api_url}/api/v1/broll/jobs",
            json=payload,
            headers=headers,
            timeout=30.0,
        )

        if sub_resp.status_code not in (200, 202):
            raise BatchRunnerError(f"Job submission failed: HTTP {sub_resp.status_code}: {sub_resp.text}")

        sub_data = sub_resp.json()
        job_id = sub_data["job_id"]
        status_url = f"{self.api_url}/api/v1/jobs/{job_id}"
        print(f"[{item_name}] Enqueued job {job_id}. Polling status...")

        # Poll status
        final_job: Optional[Dict[str, Any]] = None
        while time.time() - start_time < self.job_timeout:
            await asyncio.sleep(self.poll_interval)
            stat_resp = await client.get(status_url, timeout=15.0)
            if stat_resp.status_code != 200:
                continue
            job_info = stat_resp.json()
            status = job_info["status"]
            progress = job_info["progress"]
            stage = job_info["stage"]
            print(f"[{item_name} | {job_id}] {status.upper()} ({progress}%) - {stage}")

            if status in ("succeeded", "failed"):
                final_job = job_info
                break

        if not final_job:
            raise BatchRunnerError(f"Job {job_id} timed out after {self.job_timeout} seconds.")

        elapsed = round(time.time() - start_time, 2)
        if final_job["status"] != "succeeded":
            err = final_job.get("error", {})
            return {
                "item_name": item_name,
                "job_id": job_id,
                "status": "failed",
                "elapsed_seconds": elapsed,
                "error": err,
            }

        # Download outputs into output_dir / item_name /
        item_out_dir = output_dir / item_name
        item_out_dir.mkdir(parents=True, exist_ok=True)
        outputs = final_job.get("outputs") or {}
        downloaded_files: Dict[str, str] = {}

        # 1. Download videos
        videos = outputs.get("videos", {})
        for ratio, url in videos.items():
            safe_ratio = ratio.replace(":", "x")
            dest = item_out_dir / f"video_{safe_ratio}.mp4"
            await self._download_file(client, url, dest)
            downloaded_files[f"video_{safe_ratio}"] = str(dest)

        # 2. Download metadata artifacts
        for artifact_key in ("captions", "timeline", "manifest", "quality_report", "transcript"):
            url = outputs.get(artifact_key)
            if url:
                ext = ".srt" if artifact_key == "captions" else ".json"
                dest = item_out_dir / f"{artifact_key}{ext}"
                await self._download_file(client, url, dest)
                downloaded_files[artifact_key] = str(dest)

        return {
            "item_name": item_name,
            "job_id": job_id,
            "status": "succeeded",
            "elapsed_seconds": elapsed,
            "downloaded_files": downloaded_files,
        }

    async def _download_file(self, client: httpx.AsyncClient, url: str, dest_path: Path) -> None:
        """Downloads a remote or presigned storage URL to disk."""
        # Replace minio:9000 with localhost:9000 if running on host Windows
        effective_url = url
        if "minio:9000" in url and os.name == "nt":
            # Strip signed query parameters to allow direct read if host header differs
            clean_url = url.split("?")[0]
            effective_url = clean_url.replace("http://minio:9000", "http://localhost:9000")

        try:
            resp = await client.get(effective_url, timeout=45.0)
            if resp.is_success:
                dest_path.write_bytes(resp.content)
            else:
                # Retry with stripped params or localhost
                alt_url = url.split("?")[0].replace("http://minio:9000", "http://localhost:9000")
                alt_resp = await client.get(alt_url, timeout=45.0)
                if alt_resp.is_success:
                    dest_path.write_bytes(alt_resp.content)
        except Exception as e:
            print(f"Warning: could not download {url}: {e}")

    async def run_batch(
        self,
        input_dir: Path,
        output_dir: Path,
        aspect_ratios: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Processes all input files in input_dir concurrently up to self.concurrency."""
        target_ratios = aspect_ratios or ["16:9", "9:16", "1:1"]
        output_dir.mkdir(parents=True, exist_ok=True)
        items: List[tuple[str, Dict[str, Any]]] = []

        for p in sorted(input_dir.iterdir()):
            if p.is_file():
                if p.suffix.lower() == ".txt":
                    script_text = p.read_text(encoding="utf-8").strip()
                    if script_text:
                        items.append((p.stem, {
                            "script": script_text,
                            "aspect_ratios": target_ratios,
                            "style": "cinematic, modern, clean footage",
                        }))
                elif p.suffix.lower() == ".json":
                    try:
                        data = json.loads(p.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            if "aspect_ratios" not in data:
                                data["aspect_ratios"] = target_ratios
                            items.append((p.stem, data))
                    except Exception as e:
                        print(f"Skipping invalid JSON file {p}: {e}")
                elif p.suffix.lower() in (".mp3", ".wav", ".m4a"):
                    # Local audio file path
                    items.append((p.stem, {
                        "audio_url": str(p.resolve()),
                        "aspect_ratios": target_ratios,
                        "style": "clean b-roll footage",
                    }))

        if not items:
            print(f"No valid input files found in {input_dir}.")
            return []

        print(f"Found {len(items)} batch items to process with concurrency={self.concurrency}.")

        sem = asyncio.Semaphore(self.concurrency)
        results: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=60.0) as client:
            if not await self.check_api_health(client):
                raise BatchRunnerError(f"API at {self.api_url} is not healthy or unreachable.")

            async def worker(item_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
                async with sem:
                    return await self.submit_and_await_job(client, payload, item_name, output_dir)

            tasks = [worker(name, payload) for name, payload in items]
            results = await asyncio.gather(*tasks, return_exceptions=False)

        # Save summary report
        summary_path = output_dir / "batch_summary.json"
        summary_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_items": len(results),
            "successful_items": sum(1 for r in results if r.get("status") == "succeeded"),
            "failed_items": sum(1 for r in results if r.get("status") == "failed"),
            "results": results,
        }
        summary_path.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")
        print(f"\nBatch completed. Summary saved to {summary_path}")
        return results


def main() -> None:
    parser = argparse.ArgumentParser(description="IncuBrix B-roll Engine CLI Batch Runner (Integration Standard 10)")
    parser.add_argument("--input-dir", required=True, type=Path, help="Directory containing scripts or audio files")
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to save downloaded outputs")
    parser.add_argument("--api-url", default="http://localhost:8000", help="Base URL of B-roll engine API")
    parser.add_argument("--concurrency", type=int, default=2, help="Max concurrent jobs")
    parser.add_argument("--timeout", type=float, default=180.0, help="Per-job timeout in seconds")
    parser.add_argument(
        "--aspect-ratios",
        nargs="+",
        default=["16:9", "9:16", "1:1"],
        help="Target aspect ratios to request and download (default: 16:9 9:16 1:1)",
    )

    args = parser.parse_args()

    runner = BatchRunner(
        api_url=args.api_url,
        concurrency=args.concurrency,
        job_timeout=args.timeout,
    )

    try:
        results = asyncio.run(
            runner.run_batch(
                input_dir=args.input_dir,
                output_dir=args.output_dir,
                aspect_ratios=args.aspect_ratios,
            )
        )
        failures = [r for r in results if r.get("status") != "succeeded"]
        if failures:
            print(f"Batch completed with {len(failures)} failures.")
            sys.exit(1)
        print("All batch jobs completed successfully!")
        sys.exit(0)
    except Exception as e:
        print(f"Batch runner error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
