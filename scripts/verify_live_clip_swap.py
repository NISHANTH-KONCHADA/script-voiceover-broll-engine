"""Live demonstration and verification of partial re-rendering clip swap (Advanced Criterion 2)."""

import asyncio
import json
import time
import httpx

async def main():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # First check status of existing completed job
        job_id = "broll_2706d2ae613d"
        resp = await client.get(f"http://localhost:8000/api/v1/jobs/{job_id}")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        job_data = resp.json()
        print(f"Target Job: {job_id} (Status: {job_data['status']}, Progress: {job_data['progress']}%)")

        # Execute clip swap for scene 0
        swap_payload = {
            "scene_index": 0,
            "new_query": "futuristic solar panel farm clean energy infrastructure",
            "style": "cinematic, high tech, bright",
        }

        print(f"\nCalling POST /api/v1/broll/jobs/{job_id}/swap-clip...")
        t0 = time.time()
        swap_resp = await client.post(
            f"http://localhost:8000/api/v1/broll/jobs/{job_id}/swap-clip",
            json=swap_payload,
            timeout=30.0,
        )
        elapsed = time.time() - t0

        print(f"Swap response HTTP status: {swap_resp.status_code} in {elapsed:.2f} seconds")
        assert swap_resp.status_code == 200, f"Swap failed: {swap_resp.text}"

        swap_data = swap_resp.json()
        print("\n=======================================================")
        print("         PARTIAL RE-RENDERING CLIP SWAP REPORT         ")
        print("=======================================================")
        print(f"Job ID:                 {swap_data.get('job_id')}")
        print(f"Status:                 {swap_data.get('status')}")
        print(f"Replaced Scene Index:   {swap_data.get('scene_index')}")
        print(f"Re-rendered Scene ID:   {swap_data.get('re_rendered_scene_id')}")
        print(f"Previous Clip Asset ID: {swap_data.get('previous_clip_id')}")
        print(f"New Clip Asset ID:      {swap_data.get('new_clip_id')}")
        print(f"Processing Time (API):  {swap_data.get('processing_time_seconds')}s (Target: <3.0s)")
        print(f"Wall-Clock Elapsed:     {elapsed:.2f}s")
        print(f"Message:                {swap_data.get('message')}")
        print("\nUpdated Outputs:")
        print(json.dumps(swap_data.get("outputs", {}), indent=2))
        print("=======================================================")

        # Fetch and verify updated timeline
        timeline_url = swap_data["outputs"]["timeline"].split("?")[0].replace("http://minio:9000", "http://localhost:9000")
        tl_resp = await client.get(timeline_url)
        if tl_resp.is_success:
            tl_items = tl_resp.json()
            swapped_scene = tl_items[0]
            print("\nUpdated Timeline for Scene 0:")
            print(f"  Clip ID: {swapped_scene['clip']['clip_id']}")
            print(f"  Source:  {swapped_scene['clip']['source']}")
            print(f"  Reason:  {swapped_scene['selection_reason']}")

if __name__ == "__main__":
    asyncio.run(main())
