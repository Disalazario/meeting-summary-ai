# Meeting Summary AI

Self-hosted meeting assistant: a bot joins your video call, records it, and turns it into a transcript, summary, action items, and a searchable archive — **entirely on local models**. No audio or text ever leaves your server.

```
video call ──▶ Playwright bot (records) ──▶ Whisper large-v3 (transcribe)
           ──▶ pyannote (speaker diarization) ──▶ Ollama LLM (summary / tasks / topics)
           ──▶ web app + Telegram Mini App + PDF export
```

## Why local

Meeting audio is some of the most sensitive data a company has. This stack runs Whisper, pyannote, and the LLM (Ollama) on a single GPU with VRAM orchestration — ASR is unloaded before the LLM starts — so a consumer card (8 GB) handles the full pipeline.

## Features

- **Autonomous recording bot** — Playwright-driven headless Chromium joins a meeting by link, records, and leaves when the room is empty; up to 3 bots in parallel
- **Transcription + diarization** — Whisper large-v3 with pyannote speaker labels ("who said what")
- **LLM analysis** — summary, key decisions, action items with assignees and deadlines, topic extraction; structured JSON output validated at every step
- **Chat with the meeting** — ask questions against the transcript
- **Telegram delivery** — bot notifications plus a full Telegram Mini App frontend
- **Integrations** — task tracker export (Planfix; CRM/VPBX adapters stubbed)
- **Prompt evals** — promptfoo suites for the summary, tasks, and topics prompts with JSON-validity and LLM-rubric checks (`evals/`)

## Stack

**Backend:** Python, FastAPI, SQLAlchemy + Alembic, Whisper, pyannote, Ollama, Playwright
**Frontend:** React + Vite, Telegram Mini App
**Ops:** GitLab CI (ruff, eslint, build), deploy scripts, nginx config

## Quick start

```bash
cp .env.example .env        # set SECRET_KEY, HUGGINGFACE_TOKEN, TELEGRAM_BOT_TOKEN
ollama pull qwen2.5:7b

cd backend && pip install -r requirements.txt && alembic upgrade head
uvicorn app.main:app --reload &

cd ../frontend && npm install && npm run dev
```

See `deploy/` for production setup and `evals/README.md` for running the prompt evaluation suites.
