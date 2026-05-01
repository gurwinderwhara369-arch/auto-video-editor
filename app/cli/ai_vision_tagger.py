from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests


DEFAULT_MODEL = "gemini-2.0-flash"
DEFAULT_RATE_STATE = Path("workspace/temp/gemini_rate_limit_state.json")
DEFAULT_RPM_LIMIT = 30
DEFAULT_INPUT_TPM_LIMIT = 15_000
DEFAULT_RPD_LIMIT = 14_000
DEFAULT_IMAGE_TOKEN_ESTIMATE = 3_500
CATEGORIES = [
    "stencil",
    "needle_work",
    "wiping",
    "final_reveal",
    "closeup_detail",
    "artist_client",
    "studio_ambience",
    "unusable",
]


@dataclass
class FrameCandidate:
    path: str
    source: str
    time: float | None
    reason: str
    sharpness: float
    brightness: float
    motion: float
    centered_detail: float


class RateLimitExceeded(RuntimeError):
    def __init__(self, message: str, wait_seconds: int) -> None:
        super().__init__(message)
        self.wait_seconds = wait_seconds


def score_frame(frame: np.ndarray, previous: np.ndarray | None = None) -> tuple[float, float, float, float]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(gray.mean()) / 255.0
    motion = 0.0
    if previous is not None:
        previous_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
        previous_gray = cv2.resize(previous_gray, (gray.shape[1], gray.shape[0]))
        motion = float(cv2.absdiff(gray, previous_gray).mean()) / 255.0

    edges = cv2.Canny(gray, 80, 160)
    height, width = edges.shape
    margin_x = int(width * 0.22)
    margin_y = int(height * 0.22)
    center_edges = edges[margin_y : height - margin_y, margin_x : width - margin_x]
    total_density = float(edges.mean()) / 255.0
    center_density = float(center_edges.mean()) / 255.0 if center_edges.size else 0.0
    centered_detail = center_density / total_density if total_density > 0 else 0.0
    centered_detail = max(0.0, min(1.0, centered_detail))
    return sharpness, brightness, motion, centered_detail


def extract_video_frames(video_path: Path, output_dir: Path, max_frames: int) -> list[FrameCandidate]:
    output_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise ValueError(f"Could not open video: {video_path}")

    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or 30.0
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        sample_count = min(24, total_frames)
        indexes = sorted({int(i) for i in np.linspace(0, total_frames - 1, sample_count)})

        previous = None
        scanned: list[tuple[int, np.ndarray, FrameCandidate]] = []
        for frame_index in indexes:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            if not ok:
                continue
            sharpness, brightness, motion, centered_detail = score_frame(frame, previous)
            previous = frame
            scanned.append(
                (
                    frame_index,
                    frame,
                    FrameCandidate(
                        path="",
                        source=str(video_path),
                        time=round(frame_index / fps, 3),
                        reason="sampled",
                        sharpness=round(min(1.0, sharpness / 700.0), 4),
                        brightness=round(brightness, 4),
                        motion=round(min(1.0, motion / 0.15), 4),
                        centered_detail=round(centered_detail, 4),
                    ),
                )
            )
    finally:
        capture.release()

    if not scanned:
        raise ValueError(f"No readable frames found in {video_path}")

    picks: list[tuple[str, int, np.ndarray, FrameCandidate]] = []
    picks.append(("opening_context", *scanned[0]))
    picks.append(("sharpest_detail", *max(scanned, key=lambda item: item[2].sharpness)))
    picks.append(("highest_motion", *max(scanned, key=lambda item: item[2].motion)))
    late_frames = scanned[len(scanned) // 2 :] or scanned
    picks.append(("late_stable_reveal_candidate", *max(late_frames, key=lambda item: item[2].sharpness - item[2].motion)))

    unique: dict[int, tuple[str, int, np.ndarray, FrameCandidate]] = {}
    for reason, frame_index, frame, candidate in picks:
        if frame_index not in unique:
            unique[frame_index] = (reason, frame_index, frame, candidate)
    selected = list(unique.values())[:max_frames]

    candidates: list[FrameCandidate] = []
    for rank, (reason, _frame_index, frame, candidate) in enumerate(selected, start=1):
        frame_path = output_dir / f"{video_path.stem}_{rank:02d}_{reason}.jpg"
        cv2.imwrite(str(frame_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        candidate.path = str(frame_path)
        candidate.reason = reason
        candidates.append(candidate)
    return candidates


def prepare_frame_inputs(frame_paths: list[Path]) -> list[FrameCandidate]:
    candidates: list[FrameCandidate] = []
    for frame_path in frame_paths:
        frame = cv2.imread(str(frame_path))
        if frame is None:
            raise ValueError(f"Could not read image frame: {frame_path}")
        sharpness, brightness, motion, centered_detail = score_frame(frame)
        candidates.append(
            FrameCandidate(
                path=str(frame_path),
                source=str(frame_path),
                time=None,
                reason="direct_frame_upload",
                sharpness=round(min(1.0, sharpness / 700.0), 4),
                brightness=round(brightness, 4),
                motion=round(min(1.0, motion / 0.15), 4),
                centered_detail=round(centered_detail, 4),
            )
        )
    return candidates


def build_prompt(candidates: list[FrameCandidate]) -> str:
    return f"""
You are tagging raw tattoo studio footage for an automated Instagram Reel editor.

Classify each provided frame into exactly one primary category:
{", ".join(CATEGORIES)}

Use these meanings:
- stencil: tattoo stencil/outline before needle work
- needle_work: needle machine actively tattooing skin
- wiping: paper towel/wipe/cleaning motion on tattoo area
- final_reveal: clean finished tattoo reveal or showcase
- closeup_detail: close tattoo detail, texture, ink, skin, or linework without obvious needle/wipe
- artist_client: artist/client/person-focused shot
- studio_ambience: studio, tools, chair, room, mood shot
- unusable: blurry, dark, blocked, irrelevant, or not useful

Return only valid JSON in this exact shape:
{{
  "overall_summary": "one short sentence",
  "frames": [
    {{
      "frame_index": 1,
      "primary_tag": "one category",
      "confidence": 0.0,
      "description": "short visual description",
      "best_use": "intro|process|transition|reveal|ending|unused",
      "reasons": ["short reason"],
      "planner_notes": "one line for the video planner"
    }}
  ],
  "clip_level_tags": ["one or more categories"],
  "recommended_template_slots": ["intro|process|transition|reveal|ending"],
  "usable": true
}}

OpenCV pre-scores for these frames:
{json.dumps([asdict(candidate) for candidate in candidates], indent=2)}
""".strip()


def estimate_input_tokens(candidates: list[FrameCandidate], *, image_token_estimate: int) -> int:
    # Roughly 4 chars per text token, plus conservative fixed image estimate.
    prompt_tokens = max(1, len(build_prompt(candidates)) // 4)
    return prompt_tokens + len(candidates) * image_token_estimate


def load_rate_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"requests": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError:
        return {"requests": []}
    if not isinstance(payload.get("requests"), list):
        return {"requests": []}
    return payload


def save_rate_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")


def prune_rate_state(state: dict[str, Any], now: float) -> dict[str, Any]:
    state["requests"] = [
        request
        for request in state.get("requests", [])
        if now - float(request.get("timestamp", 0)) < 86_400
    ]
    return state


def check_rate_limits(
    state: dict[str, Any],
    *,
    estimated_input_tokens: int,
    now: float,
    rpm_limit: int,
    input_tpm_limit: int,
    rpd_limit: int,
) -> None:
    requests = state.get("requests", [])
    minute_requests = [
        request for request in requests if now - float(request.get("timestamp", 0)) < 60
    ]
    day_requests = [
        request for request in requests if now - float(request.get("timestamp", 0)) < 86_400
    ]

    if len(minute_requests) + 1 > rpm_limit:
        oldest = min(float(request["timestamp"]) for request in minute_requests)
        wait = max(1, int(61 - (now - oldest)))
        raise RateLimitExceeded(f"Local RPM guard blocked request. Wait about {wait}s.", wait)

    used_minute_tokens = sum(int(request.get("input_tokens", 0)) for request in minute_requests)
    if used_minute_tokens + estimated_input_tokens > input_tpm_limit:
        oldest = min(float(request["timestamp"]) for request in minute_requests) if minute_requests else now
        wait = max(1, int(61 - (now - oldest)))
        raise RateLimitExceeded(
            "Local input-token/minute guard blocked request. "
            f"Current={used_minute_tokens}, next={estimated_input_tokens}, "
            f"limit={input_tpm_limit}. Wait about {wait}s.",
            wait,
        )

    if len(day_requests) + 1 > rpd_limit:
        oldest = min(float(request["timestamp"]) for request in day_requests)
        wait = max(1, int(86_401 - (now - oldest)))
        raise RateLimitExceeded(f"Local daily request guard blocked request. Wait about {wait}s.", wait)


def record_rate_usage(
    state_path: Path,
    state: dict[str, Any],
    *,
    model: str,
    source: str,
    input_tokens: int,
    now: float,
) -> None:
    state.setdefault("requests", []).append(
        {
            "timestamp": now,
            "model": model,
            "source": source,
            "input_tokens": input_tokens,
        }
    )
    save_rate_state(state_path, prune_rate_state(state, now))


def image_part(path: Path) -> dict[str, Any]:
    mime_type = mimetypes.guess_type(path)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {"inline_data": {"mime_type": mime_type, "data": data}}


def call_gemini(
    candidates: list[FrameCandidate],
    *,
    api_key: str,
    model: str,
    timeout: int = 60,
) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    parts: list[dict[str, Any]] = [{"text": build_prompt(candidates)}]
    for candidate in candidates:
        parts.append(image_part(Path(candidate.path)))

    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    }
    if model.startswith("gemma-"):
        body["generationConfig"].pop("response_mime_type", None)
    response = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        json=body,
        timeout=timeout,
    )
    if response.status_code == 400 and "JSON mode is not enabled" in response.text:
        body["generationConfig"].pop("response_mime_type", None)
        response = requests.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json=body,
            timeout=timeout,
        )
    if response.status_code == 429:
        wait_seconds = parse_retry_delay(response.text) or 60
        raise RateLimitExceeded(f"Remote API quota blocked request. Wait about {wait_seconds}s.", wait_seconds)
    if response.status_code >= 400:
        raise RuntimeError(f"Gemini API error {response.status_code}: {response.text}")

    payload = response.json()
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    return parse_json_text(text)


def parse_json_text(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def parse_retry_delay(text: str) -> int | None:
    match = re.search(r'"retryDelay":\s*"(\d+)s"', text)
    if match:
        return int(match.group(1))
    match = re.search(r"retry in ([0-9.]+)s", text, flags=re.IGNORECASE)
    if match:
        return int(float(match.group(1))) + 1
    return None


def dry_run_result(candidates: list[FrameCandidate]) -> dict[str, Any]:
    frames = []
    tags = set()
    slots = set()
    for index, candidate in enumerate(candidates, start=1):
        if candidate.motion > 0.55:
            tag = "needle_work"
            slot = "process"
        elif candidate.sharpness > 0.6 and candidate.motion < 0.25:
            tag = "final_reveal"
            slot = "reveal"
        elif candidate.centered_detail > 0.55:
            tag = "closeup_detail"
            slot = "process"
        else:
            tag = "studio_ambience"
            slot = "intro"
        tags.add(tag)
        slots.add(slot)
        frames.append(
            {
                "frame_index": index,
                "primary_tag": tag,
                "confidence": 0.45,
                "description": "Dry-run heuristic tag; no API call was made.",
                "best_use": slot,
                "reasons": [candidate.reason],
                "planner_notes": f"Use as {slot} if no stronger AI tag is available.",
            }
        )
    return {
        "overall_summary": "Dry run created heuristic tattoo reel tags from sampled frames.",
        "frames": frames,
        "clip_level_tags": sorted(tags),
        "recommended_template_slots": sorted(slots),
        "usable": True,
    }


def write_output(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Tag tattoo footage frames with Gemini vision.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--video", type=Path, help="Video to sample frames from.")
    source.add_argument("--frames", type=Path, nargs="+", help="One or more image frames to tag directly.")
    parser.add_argument("--output", type=Path, required=True, help="JSON output path.")
    parser.add_argument("--frame-output-dir", type=Path, default=Path("workspace/temp/vision_frames"))
    parser.add_argument("--max-frames", type=int, default=3)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dry-run", action="store_true", help="Skip API call and return heuristic tags.")
    parser.add_argument("--rate-state", type=Path, default=DEFAULT_RATE_STATE)
    parser.add_argument("--rpm-limit", type=int, default=DEFAULT_RPM_LIMIT)
    parser.add_argument("--input-tpm-limit", type=int, default=DEFAULT_INPUT_TPM_LIMIT)
    parser.add_argument("--rpd-limit", type=int, default=DEFAULT_RPD_LIMIT)
    parser.add_argument("--image-token-estimate", type=int, default=DEFAULT_IMAGE_TOKEN_ESTIMATE)
    args = parser.parse_args()

    if args.video:
        candidates = extract_video_frames(args.video, args.frame_output_dir, args.max_frames)
    else:
        candidates = prepare_frame_inputs(args.frames)

    if args.dry_run:
        ai_result = dry_run_result(candidates)
    else:
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("Set GEMINI_API_KEY before running without --dry-run.")
        estimated_input_tokens = estimate_input_tokens(
            candidates,
            image_token_estimate=args.image_token_estimate,
        )
        now = time.time()
        state = prune_rate_state(load_rate_state(args.rate_state), now)
        try:
            check_rate_limits(
                state,
                estimated_input_tokens=estimated_input_tokens,
                now=now,
                rpm_limit=args.rpm_limit,
                input_tpm_limit=args.input_tpm_limit,
                rpd_limit=args.rpd_limit,
            )
            ai_result = call_gemini(candidates, api_key=api_key, model=args.model)
            record_rate_usage(
                args.rate_state,
                state,
                model=args.model,
                source=str(args.video) if args.video else "direct_frames",
                input_tokens=estimated_input_tokens,
                now=now,
            )
        except RateLimitExceeded as error:
            payload = {
                "model": args.model,
                "source": str(args.video) if args.video else "direct_frames",
                "status": "rate_limited",
                "wait_seconds": error.wait_seconds,
                "message": str(error),
                "frames_sent": [asdict(candidate) for candidate in candidates],
            }
            write_output(args.output, payload)
            print(f"Rate limited. Wrote {args.output}. Wait about {error.wait_seconds}s.")
            raise SystemExit(2) from None

    payload = {
        "model": args.model,
        "source": str(args.video) if args.video else "direct_frames",
        "status": "ok",
        "frames_sent": [asdict(candidate) for candidate in candidates],
        "ai_result": ai_result,
    }
    write_output(args.output, payload)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
