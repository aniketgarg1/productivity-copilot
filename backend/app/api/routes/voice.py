"""Voice input: accept audio, transcribe with OpenAI Whisper, then create schedule."""

import os
import tempfile

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(prefix="/voice")

ALLOWED_AUDIO_TYPES = {
    "audio/wav", "audio/mpeg", "audio/mp3", "audio/mp4",
    "audio/webm", "audio/ogg", "audio/flac", "audio/m4a",
}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB (Whisper limit)


async def _transcribe(audio: UploadFile) -> str:
    from openai import OpenAI

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")

    content = await audio.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Audio file exceeds 25 MB limit")

    suffix = os.path.splitext(audio.filename or "audio.webm")[1] or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        client = OpenAI(api_key=api_key)
        with open(tmp_path, "rb") as f:
            transcript = client.audio.transcriptions.create(model="whisper-1", file=f)
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
    audio: UploadFile = File(...),
    horizon_days: int = Form(30),
    request: Request = None,
    db: Session = Depends(get_db),
):
    """
    Accept a voice recording describing a goal, transcribe it,
    generate a roadmap, and schedule tasks on Google Calendar.
    Reuses the existing schedule pipeline.
    """
    text = await _transcribe(audio)
    if not text or not text.strip():
        raise HTTPException(status_code=422, detail="Could not transcribe any speech from the audio")

    from app.api.routes.schedule import schedule_goal, ScheduleRequest

    fake_req = ScheduleRequest(goal=text, horizon_days=horizon_days)
    result = await schedule_goal(fake_req, request, db)

    return {"transcription": text, **result}
