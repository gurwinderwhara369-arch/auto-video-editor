from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.web.webapp.jobs import (
    ROOT,
    UPLOADS_DIR,
    JobConfig,
    create_job,
    list_jobs,
    load_status,
    media_href,
    new_job_id,
    resolve_workspace_path,
    safe_media_path,
)

app = FastAPI(title="Tattoo Reel Studio")
WEBAPP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEBAPP_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(WEBAPP_DIR / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        context={
            "request": request,
            "jobs": list_jobs()[:8],
            "defaults": {
                "trend_path": "assets/reference_trends/Montagem Tentana Trend 1.mp4",
                "clips_path": "assets/sample_raw_clips/tattoo_process",
                "metadata_path": "workspace/jobs/tattoo_raw/enriched_clip_metadata.json",
                "moments_path": "workspace/jobs/tattoo_raw/moment_metadata.json",
                "output_name": "final_selected_tattoo_reel.mp4",
            },
        },
    )


@app.post("/jobs")
async def create_render_job(
    trend_path: str = Form(""),
    clips_path: str = Form(""),
    metadata_path: str = Form(""),
    moments_path: str = Form(""),
    output_name: str = Form("final_selected_tattoo_reel.mp4"),
    trend_upload: UploadFile | None = File(None),
    clip_uploads: list[UploadFile] | None = File(None),
) -> RedirectResponse:
    job_id = new_job_id()
    upload_dir = UPLOADS_DIR / job_id
    trend_video = resolve_workspace_path(trend_path)
    clips_dir = resolve_workspace_path(clips_path)

    if trend_upload and trend_upload.filename:
        trend_video = await _save_upload(trend_upload, upload_dir / "trend")
    if clip_uploads:
        saved_clips = []
        for upload in clip_uploads:
            if upload.filename:
                saved_clips.append(await _save_upload(upload, upload_dir / "clips"))
        if saved_clips:
            clips_dir = (upload_dir / "clips").resolve()

    if trend_video is None or clips_dir is None:
        raise HTTPException(status_code=400, detail="Provide a trend video and tattoo clips folder or uploads.")

    config = JobConfig(
        trend_video=trend_video,
        clips_dir=clips_dir,
        output_name=output_name or "final_selected_tattoo_reel.mp4",
        metadata_path=resolve_workspace_path(metadata_path),
        moments_path=resolve_workspace_path(moments_path),
    )
    try:
        create_job(config, job_id=job_id, autostart=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_status_page(request: Request, job_id: str) -> HTMLResponse:
    try:
        status = load_status(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    return templates.TemplateResponse(request, "job.html", context={"request": request, "job": status})


@app.get("/jobs/{job_id}/results", response_class=HTMLResponse)
async def job_results_page(request: Request, job_id: str) -> HTMLResponse:
    try:
        status = load_status(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    if status.get("status") != "completed":
        return templates.TemplateResponse(request, "job.html", context={"request": request, "job": status})

    artifacts = status.get("artifacts", {})
    qa_report = _load_json_artifact(artifacts.get("qa_report"))
    return templates.TemplateResponse(
        request,
        "results.html",
        context={
            "request": request,
            "job": status,
            "artifacts": artifacts,
            "qa_report": qa_report,
            "media_href": _media_href_or_none,
        },
    )


@app.get("/api/jobs/{job_id}")
async def job_status_api(job_id: str) -> dict:
    try:
        return load_status(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc


@app.get("/media/{path:path}")
async def media(path: str) -> FileResponse:
    try:
        file_path = safe_media_path(path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Media not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return FileResponse(file_path)


async def _save_upload(upload: UploadFile, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(upload.filename or "upload.bin").name
    target = (target_dir / safe_name).resolve()
    with target.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)
    return target


def _load_json_artifact(path_value: str | None) -> dict | None:
    if not path_value:
        return None
    path = resolve_workspace_path(path_value)
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _media_href_or_none(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = resolve_workspace_path(path_value)
    if not path or not path.exists():
        return None
    return media_href(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Tattoo Reel Studio web UI.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run("app.web.webapp.server:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
