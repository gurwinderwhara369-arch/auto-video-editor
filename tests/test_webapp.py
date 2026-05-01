from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.web.webapp.jobs import JobConfig, create_job, load_status, run_job, safe_media_path
from app.web.webapp.server import app


def test_home_page_loads() -> None:
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert "Render a trend-style tattoo reel" in response.text


def test_safe_media_path_rejects_outside_workspace() -> None:
    with pytest.raises(ValueError):
        safe_media_path("/etc/passwd")


def test_dry_run_job_creates_status_and_artifacts(tmp_path: Path) -> None:
    trend = tmp_path / "trend.mp4"
    clips = tmp_path / "clips"
    clips.mkdir()
    trend.write_bytes(b"fake")
    (clips / "clip.mp4").write_bytes(b"fake")
    config = JobConfig(
        trend_video=trend,
        clips_dir=clips,
        output_name="final.mp4",
        dry_run=True,
    )

    job_id = create_job(config, job_id="test_dry_run_job", autostart=False)
    run_job(job_id, config)
    status = load_status(job_id)

    assert status["status"] == "completed"
    assert status["artifacts"]["qa_report"].endswith("qa_report.json")
