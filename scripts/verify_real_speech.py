import asyncio
import os
import sys
import time
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from broll_engine.speech.asr.whisper import FasterWhisperASRProvider
from broll_engine.speech.tts.edge import EdgeTTSProvider


async def run_verification():
    print("=================================================================")
    print("IncuBrix B-roll Engine - Real Model Verification (ASR & TTS)")
    print("=================================================================\n")

    tts = EdgeTTSProvider()
    asr = FasterWhisperASRProvider(model_size="tiny", device="cpu", compute_type="int8")

    test_cases = [
        {
            "lang": "en",
            "voice": "en-IN-female",
            "text": "Artificial intelligence is transforming how creators produce video content across the globe.",
            "label": "Indian English (en-IN)",
        },
        {
            "lang": "en",
            "voice": "en-US-female",
            "text": "Welcome to the IncuBrix script and voiceover automated video creation engine.",
            "label": "US English (en-US)",
        },
        {
            "lang": "hi",
            "voice": "hi-IN-female",
            "text": "तकनीक और नवाचार हमारे काम करने के तरीके को बदल रहे हैं।",
            "label": "Hindi (hi-IN)",
        },
        {
            "lang": "ta",
            "voice": "ta-IN-female",
            "text": "தொழில்நுட்பம் மனித வாழ்க்கையை எளிதாக்குகிறது.",
            "label": "Tamil (ta-IN)",
        },
    ]

    results = []

    for case in test_cases:
        print(f"--- [Testing {case['label']}] ---")
        t0 = time.perf_counter()

        # Step 1: Real TTS Synthesis via Edge-TTS
        tts_res = await tts.synthesize(case["text"], voice=case["voice"])
        tts_duration = round(time.perf_counter() - t0, 3)

        audio_path = tts_res.audio_path
        audio_dur = tts_res.metadata.duration_seconds
        print(f"  [TTS] Synthesized {audio_dur}s audio in {tts_duration}s using {tts_res.metadata.voice}")
        print(f"        Audio file: {audio_path} ({len(tts_res.audio_bytes)} bytes)")

        # Step 2: Real Silero VAD Preflight Inspection
        preflight_meta = tts.preflight.validate_file(audio_path)
        print(f"  [VAD] Silero VAD passed: {preflight_meta.silero_detected} (speech_ratio: {preflight_meta.speech_ratio:.2%}, RMS: {preflight_meta.rms_dbfs} dBFS)")

        # Step 3: Real ASR Inference via faster-whisper with language hint
        t1 = time.perf_counter()
        asr_res = await asr.transcribe(audio_path, language=case["lang"])
        asr_duration = round(time.perf_counter() - t1, 3)

        print(f"  [ASR] Detected language: {asr_res.language} (probability: {asr_res.language_probability:.2f})")
        print(f"  [ASR] Transcribed text: \"{asr_res.text}\"")
        print(f"  [ASR] Transcription latency: {asr_duration}s (RTF: {asr_duration / max(0.1, audio_dur):.2f}x)")
        print(f"  [ASR] Word-level timestamp count: {len(asr_res.words)}")
        if asr_res.words:
            print(f"  [ASR] First 3 words: {[w.to_dict() for w in asr_res.words[:3]]}")
            print(f"  [ASR] Last 2 words: {[w.to_dict() for w in asr_res.words[-2:]]}")

        # Verification asserts
        assert asr_res.language == case["lang"], f"Expected {case['lang']}, got {asr_res.language}"
        assert len(asr_res.words) > 0, "Expected word-level timestamps"

        results.append({
            "case": case["label"],
            "expected_lang": case["lang"],
            "detected_lang": asr_res.language,
            "lang_prob": asr_res.language_probability,
            "audio_dur_s": audio_dur,
            "tts_latency_s": tts_duration,
            "asr_latency_s": asr_duration,
            "word_count": len(asr_res.words),
            "text_match": asr_res.text[:50] + "...",
        })

        if os.path.exists(audio_path):
            os.remove(audio_path)

        print("  [STATUS] PASSED\n")

    print("=================================================================")
    print("Real Model Verification Summary Table:")
    print("=================================================================")
    for r in results:
        print(f"- {r['case']}: Detected={r['detected_lang']} ({r['lang_prob']:.2f}) | "
              f"Audio={r['audio_dur_s']}s | ASR Latency={r['asr_latency_s']}s | Words={r['word_count']}")
    print("=================================================================")


if __name__ == "__main__":
    asyncio.run(run_verification())
