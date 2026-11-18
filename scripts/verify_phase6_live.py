import asyncio
import json
import time
import httpx

async def main():
    async with httpx.AsyncClient(timeout=60.0) as client:
        # Submit job with all 3 aspect ratios, captions, and callback URL
        payload = {
            "script": "Artificial intelligence transforms modern clean energy grids, ensuring dependable renewable power for future generations.",
            "voice": "en-IN-female",
            "aspect_ratios": ["16:9", "9:16", "1:1"],
            "style": "cinematic, modern technology, solar panels, clean energy",
            "captions": {
                "burn_in": True,
                "font_size": 24,
                "font_color": "&H00FFFFFF",
                "highlight_color": "&H0000FFFF",
            },
            "callback_url": "https://httpbin.org/post",
            "webhook_secret": "incubrix_secret_key_demo_2027",
        }

        print("Submitting live Phase 6 job...")
        resp = await client.post("http://localhost:8000/api/v1/broll/jobs", json=payload)
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
        data = resp.json()
        job_id = data["job_id"]
        status_url = f"http://localhost:8000{data['check_status_url']}"
        print(f"Job created: {job_id}. Polling {status_url}...")

        # Poll status until finished
        for i in range(40):
            await asyncio.sleep(1.0)
            status_resp = await client.get(status_url)
            status_data = status_resp.json()
            status = status_data["status"]
            progress = status_data["progress"]
            stage = status_data["stage"]
            print(f"[{i+1}s] Status: {status} ({progress}%) - Stage: {stage}")
            if status in ("succeeded", "failed"):
                break

        print("\nFinal Job Detail Response:")
        print(json.dumps(status_data, indent=2))

        if status == "succeeded":
            outputs = status_data.get("outputs", {})
            print("\nOutputs:")
            print(f"  Videos: {list(outputs.get('videos', {}).keys())}")
            print(f"  Audio: {outputs.get('audio')}")
            print(f"  Transcript: {outputs.get('transcript')}")
            print(f"  Scenes: {outputs.get('scenes')}")
            print(f"  Captions: {outputs.get('captions')}")
            print(f"  Timeline: {outputs.get('timeline')}")
            print(f"  Manifest: {outputs.get('manifest')}")
            print(f"  Quality Report: {outputs.get('quality_report')}")

            # Fetch and inspect quality_report.json from storage
            if outputs.get("quality_report"):
                qr_url = outputs["quality_report"].replace("http://minio:9000", "http://localhost:9000")
                qr_resp = await client.get(qr_url)
                if qr_resp.is_success:
                    qr_data = qr_resp.json()
                    print("\n=== Quality Report Summary ===")
                    print(f"Overall Quality Score: {qr_data.get('overall_quality_score')}/100")
                    print(f"Passed: {qr_data.get('passed')}")
                    print(f"Failures: {qr_data.get('failures')}")
                    print(f"Warnings: {qr_data.get('warnings')}")
                    print("Objective Metrics:")
                    print(json.dumps(qr_data.get("objective_metrics", {}), indent=2))
                    print("Heuristic Metrics:")
                    print(json.dumps(qr_data.get("heuristic_metrics", {}), indent=2))
                    print("Saliency / Composition Reports:")
                    print(json.dumps(qr_data.get("saliency_reports", {}), indent=2))

            # Fetch and inspect manifest.json
            if outputs.get("manifest"):
                mf_url = outputs["manifest"].replace("http://minio:9000", "http://localhost:9000")
                mf_resp = await client.get(mf_url)
                if mf_resp.is_success:
                    mf_data = mf_resp.json()
                    print("\n=== Manifest Quality Assessment Section ===")
                    print(json.dumps(mf_data.get("quality_assessment", {}), indent=2))

if __name__ == "__main__":
    asyncio.run(main())
