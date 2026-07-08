import json
import logging
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML


logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def generate_pdf(meeting, transcript_segments, summary, tasks) -> bytes:
    """Генерация PDF-отчёта по совещанию."""
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("report.html")

    # Format duration
    duration_str = ""
    if meeting.duration_seconds:
        mins = int(meeting.duration_seconds // 60)
        secs = int(meeting.duration_seconds % 60)
        if mins > 60:
            hours = mins // 60
            mins = mins % 60
            duration_str = f"{hours}ч {mins}мин"
        else:
            duration_str = f"{mins}мин {secs}с"

    # Get unique speakers
    speakers = list(set(seg.speaker_label for seg in transcript_segments))

    # Parse key_decisions
    key_decisions = []
    if summary and summary.key_decisions:
        try:
            key_decisions = json.loads(summary.key_decisions)
        except json.JSONDecodeError:
            pass

    # Parse topics
    topics = []
    if summary and summary.topics:
        try:
            topics = json.loads(summary.topics)
        except json.JSONDecodeError:
            pass

    # Format transcript segments
    formatted_segments = []
    for seg in transcript_segments:
        start = _fmt(seg.start_time)
        end = _fmt(seg.end_time)
        formatted_segments.append({
            "speaker": seg.speaker_label,
            "text": seg.text,
            "time": f"{start} - {end}",
        })

    html_content = template.render(
        title=meeting.title,
        date=meeting.date.strftime("%d.%m.%Y %H:%M") if meeting.date else "—",
        duration=duration_str,
        speakers=speakers,
        brief=summary.brief if summary else "",
        summary_text=summary.summary_text if summary else "",
        key_decisions=key_decisions,
        topics=topics,
        tasks=tasks,
        segments=formatted_segments,
    )

    pdf = HTML(string=html_content).write_pdf()
    logger.info(f"PDF сгенерирован для совещания {meeting.id}")
    return pdf


def _fmt(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
