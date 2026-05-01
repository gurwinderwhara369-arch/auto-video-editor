from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def remove_background(
    input_path: Path,
    output_path: Path,
    *,
    method: str = "auto",
    iterations: int = 5,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if method in {"auto", "rembg"} and _try_rembg(input_path, output_path):
        return
    _remove_with_grabcut(input_path, output_path, iterations=iterations)


def _try_rembg(input_path: Path, output_path: Path) -> bool:
    try:
        from rembg import remove
    except Exception:
        return False
    data = input_path.read_bytes()
    output_path.write_bytes(remove(data))
    return True


def _remove_with_grabcut(input_path: Path, output_path: Path, *, iterations: int) -> None:
    image = cv2.imread(str(input_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Could not read image: {input_path}")

    height, width = image.shape[:2]
    inset_x = max(2, int(width * 0.07))
    inset_y = max(2, int(height * 0.05))
    rect = (inset_x, inset_y, width - inset_x * 2, height - inset_y * 2)
    mask = np.zeros((height, width), np.uint8)
    background_model = np.zeros((1, 65), np.float64)
    foreground_model = np.zeros((1, 65), np.float64)
    cv2.grabCut(
        image,
        mask,
        rect,
        background_model,
        foreground_model,
        max(1, iterations),
        cv2.GC_INIT_WITH_RECT,
    )
    alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
    alpha = cv2.medianBlur(alpha, 5)
    rgba = cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = alpha
    cv2.imwrite(str(output_path), rgba)


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove image background with rembg when available, otherwise OpenCV GrabCut.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--method", choices=["auto", "rembg", "grabcut"], default="auto")
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()

    if args.method == "grabcut":
        _remove_with_grabcut(args.input, args.output, iterations=args.iterations)
    else:
        remove_background(args.input, args.output, method=args.method, iterations=args.iterations)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
