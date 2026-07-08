import json
import logging
import re
from dataclasses import dataclass, field

from app.config import settings
from app.prompts.summary import (
    SUMMARY_SYSTEM_PROMPT, SUMMARY_USER_TEMPLATE, SUMMARY_TOPICS_HINT_TEMPLATE,
)
from app.prompts.tasks import (
    TASKS_SYSTEM_PROMPT, TASKS_USER_TEMPLATE, TASKS_PARTICIPANTS_HINT_TEMPLATE,
    NORMALIZE_SYSTEM_PROMPT, NORMALIZE_USER_TEMPLATE,
)
from app.prompts.chat import CHAT_SYSTEM_PROMPT
from app.prompts.evaluation import EVAL_SYSTEM_PROMPT, EVAL_USER_TEMPLATE
from app.prompts.topics import TOPICS_SYSTEM_PROMPT, TOPICS_USER_TEMPLATE
from app.prompts.speaker_names import (
    SPEAKER_NAMES_PROMPT, SPEAKER_NAMES_USER_TEMPLATE,
    SPEAKER_NAMES_WITH_PARTICIPANTS_PROMPT, SPEAKER_NAMES_WITH_PARTICIPANTS_USER_TEMPLATE,
)
from app.prompts.notes import NOTES_ENRICH_SYSTEM_PROMPT, NOTES_ENRICH_USER_TEMPLATE

logger = logging.getLogger(__name__)

# Ollama на CPU может генерировать медленно — таймаут 10 минут
OLLAMA_TIMEOUT = 600


@dataclass
class SummaryResult:
    brief: str
    summary: str
    key_decisions: list[str] = field(default_factory=list)


@dataclass
class TaskResult:
    description: str
    context: str | None = None
    assignee: str | None = None
    deadline: str | None = None


def _clean_json_response(text: str) -> str:
    """Очистить ответ от markdown-обёртки ```json ... ``` и <think> тегов."""
    text = text.strip()
    # Убрать <think>...</think> блоки (Qwen 3.5 thinking mode)
    text = re.sub(r'<think>[\s\S]*?</think>', '', text).strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text.strip()


class LLMService:
    def __init__(self):
        self._ollama_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        # Дополнительный контекст из Wiki.js (RAG). Если непустой —
        # подмешивается в system_prompt всех LLM-вызовов. Управляется извне:
        # processing.py / api/chat.py ставят его на время обработки одной встречи
        # или одного chat-вопроса, а затем очищают.
        self.wiki_context: str = ""
        logger.info(f"LLM сервис: Ollama ({self.model}) на {self._ollama_url}")

    def _wrap_with_wiki_context(self, system_prompt: str) -> str:
        """Если есть wiki_context — добавить его как отдельный блок над system_prompt."""
        ctx = (self.wiki_context or "").strip()
        if not ctx:
            return system_prompt
        return (
            "ВНУТРЕННЯЯ ДОКУМЕНТАЦИЯ ПРОДУКТА (используй её для уточнения терминов, "
            "корректного названия модулей и фактов о продукте; "
            "если в документации чего-то нет — не выдумывай):\n\n"
            f"{ctx}\n\n"
            "---\n\n"
            f"{system_prompt}"
        )

    def _call_with_retry(
        self, system_prompt: str, user_prompt: str,
        temperature: float = 0.3, max_retries: int = 3,
        expect_json: bool = False,
    ) -> str:
        """Вызов Ollama с retry."""
        system_prompt = self._wrap_with_wiki_context(system_prompt)
        prompt_len = len(system_prompt) + len(user_prompt)
        logger.info(f"LLM запрос: system={len(system_prompt)}, user={len(user_prompt)}, total={prompt_len} chars")

        last_error = None
        for attempt in range(max_retries):
            try:
                logger.info(f"Отправка запроса к Ollama (попытка {attempt + 1}/{max_retries})...")
                content = self._call_ollama(system_prompt, user_prompt, temperature,
                                            force_json=expect_json)
                logger.info(f"LLM ответ получен: {len(content)} chars")
                return content
            except Exception as e:
                last_error = e
                logger.warning(f"LLM запрос неудачен (попытка {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)

        raise RuntimeError(f"Ollama недоступен после {max_retries} попыток: {last_error}")

    def _call_ollama(self, system_prompt: str, user_prompt: str, temperature: float,
                     force_json: bool = False) -> str:
        """Вызов Ollama через /api/chat (правильный system/user формат).

        Для thinking-моделей (qwen3.x, deepseek-r1) передаём think:false —
        иначе модель уходит в многоминутное «размышление» перед ответом, что
        неприемлемо для нашего pipeline (8+ LLM-вызовов на одну встречу).
        Для классических моделей (qwen2.5, llama) параметр игнорируется.
        """
        import httpx
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": False,
            "options": {
                "temperature": temperature,
            },
        }
        if force_json:
            payload["format"] = "json"
        response = httpx.post(
            f"{self._ollama_url}/api/chat",
            json=payload,
            timeout=OLLAMA_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        if not content:
            raise RuntimeError("Ollama вернул пустой ответ")
        return content

    def _call_chat_with_retry(
        self, messages: list[dict],
        temperature: float = 0.7, max_retries: int = 3,
    ) -> str:
        """Вызов Ollama для чата с историей сообщений."""
        # Подмешиваем wiki_context в system-сообщение (если есть).
        if messages and messages[0].get("role") == "system":
            messages = [
                {**messages[0], "content": self._wrap_with_wiki_context(messages[0]["content"])},
                *messages[1:],
            ]
        total_len = sum(len(m.get("content", "")) for m in messages)
        logger.info(f"LLM чат запрос: {len(messages)} сообщений, total={total_len} chars")

        last_error = None
        for attempt in range(max_retries):
            try:
                import httpx
                payload = {
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "think": False,   # отключаем reasoning для qwen3/deepseek-r1
                    "options": {
                        "temperature": temperature,
                    },
                }
                response = httpx.post(
                    f"{self._ollama_url}/api/chat",
                    json=payload,
                    timeout=OLLAMA_TIMEOUT,
                )
                response.raise_for_status()
                data = response.json()
                content = data.get("message", {}).get("content", "")

                if not content:
                    raise RuntimeError("Ollama вернул пустой ответ")
                logger.info(f"LLM чат ответ: {len(content)} chars")
                return content
            except Exception as e:
                last_error = e
                logger.warning(f"LLM чат запрос неудачен (попытка {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(2 ** attempt)

        raise RuntimeError(f"Ollama чат недоступен после {max_retries} попыток: {last_error}")

    def _parse_json(self, text: str) -> dict:
        """Парсинг JSON-ответа с обработкой ошибок."""
        if text is None:
            raise ValueError("LLM вернул None вместо текста")
        cleaned = _clean_json_response(text)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            # Попытка починить тройные кавычки (Python-стиль, невалидный JSON)
            fixed = re.sub(
                r'"""(.*?)"""',
                lambda m: json.dumps(m.group(1)),
                cleaned,
                flags=re.DOTALL,
            )
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass
            # Попытка извлечь JSON-блок
            match = re.search(r'\{[\s\S]*\}', fixed)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
            logger.error(f"Не удалось распарсить JSON. Ответ LLM:\n{cleaned[:500]}")
            raise ValueError(f"Не удалось распарсить JSON: {cleaned[:200]}")

    def resolve_speaker_names(self, transcript_text: str,
                              participant_names: list[str] | None = None) -> dict[str, str]:
        """Определение имён спикеров из контекста."""
        if participant_names:
            logger.info(f"Определение имён спикеров с подсказкой: {participant_names}")
            names_list = ", ".join(participant_names)
            system = SPEAKER_NAMES_WITH_PARTICIPANTS_PROMPT
            user = SPEAKER_NAMES_WITH_PARTICIPANTS_USER_TEMPLATE.replace(
                "{transcript}", transcript_text
            ).replace("{participants}", names_list)
        else:
            logger.info(f"Определение имён спикеров из контекста... (транскрипт: {len(transcript_text)} символов)")
            system = SPEAKER_NAMES_PROMPT
            user = SPEAKER_NAMES_USER_TEMPLATE.replace("{transcript}", transcript_text)

        for attempt in range(2):
            try:
                response = self._call_with_retry(
                    system, user,
                    temperature=0.1,
                    expect_json=True,
                )
                result = self._parse_json(response)

                # Валидация: ключи должны быть SPEAKER_NN, значения — короткие строки (имена)
                valid = {}
                for k, v in result.items():
                    if k.startswith("SPEAKER_") and isinstance(v, str) and len(v) < 50:
                        valid[k] = v
                if valid:
                    logger.info(f"Имена спикеров определены: {valid}")
                    return valid

                # Модель вернула не то (например, саммари вместо имён)
                logger.warning(f"Спикеры: модель вернула невалидный формат, ключи: {list(result.keys())[:5]}")
                if attempt == 0:
                    continue  # retry
                return {}
            except (ValueError, Exception) as e:
                logger.warning(f"Ошибка определения имён (попытка {attempt + 1}): {e}")
                if attempt == 1:
                    logger.error("Не удалось определить имена спикеров, оставляем как есть")
                    return {}

    # Максимальный размер текста для одного запроса к LLM
    MAX_CHUNK_CHARS = 15000

    def _chunk_transcript(self, text: str) -> list[str]:
        """Разбить длинный транскрипт на части по границам реплик."""
        if len(text) <= self.MAX_CHUNK_CHARS:
            return [text]

        chunks = []
        lines = text.split("\n")
        current_chunk = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1  # +1 for newline
            if current_len + line_len > self.MAX_CHUNK_CHARS and current_chunk:
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            current_chunk.append(line)
            current_len += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        logger.info(f"Транскрипт разбит на {len(chunks)} частей: {[len(c) for c in chunks]}")
        return chunks

    def _summarize_single(self, text: str, topics: list[str] | None = None) -> dict:
        """Сгенерировать саммари для одного куска текста.

        Если переданы topics — они подставляются в подсказку, чтобы саммари
        охватывало все темы (two-pass подход).
        """
        if topics:
            topics_lines = "\n".join(f"  - {t}" for t in topics)
            topics_hint = SUMMARY_TOPICS_HINT_TEMPLATE.replace("{topics}", topics_lines)
        else:
            topics_hint = ""
        user = SUMMARY_USER_TEMPLATE.replace("{transcript}", text).replace(
            "{topics_hint}", topics_hint
        )
        response = self._call_with_retry(
            SUMMARY_SYSTEM_PROMPT,
            user,
            temperature=0.3,
            expect_json=True,
        )
        return self._parse_json(response)

    def _extract_summary_fields(self, data: dict) -> SummaryResult:
        """Извлечь поля саммари из JSON с fallback на альтернативные ключи."""
        # Если модель обернула всё в один ключ (meeting_summary, 会议记录, etc.),
        # и значение — вложенный dict, развернуть его
        if len(data) == 1:
            only_value = next(iter(data.values()))
            if isinstance(only_value, dict):
                logger.warning(f"LLM обернул саммари в ключ '{next(iter(data.keys()))}', разворачиваю")
                data = only_value
            elif isinstance(only_value, str):
                # Единственное строковое значение — использовать как summary
                logger.warning(f"LLM вернул единственный ключ '{next(iter(data.keys()))}' со строкой")
                return SummaryResult(brief="", summary=only_value, key_decisions=[])

        brief = (
            data.get("brief")
            or data.get("brief_summary")
            or data.get("краткий_пересказ")
            or data.get("краткое")
            or data.get("overview")
            or ""
        )
        summary = (
            data.get("summary")
            or data.get("detailed_summary")
            or data.get("meeting_summary")
            or data.get("подробное_саммари")
            or data.get("подробное")
            or data.get("summary_text")
            or data.get("details")
            or ""
        )
        key_decisions = (
            data.get("key_decisions")
            or data.get("decisions")
            or data.get("ключевые_решения")
            or data.get("key_points")
            or data.get("action_items")
            or []
        )

        # Если brief пустой но summary длинный — сделать brief из summary
        if not brief and summary:
            brief = summary[:300]

        # Если brief и summary оба пустые — взять любые строки
        if not brief and not summary:
            logger.warning(f"LLM вернул JSON с неожиданными ключами: {list(data.keys())}")
            str_values = [v for v in data.values() if isinstance(v, str) and len(v) > 20]
            if len(str_values) >= 2:
                brief = str_values[0]
                summary = str_values[1]
            elif len(str_values) == 1:
                summary = str_values[0]
                brief = summary[:300]

        # Нормализовать key_decisions — если это list[dict], извлечь текст
        if isinstance(key_decisions, list) and key_decisions and isinstance(key_decisions[0], dict):
            key_decisions = [
                d.get("task") or d.get("description") or d.get("decision") or str(d)
                for d in key_decisions
            ]

        return SummaryResult(
            brief=brief,
            summary=summary,
            key_decisions=key_decisions if isinstance(key_decisions, list) else [],
        )

    def generate_summary(self, transcript_text: str, topics: list[str] | None = None) -> SummaryResult:
        """Генерация саммари совещания. Для длинных текстов — чанкование + объединение.

        Если переданы topics — они используются как структурный ориентир (two-pass).
        """
        logger.info(
            f"Генерация саммари... (транскрипт: {len(transcript_text)} символов, "
            f"тем: {len(topics) if topics else 0})"
        )

        chunks = self._chunk_transcript(transcript_text)

        if len(chunks) == 1:
            # Короткий транскрипт — один запрос
            return self._generate_summary_single(transcript_text, topics=topics)

        # Длинный транскрипт — саммари по частям, потом объединение
        logger.info(f"Длинный транскрипт ({len(transcript_text)} chars), чанкование на {len(chunks)} частей")

        partial_summaries = []
        all_decisions = []
        for i, chunk in enumerate(chunks):
            logger.info(f"  Обработка части {i + 1}/{len(chunks)} ({len(chunk)} chars)...")
            try:
                data = self._summarize_single(chunk, topics=topics)
                result = self._extract_summary_fields(data)
                if result.summary:
                    partial_summaries.append(f"Часть {i + 1}:\n{result.summary}")
                elif result.brief:
                    partial_summaries.append(f"Часть {i + 1}:\n{result.brief}")
                all_decisions.extend(result.key_decisions)
            except Exception as e:
                logger.warning(f"  Ошибка обработки части {i + 1}: {e}")

        if not partial_summaries:
            logger.error("Ни одна часть не была обработана")
            return SummaryResult(brief="", summary="", key_decisions=[])

        # Финальное объединение
        combined_text = "\n\n".join(partial_summaries)
        logger.info(f"  Объединение {len(partial_summaries)} частей ({len(combined_text)} chars)...")

        merge_system = "Ты объединяешь саммари. Отвечай ТОЛЬКО валидным JSON. Язык — русский."
        merge_user = (
            f"Саммари частей совещания:\n{combined_text}\n\n"
            f"Ключевые решения из частей: {json.dumps(all_decisions, ensure_ascii=False)}\n\n"
            "---\nОбъедини в единое связное саммари. Ответь ТОЛЬКО JSON:\n"
            '{"brief": "краткое саммари в 2-3 предложения", '
            '"summary": "подробное объединённое саммари", '
            '"key_decisions": ["решение 1", "решение 2"]}\n\n'
            "Ключи ТОЛЬКО на английском: brief, summary, key_decisions. Значения на русском.\n"
            "Начни с { и закончи }. Никакого текста вне JSON."
        )

        try:
            response = self._call_with_retry(
                merge_system,
                merge_user,
                temperature=0.3,
                expect_json=True,
            )
            data = self._parse_json(response)
            result = self._extract_summary_fields(data)
            # Добавить решения из частей, которые LLM мог пропустить
            if all_decisions and not result.key_decisions:
                result.key_decisions = all_decisions
            logger.info(f"Итоговое саммари: brief={len(result.brief)} chars, summary={len(result.summary)} chars, решений={len(result.key_decisions)}")
            return result
        except Exception as e:
            logger.error(f"Ошибка объединения саммари: {e}")
            # Fallback — вернуть склеенные части
            return SummaryResult(
                brief=partial_summaries[0][:300] if partial_summaries else "",
                summary=combined_text,
                key_decisions=all_decisions,
            )

    def _generate_summary_single(
        self, transcript_text: str, topics: list[str] | None = None,
    ) -> SummaryResult:
        """Генерация саммари для короткого транскрипта (один запрос)."""
        for attempt in range(2):
            try:
                data = self._summarize_single(transcript_text, topics=topics)
                result = self._extract_summary_fields(data)
                logger.info(f"Саммари сгенерировано: brief={len(result.brief)} chars, summary={len(result.summary)} chars")
                return result
            except (ValueError, Exception) as e:
                logger.warning(f"Ошибка генерации саммари (попытка {attempt + 1}): {e}")
                if attempt == 1:
                    raise

    # Минимальное число «галочек» из rubric (5), при котором саммари считается приемлемым.
    EVAL_PASS_THRESHOLD = 4

    def evaluate_summary(
        self, transcript_excerpt: str, summary: str, topics: list[str] | None = None,
    ) -> dict:
        """Rubric-оценка саммари: 5 бинарных проверок + issues.

        Возвращает {"score": 0..5, "checks": {...}, "issues": [...]}.
        score = число True-чеков.
        """
        logger.info("Rubric-оценка саммари...")
        topics_str = ", ".join(topics) if topics else "(не извлечены)"
        user = (
            EVAL_USER_TEMPLATE
            .replace("{transcript_excerpt}", transcript_excerpt)
            .replace("{topics}", topics_str)
            .replace("{summary}", summary)
        )

        try:
            response = self._call_with_retry(
                EVAL_SYSTEM_PROMPT,
                user,
                temperature=0.1,
                expect_json=True,
            )
            data = self._parse_json(response)
            checks = {
                k: bool(data.get(k))
                for k in (
                    "topics_covered", "has_structured_brief", "decisions_concrete",
                    "assignees_named", "no_hallucinations",
                )
            }
            score = sum(checks.values())
            issues = data.get("issues", [])
            if not isinstance(issues, list):
                issues = []
            logger.info(f"Оценка саммари: score={score}/5, checks={checks}, issues={issues}")
            return {"score": score, "checks": checks, "issues": issues}
        except Exception as e:
            logger.warning(f"Ошибка оценки саммари: {e}")
            # При ошибке eval — считаем «нейтрально» (не триггерим бесполезный retry)
            return {"score": self.EVAL_PASS_THRESHOLD, "checks": {}, "issues": []}

    def generate_summary_with_eval(
        self, transcript_text: str, topics: list[str] | None = None,
    ) -> SummaryResult:
        """Генерация саммари с rubric-оценкой и повторной попыткой при низком качестве."""
        logger.info("Генерация саммари с rubric-оценкой...")

        result = self.generate_summary(transcript_text, topics=topics)

        # Оценка качества на первых 3000 символах транскрипта
        transcript_excerpt = transcript_text[:3000]
        summary_text = result.summary or result.brief
        evaluation = self.evaluate_summary(transcript_excerpt, summary_text, topics=topics)

        if evaluation["score"] < self.EVAL_PASS_THRESHOLD:
            logger.warning(
                f"Низкое качество саммари (score={evaluation['score']}/5), "
                f"проблемы: {evaluation['issues']}. Повторная генерация..."
            )
            retry_result = self.generate_summary(transcript_text, topics=topics)
            retry_eval = self.evaluate_summary(
                transcript_excerpt,
                retry_result.summary or retry_result.brief,
                topics=topics,
            )
            logger.info(
                f"Повторная оценка: score={retry_eval['score']}/5 "
                f"(было {evaluation['score']}/5)"
            )
            if retry_eval["score"] >= evaluation["score"]:
                return retry_result
            return result

        return result

    def extract_topics(self, transcript_text: str) -> list[str]:
        """Извлечение ключевых тем совещания."""
        logger.info(f"Извлечение тем... (транскрипт: {len(transcript_text)} символов)")
        user = TOPICS_USER_TEMPLATE.replace("{transcript}", transcript_text)

        try:
            response = self._call_with_retry(
                TOPICS_SYSTEM_PROMPT,
                user,
                temperature=0.2,
                expect_json=True,
            )
            data = self._parse_json(response)
            topics = data.get("topics", [])
            if not isinstance(topics, list):
                topics = []
            # Убедиться что все элементы — строки
            topics = [str(t) for t in topics if t]
            logger.info(f"Извлечено тем: {len(topics)} — {topics}")
            return topics
        except Exception as e:
            logger.warning(f"Ошибка извлечения тем: {e}")
            return []

    def _extract_tasks_from_data(self, data: dict) -> list[TaskResult]:
        """Извлечь задачи из JSON с fallback на альтернативные ключи."""
        # Попробовать разные ключи для массива задач
        tasks_list = (
            data.get("tasks")
            or data.get("action_items")
            or data.get("задачи")
            or data.get("items")
            or []
        )

        # Если корневой элемент — единственный ключ с вложенным dict/list
        if not tasks_list and len(data) == 1:
            only_value = next(iter(data.values()))
            if isinstance(only_value, list):
                tasks_list = only_value
            elif isinstance(only_value, dict):
                # Рекурсия на один уровень
                return self._extract_tasks_from_data(only_value)

        results = []
        for t in tasks_list:
            if isinstance(t, str):
                # Простой список строк
                if t.strip():
                    results.append(TaskResult(description=t.strip()))
                continue
            if not isinstance(t, dict):
                continue
            desc = (
                t.get("description") or t.get("task") or t.get("описание") or ""
            ).strip()
            if desc:
                results.append(TaskResult(
                    description=desc,
                    context=(t.get("context") or t.get("контекст") or t.get("reason") or None),
                    assignee=t.get("assignee") or t.get("person") or t.get("ответственный"),
                    deadline=t.get("deadline") or t.get("срок"),
                ))
        return results

    def extract_tasks(
        self, transcript_text: str, participants: list[str] | None = None,
    ) -> list[TaskResult]:
        """Извлечь задачи + нормализовать assignee + удалить дубли.

        participants — канонические имена для нормализации (Геннадий, Мария, ...).
        """
        logger.info(
            f"Извлечение задач... (транскрипт: {len(transcript_text)} символов, "
            f"известных участников: {len(participants) if participants else 0})"
        )

        # Подсказка с участниками — модель чаще пишет правильное имя сразу
        if participants:
            participants_hint = TASKS_PARTICIPANTS_HINT_TEMPLATE.replace(
                "{participants}", ", ".join(participants)
            )
        else:
            participants_hint = ""

        chunks = self._chunk_transcript(transcript_text)
        all_tasks: list[TaskResult] = []

        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                logger.info(f"  Извлечение задач из части {i + 1}/{len(chunks)} ({len(chunk)} chars)...")
            user = (
                TASKS_USER_TEMPLATE
                .replace("{transcript}", chunk)
                .replace("{participants_hint}", participants_hint)
            )
            for attempt in range(2):
                try:
                    response = self._call_with_retry(
                        TASKS_SYSTEM_PROMPT,
                        user,
                        temperature=0.3,
                        expect_json=True,
                    )
                    data = self._parse_json(response)
                    tasks = self._extract_tasks_from_data(data)
                    all_tasks.extend(tasks)
                    if tasks:
                        logger.info(f"  Часть {i + 1}: найдено {len(tasks)} задач")
                    break
                except (ValueError, Exception) as e:
                    logger.warning(f"Ошибка извлечения задач (часть {i + 1}, попытка {attempt + 1}): {e}")
                    if attempt == 1:
                        continue

        logger.info(f"Извлечено задач (черновик): {len(all_tasks)}")

        # Post-processing: нормализация + дедуп
        if participants:
            all_tasks = self._normalize_tasks_llm(all_tasks, participants)
        all_tasks = self._dedupe_tasks_local(all_tasks)
        logger.info(f"После нормализации и дедупа: {len(all_tasks)}")
        return all_tasks

    def _normalize_tasks_llm(
        self, tasks: list[TaskResult], participants: list[str],
    ) -> list[TaskResult]:
        """LLM-проход: приводит assignee к каноническим именам и убирает явные дубли."""
        if not tasks:
            return tasks

        tasks_json = json.dumps(
            [
                {
                    "description": t.description,
                    "context": t.context,
                    "assignee": t.assignee,
                    "deadline": t.deadline,
                }
                for t in tasks
            ],
            ensure_ascii=False,
        )
        user = (
            NORMALIZE_USER_TEMPLATE
            .replace("{participants}", ", ".join(participants))
            .replace("{tasks_json}", tasks_json)
        )
        try:
            response = self._call_with_retry(
                NORMALIZE_SYSTEM_PROMPT,
                user,
                temperature=0.1,
                expect_json=True,
            )
            data = self._parse_json(response)
            normalized = self._extract_tasks_from_data(data)
            if normalized:
                return normalized
        except Exception as e:
            logger.warning(f"Нормализация задач не удалась, возвращаю исходный список: {e}")
        return tasks

    @staticmethod
    def _dedupe_tasks_local(tasks: list[TaskResult]) -> list[TaskResult]:
        """Локальная дедупликация по совпадению первых 4 слов + assignee.

        При совпадении оставляем более полную формулировку (длиннее description).
        """
        def _prefix_key(t: TaskResult) -> tuple[str, str]:
            assignee = (t.assignee or "").lower().strip()
            words = t.description.lower().split()
            prefix = " ".join(words[:4])
            return (assignee, prefix)

        by_key: dict[tuple[str, str], TaskResult] = {}
        order: list[tuple[str, str]] = []
        for t in tasks:
            key = _prefix_key(t)
            if key not in by_key:
                by_key[key] = t
                order.append(key)
            else:
                # Оставляем более полное описание
                if len(t.description) > len(by_key[key].description):
                    by_key[key] = t
        return [by_key[k] for k in order]

    def chat(self, transcript_text: str, chat_history: list[dict], user_message: str) -> str:
        """Ответ на вопрос по совещанию."""
        logger.info(f"Чат: вопрос '{user_message[:100]}', история: {len(chat_history)} сообщений")
        system = CHAT_SYSTEM_PROMPT.replace("{transcript}", transcript_text)

        messages = [{"role": "system", "content": system}]
        for msg in chat_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        response = self._call_chat_with_retry(messages, temperature=0.7)
        return response.strip()

    def enrich_notes(self, transcript_text: str, notes: str, author_name: str) -> str:
        """AI-обогащение личных заметок участника контекстом из транскрипта.

        Возвращает markdown: исходные строки автора сохранены дословно,
        под каждой добавлены уточнения курсивом. Если заметки пустые —
        вернёт пустую строку без обращения к LLM.
        """
        notes = (notes or "").strip()
        if not notes:
            return ""
        if not transcript_text.strip():
            # Нечего добавить — отдадим исходник, чтобы не терять.
            return notes
        logger.info(
            f"Обогащение заметок: автор={author_name}, заметки={len(notes)} chars, "
            f"транскрипт={len(transcript_text)} chars"
        )
        user_prompt = (
            NOTES_ENRICH_USER_TEMPLATE
            .replace("{transcript}", transcript_text)
            .replace("{notes}", notes)
            .replace("{author_name}", author_name or "участник")
        )
        response = self._call_with_retry(
            NOTES_ENRICH_SYSTEM_PROMPT, user_prompt,
            temperature=0.3, expect_json=False,
        )
        # Снимаем <think>...</think> если qwen3 thinking-режим протёк
        cleaned = re.sub(r'<think>[\s\S]*?</think>', '', response).strip()
        return cleaned or notes
