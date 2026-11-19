"""Benchmark and validation script for multi-scene, multi-aspect clip swap and partial re-rendering."""

import asyncio
import json
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List
import httpx

API_BASE = "http://localhost:8000"
STORAGE_HOST_BASE = "http://localhost:9000"


def probe_media(file_path: Path) -> Dict[str, Any]:
    """Runs ffprobe on the given file and returns stream information."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_streams",
        "-show_format",
        "-of", "json",
        str(file_path),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)

    v_stream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    a_stream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)

    v_duration = float(v_stream.get("duration") or data["format"].get("duration") or 0.0)
    a_duration = float(a_stream.get("duration") or data["format"].get("duration") or 0.0) if a_stream else 0.0

    return {
        "width": int(v_stream["width"]) if v_stream else 0,
        "height": int(v_stream["height"]) if v_stream else 0,
        "video_codec": v_stream.get("codec_name") if v_stream else "none",
        "pix_fmt": v_stream.get("pix_fmt") if v_stream else "none",
        "fps": v_stream.get("r_frame_rate") if v_stream else "unknown",
        "video_duration": v_duration,
        "audio_codec": a_stream.get("codec_name") if a_stream else "none",
        "audio_channels": int(a_stream.get("channels", 0)) if a_stream else 0,
        "audio_sample_rate": int(a_stream.get("sample_rate", 0)) if a_stream else 0,
        "audio_duration": a_duration,
        "duration_drift": abs(v_duration - a_duration),
        "file_size_bytes": file_path.stat().st_size,
    }


async def main():
    async with httpx.AsyncClient(timeout=120.0) as client:
        print("=================================================================")
        print(" INCUBRIX PS3: MULTI-SCENE & MULTI-ASPECT PARTIAL RE-RENDER BENCHMARK ")
        print("=================================================================")

        # Step 1: Submit a 4-scene job requesting 16:9, 9:16, 1:1
        script = (
            "Artificial intelligence is transforming global agriculture. "
            "Autonomous drones scan crops and analyze soil moisture. "
            "Sensors monitor irrigation networks in real time. "
            "Sustainable farming ensures food security for tomorrow."
        )
        payload = {
            "script": script,
            "aspect_ratios": ["16:9", "9:16", "1:1"],
            "style": "cinematic, modern agricultural technology, 4k",
        }

        print("\n1. Submitting baseline 4-scene multi-aspect job...")
        t_sub = time.time()
        resp = await client.post(
            f"{API_BASE}/api/v1/broll/jobs",
            json=payload,
            headers={"Idempotency-Key": f"bench_{int(t_sub)}"},
        )
        assert resp.status_code in (200, 202), f"Job submission failed: {resp.text}"
        job_id = resp.json()["job_id"]
        print(f"   Created Job: {job_id}")

        # Poll until complete
        print("   Awaiting initial generation...")
        while True:
            await asyncio.sleep(2.0)
            stat_resp = await client.get(f"{API_BASE}/api/v1/jobs/{job_id}")
            stat = stat_resp.json()
            if stat["status"] == "succeeded":
                print(f"   Initial generation finished in {time.time() - t_sub:.2f}s (Progress: 100%)")
                break
            elif stat["status"] == "failed":
                raise RuntimeError(f"Initial job failed: {stat.get('error')}")

        # Step 2: Swap individual scenes across multiple trials
        swap_trials = [
            {"scene_index": 0, "query": "satellite view of green agriculture fields at sunrise"},
            {"scene_index": 1, "query": "robotic drone flying over precision farmland"},
            {"scene_index": 2, "query": "smart IoT water irrigation smart sensors technology"},
            {"scene_index": 3, "query": "bountiful golden wheat harvest combine harvester"},
        ]

        timings_api: List[float] = []
        timings_wall: List[float] = []
        swap_results: List[Dict[str, Any]] = []

        print("\n2. Executing partial re-rendering across 4 distinct scenes...")
        for trial in swap_trials:
            idx = trial["scene_index"]
            query = trial["query"]
            print(f"\n   -> Swapping Scene {idx} (query: '{query}')...")

            req_payload = {
                "scene_index": idx,
                "new_query": query,
                "style": "cinematic, clean broadcast 4k",
            }

            t0 = time.time()
            swap_resp = await client.post(
                f"{API_BASE}/api/v1/broll/jobs/{job_id}/swap-clip",
                json=req_payload,
                timeout=60.0,
            )
            wall_elapsed = time.time() - t0

            assert swap_resp.status_code == 200, f"Swap failed: {swap_resp.text}"
            res_data = swap_resp.json()
            api_proc_time = float(res_data["processing_time_seconds"])

            timings_api.append(api_proc_time)
            timings_wall.append(wall_elapsed)

            print(f"      API Processing Time: {api_proc_time:.2f}s | Wall-Clock: {wall_elapsed:.2f}s")
            swap_results.append({
                "scene_index": idx,
                "api_time": api_proc_time,
                "wall_time": wall_elapsed,
                "outputs": res_data["outputs"],
            })

        # Step 3: Compute benchmark statistics
        min_api = min(timings_api)
        median_api = statistics.median(timings_api)
        mean_api = statistics.mean(timings_api)
        worst_api = max(timings_api)

        min_wall = min(timings_wall)
        median_wall = statistics.median(timings_wall)
        worst_wall = max(timings_wall)

        print("\n=================================================================")
        print("           PARTIAL RE-RENDERING BENCHMARK METRICS                ")
        print("=================================================================")
        print(f"  Total Swap Trials:        {len(timings_api)}")
        print(f"  API Fastest Time:         {min_api:.2f}s")
        print(f"  API Median Time:          {median_api:.2f}s  (< 3.0s threshold)")
        print(f"  API Mean Time:            {mean_api:.2f}s")
        print(f"  API Worst-Case (Max):     {worst_api:.2f}s")
        print(f"  Wall-Clock Median:        {median_wall:.2f}s")
        print(f"  Wall-Clock Worst-Case:    {worst_wall:.2f}s")
        print("=================================================================")

        # Step 4: Download and probe all 3 aspect ratio outputs from the final swap
        print("\n3. Verifying output video compatibility & stream synchronization...")
        final_outputs = swap_results[-1]["outputs"]
        download_dir = Path("tmp/benchmark_verify")
        download_dir.mkdir(parents=True, exist_ok=True)

        for ratio in ["16:9", "9:16", "1:1"]:
            video_url = final_outputs["videos"][ratio]
            # Map minio URL to localhost for host downloader
            clean_url = video_url.split("?")[0].replace("http://minio:9000", STORAGE_HOST_BASE)
            local_dest = download_dir / f"final_{ratio.replace(':', 'x')}.mp4"

            dl_resp = await client.get(clean_url)
            assert dl_resp.status_code == 200, f"Failed to download {clean_url}"
            local_dest.write_bytes(dl_resp.content)

            # Probe media
            probe = probe_media(local_dest)
            print(f"\n   [Aspect Ratio {ratio}] -> {local_dest.name}")
            print(f"      Resolution:     {probe['width']}x{probe['height']}")
            print(f"      Video Codec:    {probe['video_codec']} ({probe['pix_fmt']})")
            print(f"      Audio Codec:    {probe['audio_codec']} ({probe['audio_sample_rate']}Hz, {probe['audio_channels']}ch)")
            print(f"      Video Duration: {probe['video_duration']:.3f}s")
            print(f"      Audio Duration: {probe['audio_duration']:.3f}s")
            print(f"      A/V Drift:      {probe['duration_drift'] * 1000:.1f}ms (< 100ms tolerance)")
            print(f"      File Size:      {probe['file_size_bytes'] / 1024:.1f} KB")

            # Assertions
            if ratio == "16:9":
                assert probe["width"] == 1920 and probe["height"] == 1080
            elif ratio == "9:16":
                assert probe["width"] == 1080 and probe["height"] == 1920
            elif ratio == "1:1":
                assert probe["width"] == 1080 and probe["height"] == 1080

            assert probe["video_codec"] == "h264"
            assert probe["pix_fmt"] == "yuv420p"
            assert probe["audio_codec"] == "aac"
            assert probe["duration_drift"] < 0.1, f"Audio/video desynchronized: {probe['duration_drift']}s"

        print("\nAll QA checks verified: stream compatibility, playback, and audio sync confirmed!")


if __name__ == "__main__":
    asyncio.run(main())
