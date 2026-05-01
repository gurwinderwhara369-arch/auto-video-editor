from pathlib import Path

import cv2
import numpy as np

from app.engine.analyzer.background_remover import remove_background


def test_grabcut_background_remover_writes_alpha_png(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "cutout.png"
    image = np.full((120, 90, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (25, 25), (65, 95), (20, 20, 20), -1)
    cv2.imwrite(str(source), image)

    remove_background(source, output, method="grabcut", iterations=1)

    result = cv2.imread(str(output), cv2.IMREAD_UNCHANGED)
    assert result is not None
    assert result.shape[2] == 4
    assert result[:, :, 3].max() == 255
