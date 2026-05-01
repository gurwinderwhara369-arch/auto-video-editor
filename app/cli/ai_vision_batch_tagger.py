from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

from ai_vision_tagger import (
    DEFAULT_IMAGE_TOKEN_ESTIMATE,
    DEFAULT_INPUT_TPM_LIMIT,
    DEFAULT_MODEL,
    DEFAULT_RATE_STATE,
    DEFAULT_RPD_LIMIT,
    DEFAULT_RPM_LIMIT,
    RateLimitExceeded,
    call_gemini,
    dry_run_result,
    estimate_input_tokens,
    extract_video_frames,
    load_rate_state,
    prune_rate_state,
    record_rate_usage,
    write_output,
    check_rate_limits,
)
from app.engine.analyzer.clip_probe import list_video_files


def is_complete_tag_file(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return payload.get("status") == "ok" and isinstance(payload.get("ai_result"), dict)


def tag_video_with_retries(
    video_path: Path,
    *,
    output_path: Path,
    frame_output_dir: Path,
    api_key: str,
    model: str,
    max_frames: int,
    rate_state: Path,
    rpm_limit: int,
    input_tpm_limit: int,
    rpd_limit: int,
    image_token_estimate: int,
    dry_run: bool,
    max_attempts: int,
) -> None:
    frame_dir = frame_output_dir / video_path.stem
    candidates = extract_video_frames(video_path, frame_dir, max_frames)
    if dry_run:
        payload = {
            "model": model,
            "source": str(video_path),
            "status": "ok",
            "frames_sent": [asdict(candidate) for candidate in candidates],
            "ai_result": dry_run_result(candidates),
        }
        write_output(output_path, payload)
        return

    estimated_input_tokens = estimate_input_tokens(
        candidates,
        image_token_estimate=image_token_estimate,
    )
    attempt = 0
    while True:
        attempt += 1
        now = time.time()
        state = prune_rate_state(load_rate_state(rate_state), now)
        try:
            check_rate_limits(
                state,
                estimated_input_tokens=estimated_input_tokens,
                now=now,
                rpm_limit=rpm_limit,
                input_tpm_limit=input_tpm_limit,
                rpd_limit=rpd_limit,
            )
            ai_result = call_gemini(candidates, api_key=api_key, model=model)
            record_rate_usage(
                rate_state,
                state,
                model=model,
                source=str(video_path),
                input_tokens=estimated_input_tokens,
                now=now,
            )
            payload = {
                "model": model,
                "source": str(video_path),
                "status": "ok",
                "frames_sent": [asdict(candidate) for candidate in candidates],
                "ai_result": ai_result,
            }
            write_output(output_path, payload)
            return
        except RateLimitExceeded as error:
            if attempt >= max_attempts:
                payload = {
                    "model": model,
                    "source": str(video_path),
                    "status": "rate_limited",
                    "wait_seconds": error.wait_seconds,
                    "message": str(error),
                    "frames_sent": [asdict(candidate) for candidate in candidates],
                }
                write_output(output_path, payload)
                raise
            wait = max(1, error.wait_seconds)
            print(f"Rate limited for {video_path.name}. Waiting {wait}s before retry {attempt + 1}.")
            time.sleep(wait)


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch tag tattoo clips with Gemini/Gemma vision.")
    parser.add_argument("--clips", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frame-output-dir", type=Path, default=Path("workspace/temp/vision_frames"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-frames", type=int, default=3)
    parser.add_argument("--rate-state", type=Path, default=DEFAULT_RATE_STATE)
    parser.add_argument("--rpm-limit", type=int, default=DEFAULT_RPM_LIMIT)
    parser.add_argument("--input-tpm-limit", type=int, default=DEFAULT_INPUT_TPM_LIMIT)
    parser.add_argument("--rpd-limit", type=int, default=DEFAULT_RPD_LIMIT)
    parser.add_argument("--image-token-estimate", type=int, default=DEFAULT_IMAGE_TOKEN_ESTIMATE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-attempts", type=int, default=6)
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not args.dry_run and not api_key:
        raise RuntimeError("Set GEMINI_API_KEY before running without --dry-run.")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    files = list_video_files(args.clips)
    if not files:
        raise ValueError(f"No video files found in {args.clips}")

    for index, video_path in enumerate(files, start=1):
        output_path = args.output_dir / f"{video_path.stem}_gemma_tags.json"
        if is_complete_tag_file(output_path):
            print(f"[{index}/{len(files)}] Skipping complete {output_path}")
            continue
        if output_path.exists():
            print(f"[{index}/{len(files)}] Retrying incomplete {output_path}")
        else:
            print(f"[{index}/{len(files)}] Tagging {video_path.name}")
        tag_video_with_retries(
            video_path,
            output_path=output_path,
            frame_output_dir=args.frame_output_dir,
            api_key=api_key or "",
            model=args.model,
            max_frames=args.max_frames,
            rate_state=args.rate_state,
            rpm_limit=args.rpm_limit,
            input_tpm_limit=args.input_tpm_limit,
            rpd_limit=args.rpd_limit,
            image_token_estimate=args.image_token_estimate,
            dry_run=args.dry_run,
            max_attempts=args.max_attempts,
        )
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
