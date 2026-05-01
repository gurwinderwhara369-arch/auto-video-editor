# Tattoo Studio AI Editor

Local-first Python engine for turning raw tattoo studio clips into vertical,
template-timed Instagram Reel exports.

## Project Layout

```text
app/
  cli/              Command-line entrypoints
  engine/           Analyzer, scanner, planner, renderer, QA core
  web/webapp/       FastAPI UI
assets/
  reference_trends/ Sample trend videos
  sample_raw_clips/ Sample tattoo footage
templates/         Reusable edit templates
tests/             Unit and smoke tests
workspace/         Local generated jobs, uploads, reports, outputs
```

Legacy root wrappers like `main.py`, `variant_renderer.py`, `scanner/`, and
`renderer/` remain so older commands still work while the real source lives
under `app/`.

## Codespace Setup

This project is designed to run in GitHub Codespaces. The devcontainer installs:

- Python 3.12
- FFmpeg / ffprobe
- Python dependencies from `requirements.txt`

If your current Codespace was created before `.devcontainer/devcontainer.json`
existed, rebuild the container or install dependencies manually:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
python -m pip install -r requirements.txt
```

## Render A Reel

Place clips and a song in a job folder:

```text
workspace/jobs/job_001/raw_clips/
workspace/jobs/job_001/song.mp3
```

Run:

```bash
python -m app.cli.render_reel \
  --template templates/fast_glitch.json \
  --clips workspace/jobs/job_001/raw_clips \
  --song workspace/jobs/job_001/song.mp3 \
  --output workspace/outputs/job_001/final_reel.mp4
```

The CLI analyzes clips, builds a timeline, renders normalized vertical segments,
and exports a 1080x1920 H.264 MP4 with AAC audio.

## Useful Commands

Analyze clips only:

```bash
python -m analyzer.clip_ranker workspace/jobs/job_001/raw_clips \
  --output workspace/jobs/job_001/clip_metadata.json
```

Detect beats only:

```bash
python -m beat.beat_detector workspace/jobs/job_001/song.mp3 \
  --output workspace/jobs/job_001/beat_map.json
```

Run tests:

```bash
pytest
```

## Web Interface

Start the local Codespace UI:

```bash
python -m app.web.webapp.server --host 0.0.0.0 --port 8000
```

Open the forwarded port in your browser. The UI supports workspace paths and
browser uploads, then runs the full trend-to-tattoo pipeline in the background:

- scan trend template
- extract trend audio
- detect beats
- analyze tattoo clips and best moments
- render clean, balanced, and aggressive variants
- QA-select the final MP4

The default form values target the current test assets:

```text
assets/reference_trends/Montagem Tentana Trend 1.mp4
assets/sample_raw_clips/tattoo_process/
workspace/jobs/tattoo_raw/enriched_clip_metadata.json
workspace/jobs/tattoo_raw/moment_metadata.json
```

Legacy wrappers still work for the old commands:

```bash
python main.py --help
python -m webapp.server --help
```

## AI Vision Tagging

`ai_vision_tagger.py` is a separate CLI for tagging tattoo footage with Gemini
vision. It supports two modes:

- video input: OpenCV samples a few useful frames, then sends those frames
- frame input: send specific image files directly

Set your API key in the terminal session only:

```bash
export GEMINI_API_KEY="your-key-here"
```

Tag a video:

```bash
python ai_vision_tagger.py \
  --video workspace/jobs/job_001/raw_clips/clip_01.mp4 \
  --output workspace/jobs/job_001/clip_01_ai_tags.json
```

Tag direct frames:

```bash
python ai_vision_tagger.py \
  --frames workspace/temp/frame_01.jpg workspace/temp/frame_02.jpg \
  --output workspace/jobs/job_001/frame_ai_tags.json
```

Test without calling the API:

```bash
python ai_vision_tagger.py \
  --video workspace/jobs/job_001/raw_clips/clip_01.mp4 \
  --output workspace/jobs/job_001/clip_01_ai_tags.dry_run.json \
  --dry-run
```

The output JSON contains the sampled frames, OpenCV scores, AI tags, confidence,
short descriptions, and planner notes.

### Vision API Limit Protection

The live tagger keeps a local quota ledger at:

```text
workspace/temp/gemini_rate_limit_state.json
```

Defaults are set for the current free-tier guardrails:

- 30 requests per minute
- 15,000 estimated input tokens per minute
- 14,000 requests per day

You can override them if the API limits change:

```bash
python ai_vision_tagger.py \
  --video workspace/jobs/job_001/raw_clips/clip_01.mp4 \
  --output workspace/jobs/job_001/clip_01_ai_tags.json \
  --model gemma-3-27b-it \
  --rpm-limit 30 \
  --input-tpm-limit 15000 \
  --rpd-limit 14000
```

If a limit would be exceeded, the CLI writes a `rate_limited` JSON file with a
recommended `wait_seconds` value instead of crashing.
