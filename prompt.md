# PS3 Project — Assessment Understanding and Technical Research

We are building **Script, Voiceover and B-roll Video Engine** for the IncuBrix 2027 Software Engineer Assessment (PS3).

Your first task is to understand the complete project. Do NOT start implementing code yet.

## 1. Assessment documents

Read both files completely:

- `assessment/PS3_Assessment_Brief.pdf`
- `assessment/PS3_Submission_Workbook.xlsx`

For the PDF:
- Extract every requirement.
- Understand all 8 must-haves.
- Understand Core, Advanced and Outstanding evaluation levels.
- Identify hard cases, metrics, output formats and submission requirements.
- Identify all integration requirements.

For the Excel workbook:
- Inspect every sheet.
- Understand all required fields and calculated fields.
- Identify evidence requirements, metrics and self-checks.
- Map each workbook requirement to the corresponding PDF requirement.

Do not invent or omit requirements.

## 2. HyperFrames technical research

Study the cloned repository:

`references/hyperframes/`

Read its:
- README and documentation.
- Architecture and package structure.
- CLI implementation.
- Core, engine and producer packages.
- Rendering pipeline.
- FFmpeg integration.
- Audio handling.
- Caption and overlay components.
- Timing and frame synchronisation.
- Examples and tests.
- Licensing information.

Understand how it works internally, not just how to run its commands.

Also identify which components can be reused, which need adapters, and which PS3 requirements must be implemented independently.

Official source: https://github.com/heygen-com/hyperframes

## 3. Understand the complete PS3 workflow

The system must support:

1. Audio upload and script input.
2. Speech transcription or narration generation.
3. Semantic scene segmentation.
4. Relevant B-roll retrieval from licensed sources.
5. Clip relevance scoring and duplicate prevention.
6. Scene timing based on narration.
7. Timeline and attribution generation.
8. Captions and SRT generation.
9. Video rendering in requested aspect ratios.
10. Manifest generation and job tracking.

## 4. Technical and assessment constraints

Pay particular attention to:
- Commercial-use licensing and source attribution.
- No watermarked or unauthorised footage.
- No realistic AI-generated faces of real people.
- Every second of narration must be covered.
- No repeated footage within a video.
- No black frames, frozen frames or audio drift.
- Background jobs and progress tracking.
- OpenAPI 3.1.
- Idempotency keys.
- Structured errors and logs.
- Docker Compose one-command startup.
- Tests that run without paid API keys.
- Reproducible outputs and honest performance metrics.

## 5. Expected research deliverables

Create these documents before implementation:

1. `docs/REQUIREMENTS.md` — complete assessment requirements checklist.
2. `docs/ARCHITECTURE.md` — proposed system architecture and data flow.
3. `docs/TECH_STACK.md` — recommended technologies and reasoning.
4. `docs/HYPERFRAMES_ANALYSIS.md` — what HyperFrames provides, relevant packages, integration approach and limitations.
5. `docs/IMPLEMENTATION_PLAN.md` — phased implementation plan mapped to assessment criteria.
6. `docs/RISKS_AND_GAPS.md` — technical, licensing, performance and assessment risks.

## 6. Important instructions

- Do not start coding yet.
- Do not blindly copy HyperFrames into our implementation.
- Do not claim HyperFrames features as our original work.
- Do not assume a package or API exists without checking its source.
- Do not fabricate benchmarks or test results.
- Preserve all assessment requirements.
- Recommend the simplest architecture that can satisfy the requirements reliably.
- Flag unclear requirements rather than making assumptions.

At the end, provide a clear explanation of the complete system, what we need to build ourselves, what we can reuse, and the recommended implementation order.

I should be able to understand and explain every architectural decision during the IncuBrix live evaluation.

and also  inspect HyperFrames' actual source code and trace the rendering flow from CLI entry point to final MP4 generation