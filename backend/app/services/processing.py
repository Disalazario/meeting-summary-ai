import asyncio
import json
import logging
import threading
import time
from pathlib import Path

from sqlalchemy import select

from app.database import async_session
from app.models.meeting import Meeting
from app.models.transcript import TranscriptSegment
from app.models.summary import Summary
from app.models.task import Task
from app.services.audio_service import preprocess_audio

logger = logging.getLogger(__name__)


def _format_timestamp(seconds: float) -> str:
    """Форматирование секунд в MM:SS или HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class PipelineError(Exception):
    """Ошибка пайплайна, текст которой безопасно показывать пользователю."""


def _build_transcript_text(segments: list) -> str:
    """Формирование текста транскрипции для LLM."""
    lines = []
    for seg in segments:
        start = _format_timestamp(seg.start)
        end = _format_timestamp(seg.end)
        lines.append(f"[{start} - {end}] {seg.speaker}:\n{seg.text}\n")
    return "\n".join(lines)


async def _update_status(meeting_id: int, status: str, error_message: str | None = None,
                         progress: int | None = None, eta_seconds: int | None = None):
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
        meeting = result.scalar_one_or_none()
        if meeting:
            meeting.status = status
            if error_message:
                meeting.error_message = error_message
            if progress is not None:
                meeting.processing_progress = progress
            if eta_seconds is not None:
                meeting.processing_eta_seconds = eta_seconds
            await session.commit()
            logger.info(f"[meeting:{meeting_id}] Статус → {status} (progress={progress}%, eta={eta_seconds}s)")


_processing_lock: set[int] = set()
_processing_lock_guard = threading.Lock()  # guards the set for thread safety


# ─────────────────────────────────────────────────────────────────────
# Очередь обработки.
#
# Множество ботов могут писать параллельно (см. BotManager._slots), но
# Whisper + Ollama делят один GPU и хорошо работают только последовательно.
# Поэтому обработка идёт строго через очередь: один воркер берёт по одной
# встрече, гоняет полный пайплайн, потом следующую.
#
# Точка входа: enqueue_meeting_processing(meeting_id) — НЕ блокирует.
# Воркер запускается из main.lifespan через start_processing_worker().
# ─────────────────────────────────────────────────────────────────────

_processing_queue: "asyncio.Queue[int] | None" = None
_processing_worker_task = None


def get_queue_size() -> int:
    """Сколько встреч ждут обработки (без учёта текущей в работе)."""
    if _processing_queue is None:
        return 0
    return _processing_queue.qsize()


async def enqueue_meeting_processing(meeting_id: int) -> int:
    """Поставить встречу в очередь на обработку. Возвращает позицию (1-based).

    Идемпотентно: если встреча уже в очереди или обрабатывается — не дублируется
    (защищено `_processing_lock` внутри process_meeting).
    """
    import asyncio as _asyncio
    global _processing_queue
    if _processing_queue is None:
        _processing_queue = _asyncio.Queue()
    await _processing_queue.put(meeting_id)
    pos = _processing_queue.qsize()
    logger.info(
        f"[meeting:{meeting_id}] Добавлен в очередь обработки (позиция: {pos}, активных воркеров: 1)"
    )
    # Если status='recording' — оставим, его перебьёт _update_status в воркере.
    # Если status='uploaded' — переведём в 'queued' для UI.
    try:
        async with async_session() as session:
            from sqlalchemy import select
            r = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            m = r.scalar_one_or_none()
            if m and m.status in ("uploaded",):
                m.status = "queued"
                await session.commit()
    except Exception as e:
        logger.warning(f"[meeting:{meeting_id}] Не удалось пометить как queued: {e}")
    return pos


async def _processing_worker_loop():
    """Бесконечный цикл: берёт meeting_id из очереди, прогоняет пайплайн."""
    import asyncio as _asyncio
    global _processing_queue
    if _processing_queue is None:
        _processing_queue = _asyncio.Queue()
    logger.info("Processing worker запущен (размер очереди: 0)")
    while True:
        meeting_id = await _processing_queue.get()
        try:
            logger.info(f"[meeting:{meeting_id}] Воркер взял задачу (осталось в очереди: {_processing_queue.qsize()})")
            await process_meeting(meeting_id)
        except Exception as e:
            logger.exception(f"[meeting:{meeting_id}] Воркер: необработанная ошибка: {e}")
        finally:
            _processing_queue.task_done()


def start_processing_worker():
    """Запустить фоновый воркер. Вызывается из main.lifespan."""
    import asyncio as _asyncio
    global _processing_worker_task, _processing_queue
    if _processing_worker_task is not None and not _processing_worker_task.done():
        return _processing_worker_task
    if _processing_queue is None:
        _processing_queue = _asyncio.Queue()
    _processing_worker_task = _asyncio.create_task(_processing_worker_loop())
    return _processing_worker_task


async def recover_stuck_meetings() -> int:
    """Поднять встречи, зависшие в промежуточных статусах после рестарта.

    Два кейса:
    1. Pipeline дошёл до шага 6/6 — в БД уже есть Summary + transcripts, но
       backend упал перед `_update_status('done')`. В этом случае
       пере-обработка не нужна — просто выставляем status='done', данные
       уже все на месте.
    2. Pipeline упал раньше — Summary ещё нет → ставим в очередь на полную
       пере-обработку.

    Это критично: иначе при каждом рестарте backend такие встречи будут
    бесконечно прогоняться через Whisper/Ollama, перезаписывая результаты.
    """
    from app.models.summary import Summary
    STUCK_STATUSES = (
        "uploaded", "queued",
        "processing", "transcribing", "diarizing", "summarizing",
    )
    async with async_session() as session:
        result = await session.execute(
            select(Meeting).where(Meeting.status.in_(STUCK_STATUSES))
        )
        stuck = list(result.scalars().all())
        if not stuck:
            return 0

        # Какие из них уже имеют Summary в БД? — pipeline дошёл до 6/6
        stuck_ids = [m.id for m in stuck]
        s_result = await session.execute(
            select(Summary.meeting_id).where(Summary.meeting_id.in_(stuck_ids))
        )
        already_finalized_ids = {row[0] for row in s_result.all()}

        # Кейс 1: данные есть, статус не обновился — просто допишем 'done'
        if already_finalized_ids:
            from sqlalchemy import update
            await session.execute(
                update(Meeting)
                .where(Meeting.id.in_(already_finalized_ids))
                .values(status="done", processing_progress=100, processing_eta_seconds=0)
            )
            await session.commit()
            logger.info(
                f"Recovery: {len(already_finalized_ids)} встреч имеют Summary в БД, "
                f"проставлен status=done без пере-обработки: {sorted(already_finalized_ids)}"
            )

    # Кейс 2: нужна полная пере-обработка
    to_reprocess = [m for m in stuck if m.id not in already_finalized_ids]
    if not to_reprocess:
        return len(stuck)

    logger.info(
        f"Recovery: {len(to_reprocess)} встреч без Summary, кладу в очередь "
        f"({[m.id for m in to_reprocess]})"
    )
    for m in to_reprocess:
        await enqueue_meeting_processing(m.id)
    return len(stuck)


def _calc_eta(pipeline_start: float, progress: int) -> int | None:
    """Рассчитать примерное оставшееся время (секунды)."""
    if progress <= 0:
        return None
    elapsed = time.time() - pipeline_start
    return int(elapsed / progress * (100 - progress))


async def process_meeting(meeting_id: int):
    """Основной пайплайн обработки совещания."""
    # Защита от двойного запуска (thread-safe)
    with _processing_lock_guard:
        if meeting_id in _processing_lock:
            logger.warning(f"[meeting:{meeting_id}] Обработка уже запущена, пропускаем дубль")
            return
        _processing_lock.add(meeting_id)

    pipeline_start = time.time()
    logger.info(f"[meeting:{meeting_id}] ========== НАЧАЛО ОБРАБОТКИ ==========")

    try:
        # Get meeting info
        async with async_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = result.scalar_one_or_none()
            if not meeting:
                logger.error(f"[meeting:{meeting_id}] Совещание не найдено в БД")
                return
            audio_path = Path(meeting.audio_path)
            participant_names_json = meeting.participant_names
            logger.info(f"[meeting:{meeting_id}] Аудио файл: {audio_path} (существует: {audio_path.exists()})")

        # ── 1. Preprocessing ──
        await _update_status(meeting_id, "processing", progress=0, eta_seconds=None)
        step_start = time.time()
        logger.info(f"[meeting:{meeting_id}] [1/6] Предобработка аудио...")
        wav_path, duration = await preprocess_audio(audio_path)
        logger.info(f"[meeting:{meeting_id}] [1/6] Предобработка завершена за {time.time()-step_start:.1f}с — WAV: {wav_path}, длительность: {duration:.1f}с")

        # Save duration
        async with async_session() as session:
            from sqlalchemy import select
            result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = result.scalar_one()
            meeting.duration_seconds = duration
            await session.commit()

        # ── 2+3. Transcription (GPU) + Diarization (CPU) — параллельно ──
        await _update_status(meeting_id, "transcribing", progress=5, eta_seconds=_calc_eta(pipeline_start, 5))
        step_start = time.time()
        logger.info(f"[meeting:{meeting_id}] [2/6] Транскрибация (faster-whisper, GPU) + диаризация (diarize, CPU) — параллельно...")

        import asyncio
        from app.services.transcription import transcribe, unload_model
        from app.services.diarization import diarize

        whisper_segments, diarization_segments = await asyncio.gather(
            asyncio.to_thread(transcribe, wav_path),
            asyncio.to_thread(diarize, wav_path),
        )
        logger.info(f"[meeting:{meeting_id}] [2/6] Транскрибация + диаризация завершены за {time.time()-step_start:.1f}с")

        if whisper_segments:
            total_text = sum(len(s.text) for s in whisper_segments)
            logger.info(f"[meeting:{meeting_id}]   Транскрибация: {len(whisper_segments)} сегментов, {total_text} символов")
            logger.info(f"[meeting:{meeting_id}]   Первый сегмент: [{whisper_segments[0].start:.1f}-{whisper_segments[0].end:.1f}] '{whisper_segments[0].text[:80]}'")
        else:
            logger.warning(f"[meeting:{meeting_id}]   ВНИМАНИЕ: транскрибация вернула 0 сегментов!")

        if diarization_segments:
            speakers = set(s.speaker for s in diarization_segments)
            logger.info(f"[meeting:{meeting_id}]   Диаризация: {len(diarization_segments)} сегментов, спикеров: {len(speakers)} — {speakers}")
        else:
            logger.warning(f"[meeting:{meeting_id}]   ВНИМАНИЕ: диаризация вернула 0 сегментов!")

        # Выгрузить Whisper из GPU — освободить VRAM для Ollama
        unload_model()
        logger.info(f"[meeting:{meeting_id}] Whisper выгружен из GPU")

        # ── 4. Alignment ──
        await _update_status(meeting_id, "transcribing", progress=45, eta_seconds=_calc_eta(pipeline_start, 45))
        step_start = time.time()
        logger.info(f"[meeting:{meeting_id}] [4/6] Совмещение транскрипции и диаризации...")
        from app.services.alignment import align
        aligned_segments = align(whisper_segments, diarization_segments)
        logger.info(f"[meeting:{meeting_id}] [4/6] Совмещение завершено за {time.time()-step_start:.1f}с — {len(aligned_segments)} объединённых сегментов")

        # ── 5. LLM processing ──
        await _update_status(meeting_id, "summarizing", progress=50, eta_seconds=_calc_eta(pipeline_start, 50))
        step_start = time.time()
        logger.info(f"[meeting:{meeting_id}] [5/6] LLM обработка (Ollama)...")

        from app.services.llm_service import LLMService
        llm = LLMService()

        transcript_text = _build_transcript_text(aligned_segments)
        logger.info(f"[meeting:{meeting_id}]   Транскрипт для LLM: {len(transcript_text)} символов")

        if not transcript_text.strip():
            logger.error(f"[meeting:{meeting_id}]   ОШИБКА: транскрипт пустой, LLM обработка невозможна")
            raise PipelineError(
                "Транскрипт пустой: в записи не распознана речь. "
                "Проверьте, что в файле есть звук, и загрузите запись заново."
            )

        # Подгружаем контекст из вики (RAG). Берём релевантные чанки по первой
        # части транскрипта — там обычно представление темы. Если вики не
        # настроена или ничего не нашлось — wiki_block будет пустым.
        try:
            from app.services.wiki_retrieval import build_context_for
            query_text = transcript_text[:2500]
            wiki_block = await build_context_for(query_text, k=5)
            llm.wiki_context = wiki_block
            if wiki_block:
                logger.info(
                    f"[meeting:{meeting_id}]   Wiki RAG: подмешан контекст "
                    f"{len(wiki_block)} символов"
                )
        except Exception as e:
            logger.warning(f"[meeting:{meeting_id}]   Wiki RAG: не удалось получить контекст: {e}")

        # 5a. Resolve speaker names
        # Загрузить имена участников из Телемоста (если запись через бота)
        known_participants = None
        if participant_names_json:
            try:
                known_participants = json.loads(participant_names_json)
                logger.info(f"[meeting:{meeting_id}]   Известные участники из Телемоста: {known_participants}")
            except (json.JSONDecodeError, TypeError):
                pass

        await _update_status(meeting_id, "summarizing", progress=50, eta_seconds=_calc_eta(pipeline_start, 50))
        logger.info(f"[meeting:{meeting_id}]   [5a.1] Сопоставление голосов с зарегистрированными пользователями...")

        # Сначала — попытка matching через голосовые embeddings (точно и стабильно).
        # Fallback на LLM-guessing по контексту транскрипта — только для тех,
        # кого не удалось распознать по голосу.
        from app.models.voice_profile import VoiceProfile
        from sqlalchemy.orm import selectinload
        from app.services.speaker_matching import match_speakers_to_users

        async with async_session() as session:
            result = await session.execute(
                select(VoiceProfile).options(selectinload(VoiceProfile.user))
            )
            voice_profiles = list(result.scalars().all())

        embedding_matches: dict[str, str] = {}
        if voice_profiles:
            try:
                embedding_matches = await asyncio.to_thread(
                    match_speakers_to_users, wav_path, diarization_segments, voice_profiles,
                )
                logger.info(f"[meeting:{meeting_id}]   Embedding matches: {embedding_matches}")
            except Exception as e:
                logger.warning(f"[meeting:{meeting_id}]   Embedding matching failed: {e}")
        else:
            logger.info(f"[meeting:{meeting_id}]   Голосовых профилей в БД нет, пропускаем embedding matching")

        # Применить embedding-matches к сегментам.
        for seg in aligned_segments:
            if seg.speaker in embedding_matches:
                seg.speaker = embedding_matches[seg.speaker]
        if embedding_matches:
            transcript_text = _build_transcript_text(aligned_segments)

        # Для оставшихся неопознанных SPEAKER_NN — fallback на LLM-резолюцию по контексту.
        remaining_labels = {s.speaker for s in aligned_segments if s.speaker.startswith("SPEAKER_")}
        if remaining_labels:
            logger.info(f"[meeting:{meeting_id}]   [5a.2] LLM-резолюция оставшихся: {remaining_labels}")
            speaker_names = await asyncio.to_thread(
                llm.resolve_speaker_names, transcript_text, known_participants,
            )
            if speaker_names:
                logger.info(f"[meeting:{meeting_id}]   LLM имена: {speaker_names}")
                for seg in aligned_segments:
                    if seg.speaker in speaker_names:
                        seg.speaker = speaker_names[seg.speaker]
                transcript_text = _build_transcript_text(aligned_segments)
            else:
                logger.info(f"[meeting:{meeting_id}]   LLM имена не определены, оставляем метки")
        else:
            logger.info(f"[meeting:{meeting_id}]   Все спикеры распознаны по голосу, LLM-резолюция не нужна")

        # 5b. Extract topics FIRST — они нужны как анкер для саммари и для rubric-оценки.
        await _update_status(meeting_id, "summarizing", progress=55, eta_seconds=_calc_eta(pipeline_start, 55))
        logger.info(f"[meeting:{meeting_id}]   [5b] Извлечение тем (анкер для саммари)...")
        topics = await asyncio.to_thread(llm.extract_topics, transcript_text)
        logger.info(f"[meeting:{meeting_id}]   Темы: {topics}")

        # 5c. Generate summary with topics as anchor + rubric-eval.
        await _update_status(meeting_id, "summarizing", progress=65, eta_seconds=_calc_eta(pipeline_start, 65))
        logger.info(f"[meeting:{meeting_id}]   [5c] Генерация саммари с rubric-оценкой (topics={len(topics)})...")
        summary_result = await asyncio.to_thread(
            llm.generate_summary_with_eval, transcript_text, topics,
        )
        logger.info(f"[meeting:{meeting_id}]   Саммари: brief={len(summary_result.brief)} chars, решений={len(summary_result.key_decisions)}")

        # 5d. Extract tasks with normalization + dedupe.
        # Известные участники — для нормализации assignee (Гена → Геннадий и т.п.).
        canonical_participants: list[str] = []
        if known_participants:
            canonical_participants = list(known_participants)
        # Добавить имена из распознанных спикеров (real-name labels, без SPEAKER_NN)
        seen_names = {p.lower() for p in canonical_participants}
        for seg in aligned_segments:
            label = seg.speaker
            if label and not label.startswith("SPEAKER_") and label.lower() not in seen_names:
                canonical_participants.append(label)
                seen_names.add(label.lower())

        await _update_status(meeting_id, "summarizing", progress=80, eta_seconds=_calc_eta(pipeline_start, 80))
        logger.info(
            f"[meeting:{meeting_id}]   [5d] Извлечение задач (участники для нормализации: "
            f"{canonical_participants})..."
        )
        tasks_result = await asyncio.to_thread(
            llm.extract_tasks, transcript_text, canonical_participants,
        )
        logger.info(f"[meeting:{meeting_id}]   Задач извлечено: {len(tasks_result)}")

        logger.info(f"[meeting:{meeting_id}] [5/6] LLM обработка завершена за {time.time()-step_start:.1f}с")

        # ── 6. Save to DB ──
        await _update_status(meeting_id, "summarizing", progress=95, eta_seconds=_calc_eta(pipeline_start, 95))
        step_start = time.time()
        logger.info(f"[meeting:{meeting_id}] [6/6] Сохранение результатов в БД...")
        async with async_session() as session:
            # Удалить старые результаты (при повторной обработке)
            from sqlalchemy import delete
            await session.execute(delete(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id))
            await session.execute(delete(Summary).where(Summary.meeting_id == meeting_id))
            await session.execute(delete(Task).where(Task.meeting_id == meeting_id))

            # Save transcript segments
            for seg in aligned_segments:
                session.add(TranscriptSegment(
                    meeting_id=meeting_id,
                    speaker_label=seg.speaker,
                    text=seg.text,
                    start_time=seg.start,
                    end_time=seg.end,
                ))

            # Save summary
            session.add(Summary(
                meeting_id=meeting_id,
                summary_text=summary_result.summary,
                brief=summary_result.brief,
                key_decisions=json.dumps(summary_result.key_decisions, ensure_ascii=False),
                topics=json.dumps(topics, ensure_ascii=False) if topics else None,
            ))

            # Save tasks (с контекстом)
            for task in tasks_result:
                session.add(Task(
                    meeting_id=meeting_id,
                    description=task.description,
                    context=task.context,
                    assignee=task.assignee,
                    deadline=task.deadline,
                ))

            await session.commit()
        logger.info(f"[meeting:{meeting_id}] [6/6] Сохранение завершено за {time.time()-step_start:.1f}с")

        # ── 7. AI-обогащение личных заметок участников ──
        # Запускаем ДО _update_status('done'), чтобы UI не показывал «готово»
        # раньше, чем подъехало AI-обогащение. Если упадёт — не критично,
        # сами заметки и саммари уже сохранены.
        try:
            await _enrich_meeting_notes(meeting_id, llm, transcript_text)
        except Exception as e:
            logger.warning(f"[meeting:{meeting_id}] Обогащение заметок не удалось: {e}")

        # ── Done ──
        await _update_status(meeting_id, "done", progress=100, eta_seconds=0)
        total_time = time.time() - pipeline_start
        logger.info(f"[meeting:{meeting_id}] ========== ОБРАБОТКА ЗАВЕРШЕНА за {total_time:.1f}с ==========")

        # ── Telegram уведомления ──
        await _notify_telegram(meeting_id)         # групповой чат (если был указан при записи)
        await _notify_participants(meeting_id)     # личка каждому привязанному участнику

    except Exception as e:
        total_time = time.time() - pipeline_start
        logger.exception(f"[meeting:{meeting_id}] ОШИБКА ОБРАБОТКИ после {total_time:.1f}с: {type(e).__name__}: {e}")
        # Store a safe error message for the user; full details are in logs only.
        # PipelineError carries a user-facing text; everything else is opaque.
        if isinstance(e, PipelineError):
            safe_msg = str(e)
        else:
            safe_msg = f"Ошибка обработки: {type(e).__name__}"
        await _update_status(meeting_id, "error", safe_msg)
    finally:
        with _processing_lock_guard:
            _processing_lock.discard(meeting_id)


async def _enrich_meeting_notes(meeting_id: int, llm, transcript_text: str):
    """Обогатить личные заметки участников контекстом из транскрипта.

    Логика:
    - Берём все непустые `MeetingNote` по этой встрече, у которых ещё нет
      `enriched_content` или которые обновлялись после прошлого обогащения.
    - Для каждой делаем отдельный LLM-вызов. Чужие заметки не пересекаются —
      каждый участник видит ровно свой обогащённый текст.
    - Если транскрипт пустой или модель упала на конкретной заметке —
      пропускаем без падения всего пайплайна.
    """
    import asyncio
    from datetime import datetime as _dt
    from app.models.note import MeetingNote
    from sqlalchemy.orm import selectinload

    async with async_session() as session:
        from sqlalchemy import select as _select
        r = await session.execute(
            _select(MeetingNote)
            .options(selectinload(MeetingNote.user))
            .where(MeetingNote.meeting_id == meeting_id)
        )
        notes = list(r.scalars().all())
        # Только непустые и устаревшие (или ещё не обогащённые).
        targets = [
            n for n in notes
            if (n.content or "").strip()
            and (n.enriched_at is None or n.enriched_at < n.updated_at)
        ]
        if not targets:
            logger.info(f"[meeting:{meeting_id}] Заметок для обогащения нет")
            return

        logger.info(f"[meeting:{meeting_id}] Обогащение заметок: {len(targets)} шт.")
        for note in targets:
            author_name = (note.user.display_name or note.user.username) if note.user else "участник"
            try:
                enriched = await asyncio.to_thread(
                    llm.enrich_notes, transcript_text, note.content, author_name,
                )
                note.enriched_content = enriched
                note.enriched_at = _dt.utcnow()
                logger.info(
                    f"[meeting:{meeting_id}]   Обогащено для user_id={note.user_id} "
                    f"({author_name}): {len(enriched)} chars"
                )
            except Exception as e:
                logger.warning(
                    f"[meeting:{meeting_id}]   Обогащение упало для user_id={note.user_id}: {e}"
                )
        await session.commit()


async def _notify_participants(meeting_id: int):
    """Разослать саммари в личку каждому участнику, чей display_name найден среди спикеров.

    Логика:
    1. Берём уникальные speaker_label-ы из транскрипта (исключая SPEAKER_NN).
    2. Ищем пользователей с привязанным telegram_id и подходящим display_name
       (case-insensitive нормализация).
    3. Каждому шлём краткое саммари + ссылку на mini app или web.
    """
    try:
        from app.config import settings
        from app.models.user import User
        from app.models.summary import Summary
        from app.services.telegram_service import TelegramService
        from sqlalchemy import select, distinct

        if not settings.TELEGRAM_BOT_TOKEN:
            return

        async with async_session() as session:
            # Уникальные спикеры из транскрипта
            r = await session.execute(
                select(distinct(TranscriptSegment.speaker_label))
                .where(TranscriptSegment.meeting_id == meeting_id)
            )
            speaker_labels = [s for (s,) in r.all() if s and not s.startswith("SPEAKER_")]
            if not speaker_labels:
                logger.info(f"[meeting:{meeting_id}] Участники не определены, рассылка пропущена")
                return

            # Нормализация: «Антон» / «  АНТОН  » → "антон"
            norm = {s.strip().lower() for s in speaker_labels}

            # Пользователи с привязанным Telegram
            r = await session.execute(select(User).where(User.telegram_id.is_not(None)))
            candidates = r.scalars().all()
            recipients = [u for u in candidates if u.display_name.strip().lower() in norm]
            if not recipients:
                logger.info(
                    f"[meeting:{meeting_id}] Никто из спикеров {speaker_labels} "
                    f"не привязал Telegram — рассылка пропущена"
                )
                return

            # Данные саммари
            r = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = r.scalar_one_or_none()
            r = await session.execute(select(Summary).where(Summary.meeting_id == meeting_id))
            summary = r.scalar_one_or_none()
            if meeting is None:
                return

        brief = (summary.brief if summary else "") or ""
        # Обрежем до 700 символов чтобы влезло в Telegram-сообщение читабельно
        if len(brief) > 700:
            brief = brief[:700].rstrip() + "…"

        from html import escape
        title = escape(meeting.title or "Совещание")
        body = escape(brief).replace("\n", "\n")

        web_url = f"{settings.APP_URL.rstrip('/')}/meetings/{meeting_id}" if settings.APP_URL else None
        miniapp_url = None
        if settings.MINI_APP_URL:
            miniapp_url = f"{settings.MINI_APP_URL.rstrip('/')}/miniapp/meeting/{meeting_id}"

        text = (
            f"📋 <b>{title}</b>\n\n"
            f"{body if body else 'Саммари готово.'}\n\n"
            f"Открыть полностью:"
        )

        telegram = TelegramService(settings.TELEGRAM_BOT_TOKEN)
        sent = 0
        for user in recipients:
            try:
                if miniapp_url:
                    ok = await telegram.send_message_with_webapp(
                        user.telegram_id, text, "Открыть в приложении", miniapp_url,
                    )
                else:
                    if web_url:
                        text_with_url = text + f'\n<a href="{escape(web_url)}">{escape(web_url)}</a>'
                    else:
                        text_with_url = text
                    ok = await telegram.send_message(user.telegram_id, text_with_url)
                if ok:
                    sent += 1
                    logger.info(
                        f"[meeting:{meeting_id}] Уведомление участнику {user.username} "
                        f"({user.display_name}, tg_id={user.telegram_id}) отправлено"
                    )
            except Exception as e:
                logger.warning(
                    f"[meeting:{meeting_id}] Не удалось уведомить {user.username}: {e}"
                )

        logger.info(
            f"[meeting:{meeting_id}] Рассылка участникам: {sent}/{len(recipients)} доставлено"
        )
    except Exception as e:
        logger.exception(f"[meeting:{meeting_id}] Ошибка рассылки участникам: {e}")


async def _notify_telegram(meeting_id: int):
    """Отправить уведомление в Telegram после обработки."""
    try:
        from app.config import settings
        from app.services.telegram_service import TelegramService
        from sqlalchemy import select

        if not settings.TELEGRAM_BOT_TOKEN:
            return

        async with async_session() as session:
            result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = result.scalar_one_or_none()
            if not meeting or not meeting.telegram_chat_id:
                return

        telegram = TelegramService(settings.TELEGRAM_BOT_TOKEN)
        app_url = f"{settings.APP_URL}/meetings/{meeting_id}"
        # web_app кнопки работают только в личных чатах (не в группах)
        miniapp_url = None
        chat_id = meeting.telegram_chat_id
        if settings.MINI_APP_URL and not chat_id.startswith("-"):
            miniapp_url = f"{settings.MINI_APP_URL.rstrip('/')}/miniapp/meeting/{meeting_id}"
        await telegram.send_meeting_ready(
            chat_id=chat_id,
            title=meeting.title,
            app_url=app_url,
            miniapp_url=miniapp_url,
        )
        logger.info(f"[meeting:{meeting_id}] Telegram уведомление отправлено в {meeting.telegram_chat_id}")
    except Exception as e:
        logger.error(f"[meeting:{meeting_id}] Ошибка Telegram уведомления: {e}")
