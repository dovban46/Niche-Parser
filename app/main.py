import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .config import IMAGE_PROVIDER, LLM_PROVIDER, STORAGE_ROOT, TTS_PROVIDER, VIDEO_PROVIDER, VIDEOS_ROOT
from .jobs import repository as repo
from .jobs import service
from .jobs.runner import start_worker
from .providers.base import ProviderConfigError
from .schemas import (
    STAGE_LABELS,
    STAGE_ORDER,
    SUPPORTED_LANGUAGES,
    JobCreateRequest,
    JobDetail,
    JobSummary,
    DossierSaveRequest,
    ScriptReviseRequest,
    VoicePreviewRequest,
)
from .styles import DEFAULT_STYLE_ID, STYLES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    recovered = repo.mark_running_jobs_failed_on_startup()
    if recovered:
        logging.getLogger("video_factory.main").warning(
            "%s job(ів) перервано попереднім рестартом сервера — позначено failed.", recovered
        )
    start_worker()
    yield


# StaticFiles падає на старті, якщо теки немає (свіжий клон: storage/ і videos/ у .gitignore).
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
VIDEOS_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Video Factory", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/storage", StaticFiles(directory=STORAGE_ROOT), name="storage")
app.mount("/videos", StaticFiles(directory=VIDEOS_ROOT), name="videos")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _static_version() -> str:
    try:
        mtimes = [(STATIC_DIR / f).stat().st_mtime for f in ("app.js", "style.css")]
        return str(int(max(mtimes)))
    except OSError:
        return "0"


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "static_version": _static_version(),
            "llm_provider": LLM_PROVIDER,
            "tts_provider": TTS_PROVIDER,
            "image_provider": IMAGE_PROVIDER,
            "video_provider": VIDEO_PROVIDER,
            "styles": [(s.id, s.label, s.description) for s in STYLES.values()],
            "default_style": DEFAULT_STYLE_ID,
            "languages": list(SUPPORTED_LANGUAGES.items()),
        },
    )


@app.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(request: Request, job_id: int):
    detail = service.get_job_detail(job_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Job не знайдено.")
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {"job_id": job_id, "stage_order": STAGE_ORDER, "static_version": _static_version()},
    )


@app.post("/api/jobs")
def api_create_job(req: JobCreateRequest):
    job_id = service.create_job(
        req.topic, req.niche, req.target_duration_minutes, req.language, req.voice_id,
        req.style_id, req.preview_seconds, req.auto_dossier,
    )
    return {"id": job_id}


@app.get("/api/jobs", response_model=list[JobSummary])
def api_list_jobs():
    return service.list_jobs()


@app.get("/api/jobs/{job_id}", response_model=JobDetail)
def api_get_job(job_id: int):
    detail = service.get_job_detail(job_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Job не знайдено.")
    return detail


@app.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: int):
    try:
        if not service.delete_job(job_id):
            raise HTTPException(status_code=404, detail="Job не знайдено.")
    except service.JobBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.JobDeleteError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"deleted": True}


@app.get("/api/voices")
def api_voices(language: str = "uk"):
    if language not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Непідтримувана мова '{language}'.")
    return service.list_voices(language)


@app.post("/api/voices/preview")
def api_voice_preview(req: VoicePreviewRequest):
    try:
        url = service.preview_voice(req.language, req.voice_id)
    except ProviderConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"url": url}


@app.post("/api/jobs/{job_id}/retry")
def api_retry_job(job_id: int):
    if not service.retry_job(job_id):
        raise HTTPException(status_code=404, detail="Job не знайдено.")
    return {"retried": True}


@app.put("/api/jobs/{job_id}/dossier")
def api_dossier_save(job_id: int, req: DossierSaveRequest):
    if not service.save_dossier(job_id, req.text):
        raise HTTPException(status_code=400, detail="Досьє можна правити лише поки job чекає на його перевірку.")
    return {"saved": True}


@app.post("/api/jobs/{job_id}/dossier/approve")
def api_dossier_approve(job_id: int):
    if not service.approve_dossier(job_id):
        raise HTTPException(status_code=400, detail="Job не чекає на схвалення досьє (або не знайдено).")
    return {"approved": True}


@app.post("/api/jobs/{job_id}/script/approve")
def api_script_approve(job_id: int):
    if not service.approve_script(job_id):
        raise HTTPException(
            status_code=400, detail="Job не в стані очікування перевірки сценарію (або не знайдено)."
        )
    return {"approved": True}


@app.post("/api/jobs/{job_id}/script/revise")
def api_script_revise(job_id: int, req: ScriptReviseRequest):
    try:
        revised = service.revise_script(job_id, req.feedback)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"script_text": revised}


@app.get("/api/llm-usage")
def api_llm_usage():
    """Реальне використання Anthropic API (токени/вартість) за час роботи процесу."""
    from .providers.llm.usage import usage_tracker

    return usage_tracker.summary()


@app.get("/api/stage-labels")
def api_stage_labels():
    return STAGE_LABELS
