# Tattoo Studio AI Editor — Product Requirements Document (PRD)

**Version:** 1.0  
**Status:** Codex-ready planning document  
**Product Codename:** `Trend-Sync Engine`  
**Primary Goal:** Build an automated video editing engine that converts raw tattoo studio footage into trendy, beat-synced Instagram Reels/short-form videos using reusable template recipes.

---

## 0. Executive Summary

The product is an **automated trendy reel generator for tattoo studios**.

Tattoo studios record raw clips every day: stencil, needle work, wiping, final reveal, artist/client shots. Editing those clips manually into trendy Reels takes time and requires skill. This system automates that process.

The core promise:

> Tattoo studio uploads raw clips, chooses a trendy template, and receives a finished vertical reel automatically.

This system is not a generic editor and not a full CapCut clone. It is a **niche automation tool** for one repeatable content category: tattoo reels.

The system has two major engines:

1. **Tattoo Reel Generator**  
   Takes raw tattoo clips + song/template and outputs a final reel.

2. **Trend Template Scanner**  
   Scans a viral reference video and extracts its editing structure into a reusable JSON recipe.

The correct business build order is:

```text
Manual/internal automation first
↓
Paid freelancer service
↓
Simple upload portal
↓
Template marketplace
↓
Advanced trend scanner
```

Do not build the full SaaS first. Build the local editing engine first.

---

## 1. Product Vision

### 1.1 What We Are Building

A system that can:

```text
Raw tattoo clips
+ selected template
+ song/audio
        ↓
analyze clips
detect best moments
sync to beat
apply effects/transitions
render final vertical reel
```

### 1.2 Target Users

Primary users:

- Freelance video editor serving tattoo studios
- Tattoo studios needing daily reels
- Tattoo artists who shoot raw clips but do not want to edit
- Social media managers for tattoo studios

### 1.3 Customer Pain

Tattoo studios need frequent Instagram content, but:

- Editing is slow
- Good editors are expensive
- Tattoo artists are busy
- Raw footage is messy
- Trends change fast
- CapCut/Premiere templates still require manual work
- Studios often need 2–3 videos daily

### 1.4 Product Positioning

Do not market this as:

> AI video editor software

Market it as:

> Send raw tattoo clips and get trendy tattoo reels automatically.

Better customer-facing tagline:

> Daily tattoo reels without daily editing.

---

## 2. Success Strategy

### 2.1 Brutal Business Reality

A ₹30/video price is only profitable if the workflow is almost fully automated.

If manual checking, client revisions, bad uploads, WhatsApp communication, and re-rendering are involved, ₹30/video is too low.

Recommended pricing ladder:

| Offer | Price |
|---|---:|
| Trial/sample reel | Free or ₹30 |
| Basic auto reel, no revision | ₹49–₹99 |
| Manual-checked reel | ₹149–₹299 |
| Monthly 15 reels | ₹999–₹1499 |
| Monthly 40 reels | ₹1999–₹2999 |
| Custom trend copy | ₹499–₹999 |

### 2.2 Best Go-To-Market

Start as a **service**, not SaaS.

Workflow:

```text
Studio sends clips via WhatsApp/Drive
↓
You run local script
↓
You check final output
↓
You deliver reel
```

After 3–5 paying studios, build the upload portal.

### 2.3 What Will Make It Work

- Niche focus: tattoo studios only
- 3–5 strong templates first
- Fast delivery
- Low friction
- Simple shooting guide for studios
- No unlimited revisions
- Output quality > technical features

### 2.4 What Can Kill It

- Bad raw footage
- Too many revisions
- Overbuilding SaaS before demand
- Scanner-first development
- Weak templates
- Poor crop/reveal timing
- Copyright misuse of songs/assets

---

## 3. Core System Architecture

The system contains six major modules:

```text
1. Template Scanner
2. Raw Asset Analyzer
3. Beat Detector
4. Edit Planner
5. FFmpeg Renderer
6. Upload/Job Backend
```

High-level pipeline:

```text
Reference viral video
        ↓
Template Scanner
        ↓
Template JSON


Tattoo raw clips
        ↓
Raw Asset Analyzer
        ↓
Clip Metadata JSON


Template JSON + Clip Metadata + Song Beat Map
        ↓
Edit Planner
        ↓
Timeline JSON
        ↓
FFmpeg Renderer
        ↓
Final Reel MP4
```

---

## 4. Build Order

### Phase 1 — Local MVP Generator

Goal:

```text
input clips + template JSON + song → final_reel.mp4
```

No Flask, no payment, no scanner initially.

Features:

- Read fixed/manual template JSON
- Read raw clips from folder
- Cut clips to required durations
- Crop to 9:16
- Add music
- Export MP4

### Phase 2 — Basic Effects

Add:

- Zoom punch
- White flash
- Fade
- Basic glitch transition
- Shake
- Film grain overlay
- Color contrast

### Phase 3 — OpenCV Clip Analyzer

Add:

- Blur/sharpness detection
- Brightness scoring
- Motion scoring
- Clip ranking
- Reject bad clips

### Phase 4 — Beat Sync

Add:

- BPM detection
- Beat timestamps
- Strong beats
- Beat-aligned cuts/transitions

### Phase 5 — Tattoo-Specific Logic

Add:

- Wipe detection
- Final reveal scoring
- Needle/process moment scoring
- Close-up scoring

### Phase 6 — Template Scanner

Add:

- Cut detection from reference videos
- Motion detection from reference videos
- Flash detection
- Convert reference video to template JSON

### Phase 7 — Flask Upload Portal

Add:

- Upload clips
- Upload/select song
- Choose template
- Render job
- Download result

### Phase 8 — Marketplace/SaaS

Add:

- Login
- Template gallery
- Razorpay/credits
- Render queue
- Download history
- Admin panel
- Subscription plans

---

## 5. Technical Stack

### 5.1 Python

Primary language for backend, scanning, planning, and orchestration.

### 5.2 OpenCV / cv2

Used for:

- Scene cut detection
- Optical flow / motion detection
- Blur detection
- Brightness analysis
- Wipe detection
- Frame sampling
- Raw tattoo footage scoring

### 5.3 Librosa

Used for:

- Beat detection
- Tempo/BPM estimation
- Onset strength
- Strong beat scoring
- Drop/energy peak approximation

### 5.4 FFmpeg

Used for:

- Cutting clips
- Concatenation
- Rendering
- Transitions using `xfade`
- Audio mapping
- Cropping/resizing
- Color grading
- Blur
- Zoom/pan
- Export compression

### 5.5 MoviePy

Optional convenience wrapper for:

- Simple prototyping
- Text overlays
- Layer composition
- Preview builds

Use FFmpeg for production rendering because it is faster and more stable for batch jobs.

### 5.6 MediaPipe / rembg / BackgroundRemover

Optional future features:

- Background segmentation
- Person/hand segmentation
- Background blur
- Premium cutout templates

Not first priority.

### 5.7 Flask

Used later for:

- Upload page
- Job creation API
- Download route
- Admin control panel

---

## 6. Core Data Objects

### 6.1 Template JSON

A reusable recipe extracted from a trend or manually authored.

```json
{
  "template_id": "fast_glitch_reveal_001",
  "name": "Fast Glitch Reveal",
  "version": "1.0",
  "aspect_ratio": "9:16",
  "resolution": {
    "width": 1080,
    "height": 1920
  },
  "total_duration": 15.0,
  "music_mode": "user_song",
  "segments": [
    {
      "index": 0,
      "start": 0.0,
      "end": 0.6,
      "duration": 0.6,
      "slot_type": "intro",
      "required_clip_type": "process",
      "effect": {
        "type": "slow_zoom",
        "zoom_start": 1.0,
        "zoom_end": 1.08
      },
      "transition_out": {
        "type": "cut"
      }
    },
    {
      "index": 1,
      "start": 0.6,
      "end": 1.2,
      "duration": 0.6,
      "slot_type": "high_energy",
      "required_clip_type": "motion",
      "effect": {
        "type": "shake",
        "intensity": 0.5
      },
      "transition_out": {
        "type": "glitch",
        "duration": 0.25
      }
    },
    {
      "index": 2,
      "start": 1.2,
      "end": 2.4,
      "duration": 1.2,
      "slot_type": "reveal",
      "required_clip_type": "final_reveal",
      "effect": {
        "type": "zoom_punch",
        "intensity": 0.8
      },
      "transition_out": {
        "type": "white_flash",
        "duration": 0.15
      }
    }
  ],
  "global_style": {
    "color_grade": "high_contrast_dark",
    "film_grain": true,
    "sharpen": true
  }
}
```

### 6.2 Clip Metadata JSON

Generated by raw asset analyzer.

```json
{
  "job_id": "job_001",
  "clips": [
    {
      "clip_id": "clip_001",
      "filename": "needle_closeup.mp4",
      "duration": 8.42,
      "width": 1080,
      "height": 1920,
      "fps": 30,
      "overall_score": 0.82,
      "sharpness_score": 0.88,
      "brightness_score": 0.74,
      "motion_score": 0.69,
      "detected_moments": [
        {
          "time": 2.4,
          "type": "process",
          "score": 0.81
        },
        {
          "time": 5.8,
          "type": "high_motion",
          "score": 0.9
        }
      ]
    },
    {
      "clip_id": "clip_002",
      "filename": "wipe_reveal.mp4",
      "duration": 6.1,
      "overall_score": 0.91,
      "sharpness_score": 0.94,
      "brightness_score": 0.82,
      "motion_score": 0.62,
      "detected_moments": [
        {
          "time": 3.1,
          "type": "wipe_end",
          "score": 0.87
        },
        {
          "time": 3.4,
          "type": "final_reveal",
          "score": 0.94
        }
      ]
    }
  ]
}
```

### 6.3 Beat Map JSON

Generated by beat detector.

```json
{
  "audio_file": "song.mp3",
  "duration": 15.0,
  "bpm": 128.0,
  "beats": [0.48, 0.94, 1.41, 1.88, 2.35],
  "strong_beats": [1.88, 3.76, 5.64],
  "energy_peaks": [
    {
      "time": 7.8,
      "strength": 0.95,
      "type": "drop_candidate"
    }
  ]
}
```

### 6.4 Final Timeline JSON

Generated by edit planner.

```json
{
  "job_id": "job_001",
  "template_id": "fast_glitch_reveal_001",
  "output_file": "final_reel.mp4",
  "resolution": {
    "width": 1080,
    "height": 1920
  },
  "fps": 30,
  "timeline": [
    {
      "segment_index": 0,
      "clip_id": "clip_001",
      "source_file": "needle_closeup.mp4",
      "source_start": 2.1,
      "source_end": 2.7,
      "timeline_start": 0.0,
      "timeline_end": 0.6,
      "effect": {
        "type": "slow_zoom",
        "zoom_start": 1.0,
        "zoom_end": 1.08
      },
      "transition_out": {
        "type": "cut"
      }
    },
    {
      "segment_index": 1,
      "clip_id": "clip_002",
      "source_file": "wipe_reveal.mp4",
      "source_start": 3.2,
      "source_end": 4.4,
      "timeline_start": 0.6,
      "timeline_end": 1.8,
      "effect": {
        "type": "zoom_punch",
        "intensity": 0.8
      },
      "transition_out": {
        "type": "white_flash",
        "duration": 0.15
      }
    }
  ],
  "audio": {
    "file": "song.mp3",
    "start": 0.0,
    "end": 15.0
  }
}
```

---

## 7. Module Details

---

# Module A: Template Scanner

## A.1 Purpose

Convert a reference trend video into a reusable editing recipe.

Input:

```text
reference_trend.mp4
```

Output:

```text
templates/reference_trend.json
```

## A.2 What It Detects

| Detection | Method | Output |
|---|---|---|
| Hard cuts | Histogram diff / frame diff | cut timestamps |
| Motion energy | Optical flow | motion curve |
| Zoom/pan/shake | Optical flow vector analysis | movement events |
| White/black flash | brightness spike/drop | flash events |
| Color style | average saturation/contrast | style metadata |
| Beat alignment | Librosa onset/beat detection | beat map |

## A.3 Important Rule

Do not copy original assets or copyrighted content. Only extract:

- timing
- movement pattern
- transition types
- effect timings
- structure

The scanned template should be a structural recipe, not a copied video.

## A.4 Scene Cut Detector

Algorithm:

1. Open reference video.
2. Sample frames.
3. Resize frames for speed.
4. Convert frames to HSV.
5. Calculate histogram.
6. Compare current histogram with previous histogram.
7. If difference exceeds threshold and enough time passed since previous cut, mark cut.
8. Save cut timestamps.

Recommended defaults:

```json
{
  "threshold": 0.55,
  "min_gap_seconds": 0.25,
  "sample_every_n_frames": 1
}
```

Tuning:

- Too many cuts: increase threshold to 0.65–0.75
- Missed cuts: decrease threshold to 0.35–0.45
- Duplicate cuts: increase min_gap_seconds

## A.5 Motion Scanner

Use Farneback optical flow.

Detect:

- high motion
- shake-like jitter
- zoom-like outward flow
- pan-left/pan-right
- pan-up/pan-down

MVP simplification:

- First version only calculates `motion_score`
- Later classify motion type

Motion output:

```json
{
  "motion_events": [
    {
      "start": 1.2,
      "end": 1.8,
      "type": "high_motion",
      "score": 0.86
    }
  ]
}
```

## A.6 Flash Scanner

Algorithm:

1. Convert frame to grayscale.
2. Calculate average brightness.
3. Compare brightness to rolling average.
4. If brightness jumps sharply, mark `white_flash`.
5. If brightness drops sharply, mark `black_flash` or `blackout`.

Output:

```json
{
  "effects": [
    {
      "time": 2.2,
      "type": "white_flash",
      "duration": 0.15,
      "intensity": 0.9
    }
  ]
}
```

---

# Module B: Raw Asset Analyzer

## B.1 Purpose

Understand and rank raw tattoo footage.

Input:

```text
uploads/job_001/raw_clips/*.mp4
```

Output:

```text
uploads/job_001/clip_metadata.json
```

## B.2 What It Detects

| Feature | MVP? | Purpose |
|---|---:|---|
| Duration | yes | know usable length |
| Resolution/FPS | yes | normalize render |
| Sharpness | yes | reject blurry clips |
| Brightness | yes | reject dark clips |
| Motion score | yes | match high-energy slots |
| Wipe moment | later | find reveal |
| Final reveal | later | ending/drop |
| Close-up/detail | later | process shots |
| Background removal | later | premium style |

## B.3 Sharpness Detection

Use Laplacian variance.

Logic:

```text
variance of Laplacian high = sharp
variance low = blurry
```

Clip-level score:

```json
{
  "sharpness_score": 0.88,
  "is_blurry": false
}
```

## B.4 Brightness Detection

Calculate average frame luminance.

Reject:

- too dark
- too bright/overexposed

## B.5 Motion Detection

Use frame difference or optical flow.

Use motion score to classify:

| Motion Score | Meaning |
|---:|---|
| 0.0–0.2 | static |
| 0.2–0.5 | normal |
| 0.5–0.8 | active |
| 0.8–1.0 | high energy |

## B.6 Tattoo Wipe Detection

Future feature.

Goal:

Detect paper towel/wipe moving over tattoo.

Simple heuristic:

- Look for large white/light object moving across frame
- Detect high brightness region
- Detect motion across tattoo area
- Mark moment after white object exits frame

Output:

```json
{
  "time": 4.2,
  "type": "wipe_end",
  "score": 0.87
}
```

## B.7 Final Reveal Detection

MVP heuristic:

- low motion
- high sharpness
- stable frame
- close-up
- appears after wipe moment if detected

---

# Module C: Beat Detector

## C.1 Purpose

Extract rhythm from audio.

Input:

```text
song.mp3
```

Output:

```text
beat_map.json
```

## C.2 Required Outputs

- BPM
- Beat timestamps
- Strong beat timestamps
- Energy peaks
- Drop candidates

## C.3 MVP Logic

1. Load audio.
2. Calculate onset envelope.
3. Estimate BPM.
4. Detect beat frames.
5. Convert frames to time.
6. Score beat strength using onset envelope.
7. Top 25% beat strengths become `strong_beats`.

## C.4 Drop Candidate Logic

MVP approximation:

- compute onset strength
- compute RMS energy
- find peaks where energy increases suddenly
- mark strongest peaks as drop candidates

---

# Module D: Edit Planner

## D.1 Purpose

The planner decides which tattoo clip fills which template slot.

Input:

```text
template.json
clip_metadata.json
beat_map.json
```

Output:

```text
timeline.json
```

## D.2 Matching Rules

### Slot Types

| Slot Type | Preferred Clip Type |
|---|---|
| intro | stable/process |
| process | needle/work |
| high_energy | high motion |
| transition | any sharp clip |
| reveal | final reveal/wipe_end |
| detail | close-up sharp clip |
| ending | final clean tattoo |

### Effect Rules

| Event | Effect |
|---|---|
| normal beat | cut |
| strong beat | zoom punch / flash |
| drop | final reveal + flash + zoom |
| high motion slot | shake/glitch |
| slow section | cinematic zoom/fade |

## D.3 Fallback Logic

If no matching clip is found:

1. Pick highest overall score clip.
2. Pick sharpest clip.
3. Reuse clip with different source range.
4. If insufficient footage, slow down clip slightly.
5. Last fallback: freeze frame/zoom still.

## D.4 Avoid Repetition

Planner should track used clip ranges.

Avoid:

- same source segment repeated too often
- final reveal appearing before ending
- blurry clips used in important slots

---

# Module E: FFmpeg Renderer

## E.1 Purpose

Convert timeline JSON into final MP4.

## E.2 Rendering Responsibilities

- Normalize clips
- Crop to 9:16
- Cut source ranges
- Apply effects
- Apply transitions
- Add music
- Export MP4

## E.3 Output Settings

Recommended for Instagram Reels:

```json
{
  "width": 1080,
  "height": 1920,
  "fps": 30,
  "video_codec": "libx264",
  "audio_codec": "aac",
  "pixel_format": "yuv420p",
  "preset": "veryfast",
  "crf": 23
}
```

For production quality, use:

```text
-preset medium -crf 20
```

For faster preview, use:

```text
-preset ultrafast -crf 28
```

## E.4 Normalize Every Clip

Before applying `xfade`, clips should have same:

- resolution
- fps
- pixel format
- timebase
- sample rate if audio used

FFmpeg `xfade` requires compatible video streams. Normalize first.

## E.5 Core Effects

### Cut

No transition.

### Xfade

Use for:

- fade
- wipeleft
- wiperight
- circleopen
- circleclose
- pixelize
- dissolve
- hblur
- smoothleft
- smoothright

Example concept:

```text
[0:v][1:v]xfade=transition=fade:duration=0.5:offset=2.5[v]
```

### White Flash

Simplified:

- overlay white frame for 0.1–0.2 seconds
- fade white down

### Zoom Punch

Options:

- `scale + crop`
- `zoompan`
- pre-render segment with zoom expression

### Shake

Options:

- crop with sinusoidal/random x/y offset
- overlay shifted frame onto canvas
- OpenCV pre-render for high-quality shake

### Film Grain

Options:

- overlay grain video with opacity
- FFmpeg noise filter

### Color Grade

Use FFmpeg filters:

- `eq`
- `curves`
- `hue`
- `lut3d` for LUT support later

---

# Module F: Flask Backend

## F.1 Purpose

Build upload and job execution system after local MVP works.

## F.2 Basic Routes

### `POST /api/jobs`

Create render job.

Inputs:

- clips[]
- song
- template_id

Output:

```json
{
  "job_id": "job_abc123",
  "status": "queued"
}
```

### `GET /api/jobs/<job_id>`

Return job status.

```json
{
  "job_id": "job_abc123",
  "status": "rendering",
  "progress": 62
}
```

### `GET /api/jobs/<job_id>/download`

Download final MP4.

### `GET /api/templates`

List available templates.

## F.3 Job Status

Allowed statuses:

```text
created
uploaded
analyzing
planning
rendering
completed
failed
```

## F.4 Upload Safety

Requirements:

- Use secure filenames
- Limit file size
- Allow only video/audio types
- Store each job in unique folder
- Never trust user filenames
- Clean old jobs periodically

## F.5 Future Queue

Use a background queue later:

- Celery + Redis
- RQ + Redis
- Dramatiq
- or simple multiprocessing queue for local version

---

## 8. File Structure

Recommended repo:

```text
tattoo-reel-engine/
│
├── README.md
├── PRD.md
├── requirements.txt
├── .env.example
├── main.py
│
├── app/
│   ├── __init__.py
│   ├── flask_app.py
│   ├── routes.py
│   └── job_service.py
│
├── core/
│   ├── config.py
│   ├── paths.py
│   ├── models.py
│   └── utils.py
│
├── scanner/
│   ├── __init__.py
│   ├── scene_cut_detector.py
│   ├── motion_scanner.py
│   ├── flash_scanner.py
│   ├── beat_scanner.py
│   └── template_builder.py
│
├── analyzer/
│   ├── __init__.py
│   ├── clip_probe.py
│   ├── sharpness_detector.py
│   ├── brightness_detector.py
│   ├── motion_analyzer.py
│   ├── wipe_detector.py
│   └── clip_ranker.py
│
├── beat/
│   ├── __init__.py
│   └── beat_detector.py
│
├── planner/
│   ├── __init__.py
│   ├── slot_matcher.py
│   ├── edit_planner.py
│   └── fallback_rules.py
│
├── renderer/
│   ├── __init__.py
│   ├── ffmpeg_runner.py
│   ├── normalizer.py
│   ├── segment_renderer.py
│   ├── transition_builder.py
│   ├── effects.py
│   └── final_exporter.py
│
├── templates/
│   ├── fast_glitch.json
│   ├── cinematic_reveal.json
│   └── process_story.json
│
├── assets/
│   ├── overlays/
│   ├── grain/
│   └── luts/
│
├── workspace/
│   ├── uploads/
│   ├── jobs/
│   ├── temp/
│   └── outputs/
│
└── tests/
    ├── test_scene_cut_detector.py
    ├── test_clip_analyzer.py
    ├── test_planner.py
    └── test_renderer.py
```

---

## 9. MVP Implementation Tasks for Codex

### Sprint 1 — Local Generator Skeleton

#### Task 1: Create project structure

Create the folder structure above.

#### Task 2: Define template schema

Create `templates/fast_glitch.json`.

#### Task 3: Build `core/models.py`

Define dataclasses or Pydantic models for:

- Template
- Segment
- ClipMetadata
- BeatMap
- Timeline
- TimelineSegment

#### Task 4: Build `renderer/ffmpeg_runner.py`

Utility function:

```python
run_ffmpeg(cmd: list[str]) -> None
```

Requirements:

- print command in debug mode
- capture stderr
- raise useful error on failure

#### Task 5: Build basic assembler

`main.py` should:

1. Read template JSON
2. Read clips from input folder
3. Build naive timeline
4. Render final MP4

Acceptance:

```text
python main.py --template templates/fast_glitch.json --clips input/clips --song input/song.mp3 --output output/final.mp4
```

Produces valid vertical MP4.

---

### Sprint 2 — Clip Analyzer

#### Task 1: Clip probe

Build `analyzer/clip_probe.py`.

Return:

- duration
- width
- height
- fps

Use OpenCV or ffprobe.

#### Task 2: Sharpness detector

Build `analyzer/sharpness_detector.py`.

Use Laplacian variance.

#### Task 3: Brightness detector

Build `analyzer/brightness_detector.py`.

Return normalized brightness score.

#### Task 4: Motion analyzer

Build `analyzer/motion_analyzer.py`.

Return normalized motion score.

#### Task 5: Clip ranker

Build `analyzer/clip_ranker.py`.

Combine scores:

```text
overall_score = sharpness * 0.45 + brightness * 0.25 + motion * 0.30
```

Acceptance:

```text
python -m analyzer.clip_ranker input/clips
```

Outputs `clip_metadata.json`.

---

### Sprint 3 — Beat Detection

#### Task 1: Build beat detector

File:

```text
beat/beat_detector.py
```

Return:

- BPM
- beats
- strong_beats
- energy_peaks

#### Task 2: Integrate beat map into planner

If template has `beat_sync: true`, adjust segment boundaries to nearest beat within tolerance.

Tolerance:

```text
0.12 seconds
```

Acceptance:

Output timeline cuts align close to beat timestamps.

---

### Sprint 4 — Effects Renderer

#### Task 1: Implement crop to 9:16

Function:

```python
build_vertical_crop_filter(width=1080, height=1920)
```

#### Task 2: Implement slow zoom

Use FFmpeg scale/crop or zoompan.

#### Task 3: Implement white flash

Render small flash overlay around effect timestamp.

#### Task 4: Implement glitch transition

Use FFmpeg xfade if between two segments.

#### Task 5: Implement final audio map

Use uploaded song as final audio.

Acceptance:

Final reel has:

- vertical crop
- song audio
- template-timed cuts
- at least one visual effect

---

### Sprint 5 — Template Scanner

#### Task 1: Scene cut detector

File:

```text
scanner/scene_cut_detector.py
```

Input reference video, output cuts.

#### Task 2: Template builder

Turn detected cuts into template JSON.

#### Task 3: Flash scanner

Detect brightness spike/drop.

#### Task 4: Motion scanner

Detect motion score curve.

Acceptance:

```text
python -m scanner.template_builder reference.mp4 --output templates/reference.json
```

Produces reusable template JSON.

---

### Sprint 6 — Tattoo-Specific Detection

#### Task 1: Wipe detector MVP

Detect moving white object.

#### Task 2: Final reveal scorer

Find stable sharp frames after wipe.

#### Task 3: Slot matching improvement

Reveal slot prefers wipe/final reveal clips.

Acceptance:

Final reveal slots use best final tattoo shots.

---

### Sprint 7 — Flask Portal

#### Task 1: Upload route

Allow clips + song upload.

#### Task 2: Job creation

Create unique job folder.

#### Task 3: Run local pipeline

Call analyzer → planner → renderer.

#### Task 4: Download route

Return final MP4.

Acceptance:

User can upload files from browser and receive output video.

---

## 10. CLI Commands

### Analyze clips

```bash
python -m analyzer.clip_ranker workspace/jobs/job_001/raw_clips \
  --output workspace/jobs/job_001/clip_metadata.json
```

### Detect beats

```bash
python -m beat.beat_detector workspace/jobs/job_001/song.mp3 \
  --output workspace/jobs/job_001/beat_map.json
```

### Scan template

```bash
python -m scanner.template_builder input/reference_trend.mp4 \
  --output templates/reference_trend.json
```

### Render video

```bash
python main.py \
  --template templates/fast_glitch.json \
  --clips workspace/jobs/job_001/raw_clips \
  --song workspace/jobs/job_001/song.mp3 \
  --output workspace/outputs/job_001/final_reel.mp4
```

---

## 11. Quality Rules

### 11.1 Input Clip Rejection

Reject or deprioritize clips if:

- sharpness score < 0.35
- brightness score < 0.25
- duration < required segment duration
- FPS cannot be read
- video cannot be opened

### 11.2 Output Requirements

Every output should be:

- 9:16 vertical
- 1080x1920
- 30 FPS
- H.264 MP4
- AAC audio
- under target duration
- no black frames at beginning/end
- no missing audio
- no accidental repeated segment unless fallback

### 11.3 Human Review First

For early business version:

- system generates
- freelancer checks
- deliver only if quality acceptable

No fully automatic customer delivery until enough quality data exists.

---

## 12. Template Types to Build First

### Template A: Fast Glitch Reel

Use for trendy/high-energy posts.

Properties:

- 10–20 cuts in 15 seconds
- fast slot durations: 0.4–1.0s
- glitch transitions
- white flashes
- zoom punch on strong beats
- high contrast dark grade

### Template B: Cinematic Reveal

Use for premium tattoo showcase.

Properties:

- slower pacing
- 4–8 cuts in 15 seconds
- slow zoom
- soft fade
- film grain
- final reveal on drop
- dark cinematic grade

### Template C: Process Story

Use to show tattoo journey.

Properties:

- stencil
- needle closeup
- wipe
- final reveal
- artist/client shot
- story order matters more than beat speed

---

## 13. Legal and Ethical Constraints

The system must not:

- Download copyrighted videos illegally
- Reuse someone else’s original video frames
- Reuse watermarked assets
- Misrepresent copied content as original footage
- Bundle copyrighted music without permission

Allowed target:

- Extract structural timing/motion/effect patterns
- Use client-provided raw footage
- Use client-selected/authorized audio
- Export silent video for Instagram audio replacement if needed

Recommended workflow:

- Use reference audio only for timing
- Let client add trending Instagram audio during posting
- Or use royalty-free/authorized music

---

## 14. Business Workflow

### 14.1 Manual Service MVP

1. Studio sends raw clips.
2. Freelancer places them in job folder.
3. Script generates reel.
4. Freelancer checks result.
5. Deliver MP4.

### 14.2 Website MVP

1. Studio uploads clips.
2. Chooses template.
3. Uploads/selects song.
4. System renders.
5. Freelancer/Admin reviews.
6. Client downloads.

### 14.3 SaaS Version

1. Client logs in.
2. Selects plan/credits.
3. Uploads clips.
4. Chooses template.
5. System renders automatically.
6. Client downloads.
7. Render history saved.

---

## 15. Metrics to Track

### Product Metrics

- render success rate
- average render time
- average output duration
- failed job reasons
- number of clips rejected
- output quality score

### Business Metrics

- studios contacted
- sample reels created
- sample-to-paid conversion
- monthly active studios
- reels per studio/month
- revenue per studio
- revision rate
- churn

### Quality Metrics

- blur rejection accuracy
- final reveal selection accuracy
- beat sync accuracy
- template reuse performance
- manual correction time

---

## 16. Acceptance Criteria for First MVP

The MVP is successful when:

1. User can place 5–10 tattoo clips in a folder.
2. User can provide a song.
3. User can select one template JSON.
4. System outputs a 15-second 9:16 MP4.
5. Output contains cuts according to template.
6. Output contains music.
7. Output uses at least basic crop and effect.
8. Bad/blurry clips are avoided.
9. Video can be posted on Instagram Reels.
10. Human review takes less than 2 minutes.

---

## 17. Codex Implementation Notes

When implementing:

- Prefer simple working code over over-engineering.
- Build local CLI first.
- Avoid full Flask app until render pipeline works.
- Use JSON files for communication between modules.
- Keep modules independent and testable.
- Use `subprocess.run([...], check=True)` for FFmpeg.
- Never build one giant FFmpeg command too early.
- Render intermediate normalized segments first if easier.
- Add logging to each stage.
- Save debug JSON files for every job.
- Make thresholds configurable.

---

## 18. References

These are the main official/technical references used for the planned implementation:

- Librosa beat tracking: https://librosa.org/doc/main/generated/librosa.beat.beat_track.html
- OpenCV optical flow: https://docs.opencv.org/4.x/d4/dee/tutorial_optical_flow.html
- FFmpeg xfade wiki: https://trac.ffmpeg.org/wiki/Xfade
- FFmpeg filters documentation: https://ffmpeg.org/ffmpeg-filters.html
- Flask file uploads: https://flask.palletsprojects.com/en/stable/patterns/fileuploads/
- rembg background removal: https://github.com/danielgatis/rembg

---

## 19. One-Line Product Definition

**Tattoo Studio AI Editor is a Python/OpenCV/Librosa/FFmpeg-based automation engine that scans trend templates, analyzes raw tattoo footage, plans beat-synced timelines, and renders bulk Instagram Reels for tattoo studios.**
