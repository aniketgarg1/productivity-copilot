"""Voice input: accept audio, transcribe with OpenAI Whisper, then create schedule."""

import os
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(prefix="/voice")

ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3", "audio/mp4",
    "audio/webm", "audio/ogg", "audio/flac", "audio/m4a", "audio/x-m4a",
    "video/webm",  # what MediaRecorder produces in some browsers
}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB (Whisper limit)


async def _transcribe(audio: UploadFile) -> str:
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio type {content_type!r}. Allowed: {', '.join(sorted(ALLOWED_AUDIO_TYPES))}",
        )

    # Reject oversized uploads before buffering the whole body in memory.
    if audio.size is not None and audio.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25 MB limit")

    content = await audio.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty audio upload")
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25 MB limit")

    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, timeout=120.0)
        with open(tmp_path, "rb") as f:
            transcript = await client.audio.transcriptions.create(
                model=settings.OPENAI_TRANSCRIBE_MODEL, file=f
            )
        return transcript.text
    finally:
        os.unlink(tmp_path)


@router.post("/transcribe")
async def transcribe_audio(audio: UploadFile = File(...)):
    """Transcribe audio to text — useful for previewing before scheduling."""
    text = await _transcribe(audio)
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="Could not transcribe any speech from the audio")
    return {"text": text}


@router.post("/goal")
async def voice_goal(
    request: Request,
    audio: UploadFile = File(...),
    horizon_days: int = Form(30),
    daily_hours: float = Form(2.0),
    db: Session = Depends(get_db),
):
    """
    Accept a voice recording describing a goal, transcribe it,
    generate a roadmap, and schedule tasks on Google Calendar.
    Reuses the existing schedule pipeline.
    """
    from app.api.routes.schedule import schedule_goal, ScheduleRequest

    text = await _transcribe(audio)
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="Could not transcribe any speech from the audio")

    result = await schedule_goal(
        ScheduleRequest(goal=text.strip(), horizon_days=horizon_days, daily_hours=daily_hours),
        request,
        db,
    )

    return {"transcription": text, **result}
