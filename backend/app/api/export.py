import json
from html import escape as html_escape

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.meeting import Meeting
from app.models.transcript import TranscriptSegment
from app.models.summary import Summary
from app.models.task import Task
from app.models.user import User
from app.services.auth_service import get_current_user

router = APIRouter()


@router.get("/{meeting_id}/export/pdf")
async def export_pdf(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Check ownership
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Совещание не найдено")

    if meeting.status != "done":
        raise HTTPException(status_code=400, detail="Совещание ещё обрабатывается")

    # Get data
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_time)
    )
    segments = result.scalars().all()

    result = await db.execute(select(Summary).where(Summary.meeting_id == meeting_id))
    summary = result.scalar_one_or_none()

    result = await db.execute(
        select(Task).where(Task.meeting_id == meeting_id).order_by(Task.id)
    )
    tasks = result.scalars().all()

    # Generate PDF
    from app.services.pdf_service import generate_pdf
    pdf_bytes = generate_pdf(meeting, segments, summary, tasks)

    from urllib.parse import quote
    safe_title = meeting.title[:30].replace(' ', '_')
    filename_ascii = f"report_{meeting.id}.pdf"
    filename_utf8 = quote(f"report_{safe_title}.pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename_ascii}"; '
                f"filename*=UTF-8''{filename_utf8}"
            )
        },
    )


def _fmt_duration(seconds: float | None) -> str:
    """Форматирование длительности в человекочитаемый вид."""
    if not seconds:
        return "—"
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins > 60:
        hours = mins // 60
        mins = mins % 60
        return f"{hours} ч {mins} мин"
    return f"{mins} мин {secs} с"


def _fmt_time(seconds: float) -> str:
    """Форматирование времени в MM:SS или HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


# ──────────────────────────────────────────────
# Тема-цвета для тегов (повторяемые)
# ──────────────────────────────────────────────
_TAG_COLORS = [
    ("#ebf4ff", "#2b6cb0", "#bee3f8"),
    ("#f0fff4", "#276749", "#c6f6d5"),
    ("#fffff0", "#975a16", "#fefcbf"),
    ("#fff5f5", "#c53030", "#fed7d7"),
    ("#faf5ff", "#6b46c1", "#e9d8fd"),
    ("#fffaf0", "#c05621", "#feebc8"),
    ("#e6fffa", "#285e61", "#b2f5ea"),
]


@router.get("/{meeting_id}/report")
async def meeting_report(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Генерация самодостаточного HTML-отчёта по совещанию."""
    # Check ownership
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Совещание не найдено")

    if meeting.status != "done":
        raise HTTPException(status_code=400, detail="Совещание ещё обрабатывается")

    # Load data
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_time)
    )
    segments = result.scalars().all()

    result = await db.execute(select(Summary).where(Summary.meeting_id == meeting_id))
    summary = result.scalar_one_or_none()

    result = await db.execute(
        select(Task).where(Task.meeting_id == meeting_id).order_by(Task.id)
    )
    tasks = result.scalars().all()

    # ── Parse JSON fields ──
    key_decisions: list[str] = []
    if summary and summary.key_decisions:
        try:
            key_decisions = json.loads(summary.key_decisions)
        except json.JSONDecodeError:
            pass

    topics: list[str] = []
    if summary and summary.topics:
        try:
            topics = json.loads(summary.topics)
        except json.JSONDecodeError:
            pass

    # ── Speaker statistics ──
    speaker_chars: dict[str, int] = {}
    for seg in segments:
        speaker_chars[seg.speaker_label] = speaker_chars.get(seg.speaker_label, 0) + len(seg.text)
    total_chars = max(sum(speaker_chars.values()), 1)
    speaker_stats = sorted(speaker_chars.items(), key=lambda x: x[1], reverse=True)

    # ── Participant info ──
    participant_names: list[str] = []
    if meeting.participant_names:
        try:
            participant_names = json.loads(meeting.participant_names)
        except json.JSONDecodeError:
            pass
    if not participant_names:
        participant_names = list(speaker_chars.keys())

    # ── Format date ──
    date_str = meeting.date.strftime("%d.%m.%Y %H:%M") if meeting.date else "—"
    duration_str = _fmt_duration(meeting.duration_seconds)

    # ── Build topic tags HTML ──
    topics_html = ""
    if topics:
        tags = []
        for i, topic in enumerate(topics):
            bg, fg, border = _TAG_COLORS[i % len(_TAG_COLORS)]
            tags.append(
                f'<span style="display:inline-block;background:{bg};color:{fg};'
                f'border:1px solid {border};border-radius:14px;padding:3px 12px;'
                f'font-size:13px;margin:3px 5px 3px 0;">{html_escape(topic)}</span>'
            )
        topics_html = "\n".join(tags)

    # ── Build key decisions HTML ──
    decisions_html = ""
    if key_decisions:
        items = "".join(
            f'<li style="margin-bottom:6px;">{html_escape(d)}</li>' for d in key_decisions
        )
        decisions_html = f'<ol style="padding-left:22px;margin:8px 0;">{items}</ol>'

    # ── Build tasks table HTML ──
    tasks_html = ""
    if tasks:
        rows = []
        for idx, t in enumerate(tasks, 1):
            row_bg = "#f7fafc" if idx % 2 == 0 else "#ffffff"
            status_color = "#276749" if t.done else "#c05621"
            status_text = "Выполнено" if t.done else "В работе"
            desc_style = "text-decoration:line-through;color:#a0aec0;" if t.done else ""
            rows.append(
                f'<tr style="background:{row_bg};">'
                f'<td style="padding:8px 10px;border:1px solid #e2e8f0;text-align:center;">{idx}</td>'
                f'<td style="padding:8px 10px;border:1px solid #e2e8f0;{desc_style}">{html_escape(t.description)}</td>'
                f'<td style="padding:8px 10px;border:1px solid #e2e8f0;">{html_escape(t.assignee or "—")}</td>'
                f'<td style="padding:8px 10px;border:1px solid #e2e8f0;">{html_escape(t.deadline or "—")}</td>'
                f'<td style="padding:8px 10px;border:1px solid #e2e8f0;color:{status_color};font-weight:bold;">{status_text}</td>'
                f'</tr>'
            )
        tasks_html = (
            '<table style="width:100%;border-collapse:collapse;margin:10px 0;">'
            '<thead><tr>'
            '<th style="background:#2c5282;color:white;padding:8px 10px;border:1px solid #2c5282;width:5%;text-align:center;">№</th>'
            '<th style="background:#2c5282;color:white;padding:8px 10px;border:1px solid #2c5282;width:40%;text-align:left;">Описание</th>'
            '<th style="background:#2c5282;color:white;padding:8px 10px;border:1px solid #2c5282;width:20%;text-align:left;">Ответственный</th>'
            '<th style="background:#2c5282;color:white;padding:8px 10px;border:1px solid #2c5282;width:15%;text-align:left;">Срок</th>'
            '<th style="background:#2c5282;color:white;padding:8px 10px;border:1px solid #2c5282;width:15%;text-align:left;">Статус</th>'
            '</tr></thead><tbody>'
            + "".join(rows)
            + '</tbody></table>'
        )

    # ── Build speaker chart HTML ──
    bar_colors = ["#3182ce", "#38a169", "#d69e2e", "#e53e3e", "#805ad5", "#dd6b20", "#319795"]
    speaker_bars = []
    for i, (speaker, chars) in enumerate(speaker_stats):
        pct = round(chars / total_chars * 100, 1)
        color = bar_colors[i % len(bar_colors)]
        speaker_bars.append(
            f'<div style="margin-bottom:10px;">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:3px;">'
            f'<span style="font-weight:600;color:#2d3748;">{html_escape(speaker)}</span>'
            f'<span style="color:#718096;font-size:13px;">{pct}%</span>'
            f'</div>'
            f'<div style="background:#edf2f7;border-radius:6px;height:22px;overflow:hidden;">'
            f'<div style="background:{color};height:100%;width:{pct}%;border-radius:6px;'
            f'min-width:2px;transition:width 0.3s;"></div>'
            f'</div>'
            f'</div>'
        )
    speaker_chart_html = "\n".join(speaker_bars)

    # ── Assemble full HTML ──
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html_escape(meeting.title)} — Отчёт</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Segoe UI','Helvetica Neue',Arial,sans-serif;color:#2d3748;line-height:1.6;">

<div style="max-width:900px;margin:0 auto;background:#ffffff;box-shadow:0 1px 8px rgba(0,0,0,0.08);min-height:100vh;">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1a365d 0%,#2c5282 100%);color:white;padding:32px 40px 28px;">
    <h1 style="margin:0 0 8px;font-size:26px;font-weight:700;">{html_escape(meeting.title)}</h1>
    <div style="display:flex;flex-wrap:wrap;gap:20px;font-size:14px;opacity:0.9;">
      <span>&#128197; {date_str}</span>
      <span>&#9200; {duration_str}</span>
      <span>&#128101; {len(participant_names)} участник(ов)</span>
    </div>
    {('<div style="margin-top:12px;">' + topics_html + '</div>') if topics_html else ''}
  </div>

  <div style="padding:30px 40px;">

    <!-- Участники -->
    <div style="margin-bottom:24px;padding:14px 18px;background:#f7fafc;border:1px solid #e2e8f0;border-radius:6px;">
      <div style="font-weight:600;color:#2c5282;margin-bottom:6px;font-size:14px;">Участники</div>
      <div style="color:#4a5568;font-size:14px;">{html_escape(', '.join(participant_names)) if participant_names else '—'}</div>
    </div>

    <!-- Краткий пересказ -->
    {f'''<div style="margin-bottom:28px;">
      <h2 style="font-size:18px;color:#1a365d;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #bee3f8;">Краткий пересказ</h2>
      <div style="background:#ebf8ff;border-left:4px solid #3182ce;padding:14px 18px;border-radius:0 6px 6px 0;font-size:15px;line-height:1.7;">
        {html_escape(summary.brief)}
      </div>
    </div>''' if summary and summary.brief else ''}

    <!-- Подробное саммари -->
    {f'''<div style="margin-bottom:28px;">
      <h2 style="font-size:18px;color:#1a365d;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #bee3f8;">Подробное саммари</h2>
      <div style="font-size:14px;line-height:1.8;text-align:justify;">
        {html_escape(summary.summary_text)}
      </div>
    </div>''' if summary and summary.summary_text else ''}

    <!-- Ключевые решения -->
    {f'''<div style="margin-bottom:28px;">
      <h2 style="font-size:18px;color:#1a365d;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #bee3f8;">Ключевые решения</h2>
      {decisions_html}
    </div>''' if key_decisions else ''}

    <!-- Задачи -->
    {f'''<div style="margin-bottom:28px;">
      <h2 style="font-size:18px;color:#1a365d;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #bee3f8;">Задачи ({len(tasks)})</h2>
      {tasks_html}
    </div>''' if tasks else ''}

    <!-- Участие спикеров -->
    {f'''<div style="margin-bottom:28px;">
      <h2 style="font-size:18px;color:#1a365d;margin:0 0 12px;padding-bottom:8px;border-bottom:2px solid #bee3f8;">Участие спикеров</h2>
      <div style="padding:16px 20px;background:#f7fafc;border-radius:8px;border:1px solid #e2e8f0;">
        {speaker_chart_html}
      </div>
    </div>''' if speaker_stats else ''}

    <!-- Footer -->
    <div style="margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0;text-align:center;font-size:12px;color:#a0aec0;">
      Отчёт сгенерирован автоматически — Meeting Summary AI
    </div>

  </div>
</div>

</body>
</html>"""

    return HTMLResponse(content=html)
