"""Rubric-based оценка качества саммари.

Возвращает чек-лист: упомянуты ли темы, решения, ответственные.
Регенерация запускается если score < THRESHOLD (см. llm_service).
"""

EVAL_SYSTEM_PROMPT = """Ты строго оцениваешь саммари совещания по чек-листу. Отвечай ТОЛЬКО валидным JSON."""

EVAL_USER_TEMPLATE = """Транскрипт (фрагмент):
{transcript_excerpt}

Темы из транскрипта:
{topics}

Саммари:
{summary}

---
Проверь саммари по чек-листу. Для каждого пункта ответь true/false.

Чек-лист:
- topics_covered: ВСЕ темы из списка отражены в brief или summary?
- has_structured_brief: brief содержит явные строки "Обсудили:", "Решили:", "Поручено:"?
- decisions_concrete: key_decisions содержит КОНКРЕТНЫЕ решения (а не общие фразы вроде "обсудили вопрос")?
- assignees_named: в brief или в summary упомянуты конкретные имена ответственных за поручения?
- no_hallucinations: в саммари НЕТ фактов, которых нет в транскрипте?

JSON:
{{
  "topics_covered": true/false,
  "has_structured_brief": true/false,
  "decisions_concrete": true/false,
  "assignees_named": true/false,
  "no_hallucinations": true/false,
  "issues": ["короткое описание проблемы 1", ...]
}}

Никакого текста вне JSON."""
