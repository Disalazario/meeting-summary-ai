"""Wiki.js RAG: локальный индекс страниц и чанков с эмбеддингами.

Зачем: чтобы саммари / задачи / чат могли опираться на внутреннюю
документацию компании, не вызывая Wiki.js на каждый LLM-запрос.

Что храним:
- WikiPage — копия страницы из Wiki.js (id из вики, путь, заголовок,
  markdown-контент, hash контента, время последнего изменения).
- WikiChunk — куски страницы ~500 токенов с эмбеддингом (BLOB, float32
  numpy array). Эмбеддинги нормализованные → cosine similarity = dot.
"""
from datetime import datetime

from sqlalchemy import Integer, String, Text, DateTime, ForeignKey, LargeBinary, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class WikiPage(Base):
    __tablename__ = "wiki_pages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wiki_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    locale: Mapped[str] = mapped_column(String, nullable=False, default="ru")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    wiki_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    chunks = relationship("WikiChunk", back_populates="page", cascade="all, delete-orphan")


class WikiChunk(Base):
    __tablename__ = "wiki_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    page_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("wiki_pages.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # float32 vector dim=768 для multilingual-e5-base. Сохраняется как
    # numpy.tobytes(); читается через numpy.frombuffer(..., dtype=float32).
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)

    page = relationship("WikiPage", back_populates="chunks")


Index("ix_wiki_chunks_page_id", WikiChunk.page_id)
