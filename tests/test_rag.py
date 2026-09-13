"""Tests for the source-grounded RAG pipeline (contracts, retrieval, grounding)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from sqlalchemy.orm import Session

from knowledge_base.config import Settings
from knowledge_base.database.enums import (
    BlockType,
    ChapterKind,
    ContentStatus,
    Language,
    SourceFormat,
)
from knowledge_base.database.models.books import Book
from knowledge_base.database.models.sources import SourceFile
from knowledge_base.database.models.structure import (
    Chapter,
    ContentBlock,
    ContentChunk,
    Section,
)
from knowledge_base.rag.config import RagConfig
from knowledge_base.rag.generation import (
    ExtractiveGenerator,
    generate_answer,
    render_context,
    verify_grounding,
)
from knowledge_base.rag.models import RetrievalQuery, RetrievedSource
from knowledge_base.rag.retrieval import retrieve
from knowledge_base.rag.service import RagService

# ------------------------------------------------------------- fake helpers


@dataclass
class StubHit:
    chunk_id: str
    text: str
    score: float
    fts_score: float | None = None
    vector_score: float | None = None
    retrievers: tuple[str, ...] = field(default_factory=lambda: ("fts",))
    book: str | None = None
    book_id: str | None = None
    chapter: str | None = None
    chapter_id: str | None = None
    section: str | None = None
    section_id: str | None = None
    page: int | None = None
    source_id: str | None = None


class StubBackend:
    def __init__(self, hits: list[StubHit]) -> None:
        self.hits = hits

    def search(self, session: Session, query: RetrievalQuery, *, limit: int) -> list[StubHit]:
        return self.hits[:limit]


class _FakeScalarResult:
    def scalar_one_or_none(self) -> None:
        return None


class _FakeSession:
    def get(self, model: object, pk: object) -> None:
        return None

    def execute(self, statement: object) -> _FakeScalarResult:
        return _FakeScalarResult()


PASSAGE = "The scholars transmitted hadith with meticulous care across generations."
PASSAGE2 = "Patience among the believers is a praised character."


def _mk_source(idx: int, *, score: float = 0.8, passage: str = PASSAGE) -> RetrievedSource:
    from knowledge_base.citations import Citation

    citation = Citation(
        source_type="book",
        book_id=f"b{idx}",
        book_title=f"Book {idx}",
        chapter_title="Chapter One",
        page=idx,
        chunk_id=f"chunk-{idx}",
    )
    return RetrievedSource(
        citation=citation,
        passage=passage,
        score=score,
        reference=citation.reference(),
        chunk_id=f"chunk-{idx}",
        fts_score=score,
        vector_score=None,
        retrievers=("fts",),
    )


# -------------------------------------------------------------- retrieval


class TestRetrieve:
    def test_sorts_by_score_and_respects_query_min_score(self) -> None:
        backend = StubBackend(
            [
                StubHit("c1", PASSAGE, 0.4),
                StubHit("c2", PASSAGE2, 0.9),
                StubHit("c3", "low", 0.1),
            ]
        )
        result = retrieve(
            _FakeSession(),  # type: ignore[arg-type]
            RetrievalQuery("x", min_score=0.3),
            backend=backend,
            model_name="m",
        )
        assert [s.chunk_id for s in result.sources] == ["c2", "c1"]
        assert result.used_fts is True
        assert result.used_vector is False
        assert result.note and "no embedding provider" in result.note

    def test_config_min_score_is_applied(self) -> None:
        backend = StubBackend([StubHit("c1", PASSAGE, 0.5)])
        result = retrieve(
            _FakeSession(),  # type: ignore[arg-type]
            RetrievalQuery("x"),
            backend=backend,
            config=RagConfig(min_score=0.7),
            model_name="m",
        )
        assert result.is_empty
        assert result.note == "no passages retrieved"

    def test_caps_at_k(self) -> None:
        backend = StubBackend(
            [
                StubHit("c1", PASSAGE, 0.9),
                StubHit("c2", PASSAGE2, 0.8),
                StubHit("c3", "x", 0.7),
            ]
        )
        result = retrieve(
            _FakeSession(),  # type: ignore[arg-type]
            RetrievalQuery("x", k=2),
            backend=backend,
            model_name="m",
        )
        assert len(result.sources) == 2

    def test_uses_vector_flag_when_hit_from_vector(self) -> None:
        backend = StubBackend(
            [StubHit("c1", PASSAGE, 0.9, vector_score=0.9, retrievers=("vector",))]
        )
        result = retrieve(
            _FakeSession(),  # type: ignore[arg-type]
            RetrievalQuery("x"),
            backend=backend,
            model_name="m",
        )
        assert result.used_vector is True
        assert result.used_fts is False

    def test_skips_hits_without_chunk_id_or_text(self) -> None:
        backend = StubBackend([StubHit("", "", 0.9), StubHit("c2", PASSAGE, 0.5)])
        result = retrieve(
            _FakeSession(),  # type: ignore[arg-type]
            RetrievalQuery("x"),
            backend=backend,
            model_name="m",
        )
        assert [s.chunk_id for s in result.sources] == ["c2"]


def test_to_source_rehydrates_citation_from_chunk(db: Session) -> None:
    sf = SourceFile(sha256="11" * 32, file_path="books/x.pdf", format=SourceFormat.PDF)
    db.add(sf)
    db.flush()
    book = Book(source_file_id=sf.id, title="Provenance Book")
    db.add(book)
    db.flush()
    chapter = Chapter(
        number=1,
        title="Chapter One",
        kind=ChapterKind.CHAPTER,
        book_id=book.id,
        source_file_id=sf.id,
    )
    db.add(chapter)
    db.flush()
    section = Section(
        number=1,
        title="Section One",
        chapter_id=chapter.id,
        book_id=book.id,
        source_file_id=sf.id,
    )
    db.add(section)
    db.flush()
    block = ContentBlock(
        book_id=book.id,
        chapter_id=chapter.id,
        section_id=section.id,
        source_file_id=sf.id,
        block_type=BlockType.PARAGRAPH,
        sequence=1,
        original_text=PASSAGE,
        status=ContentStatus.VALIDATED,
    )
    db.add(block)
    db.flush()
    chunk = ContentChunk(
        chunk_id="chunk-provenance",
        book_id=book.id,
        content_block_id=block.id,
        source_file_id=sf.id,
        chapter_id=chapter.id,
        section_id=section.id,
        language=Language.ENGLISH,
        token_count=8,
        page_start=1,
        page_end=1,
        sequence=1,
        text=PASSAGE,
        status=ContentStatus.VALIDATED,
    )
    db.add(chunk)
    db.flush()

    backend = StubBackend([StubHit("chunk-provenance", PASSAGE, 0.9)])
    result = retrieve(
        db,
        RetrievalQuery("transmission"),
        backend=backend,
        model_name="m",
    )
    assert len(result.sources) == 1
    source = result.sources[0]
    assert source.citation.book_title == "Provenance Book"
    assert source.citation.chapter_title == "Chapter One"
    assert source.citation.section_title == "Section One"
    assert source.citation.page in (1, None)
    assert "chunk-provenance" in source.reference


# -------------------------------------------------------------- generation


class TestVerifyGrounding:
    def test_no_sources_fails(self) -> None:
        grounded, notes = verify_grounding("hello", 0, fraction=0.6)
        assert not grounded
        assert "no sources" in notes[0]

    def test_no_markers_fails(self) -> None:
        grounded, _ = verify_grounding("plain answer with no cites", 3, fraction=0.6)
        assert not grounded

    def test_out_of_range_markers_fail(self) -> None:
        grounded, notes = verify_grounding("[S4] claim", 3, fraction=0.6)
        assert not grounded
        assert any("out of range" in n for n in notes)

    def test_full_attribution_passes(self) -> None:
        answer = "Claim from source one. [S1] Another claim. [S2]"
        grounded, _ = verify_grounding(answer, 3, fraction=0.6)
        assert grounded

    def test_low_attribution_fails(self) -> None:
        answer = "An unattributed claim. Another unattributed sentence. [S1] cited."
        grounded, notes = verify_grounding(answer, 3, fraction=0.6)
        assert not grounded
        assert any("1/3" in n for n in notes)


class TestRenderContext:
    def test_indexes_are_one_based(self) -> None:
        ctx = render_context((_mk_source(1), _mk_source(2)), RagConfig())
        assert [i for i, _ in ctx] == [1, 2]

    def test_truncates_over_long_passages(self) -> None:
        long_source = _mk_source(1, passage="word " * 500)
        ctx = render_context((long_source,), RagConfig(max_source_chars=50))
        assert len(ctx[0][1]) <= 51  # 50 chars + ellipsis

    def test_empty_sources(self) -> None:
        assert render_context((), RagConfig()) == []


class TestGenerateAnswer:
    def test_extractive_is_grounded_and_cites(self) -> None:
        sources = (_mk_source(1, score=0.9), _mk_source(2, score=0.6))
        answer, notes, grounded = generate_answer(
            "How did scholars transmit hadith?",
            sources,
            generator=ExtractiveGenerator(),
            config=RagConfig(),
        )
        assert grounded
        assert "[S1]" in answer
        assert any("cited" in note for note in notes)

    def test_empty_sources_produce_honest_answer(self) -> None:
        answer, _, grounded = generate_answer(
            "question", (), generator=ExtractiveGenerator(), config=RagConfig()
        )
        assert not grounded
        assert "No supporting passages" in answer

    def test_custom_generator_protocol(self) -> None:
        class FakeGenerator:
            name = "fake"

            def generate(self, question: str, context: list[tuple[int, str]]) -> str:
                if context:
                    return f"Answer grounded on {[i for i, _ in context]}. [S1]"
                return ""

        sources = (_mk_source(1),)
        answer, _, grounded = generate_answer(
            "q",
            sources,
            generator=FakeGenerator(),
            config=RagConfig(min_grounded_fraction=0.0),
        )
        assert grounded
        assert answer.startswith("Answer grounded on [1].")


# ------------------------------------------------------------------ service


class TestRagService:
    def test_dummy_provider_is_built(self) -> None:
        svc = RagService(settings=Settings(_env_file=None))
        bundle = svc._provider()
        assert bundle is not None
        provider, model, version = bundle
        assert provider.name == "dummy"
        assert model == "kb-dummy"
        assert version == "0.1.0"

    def test_unknown_provider_degrades_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("KB_EMBEDDING_PROVIDER", "no-such-engine")
        svc = RagService(settings=Settings(_env_file=None))
        assert svc._provider() is None

    def test_default_generator_is_extractive(self) -> None:
        svc = RagService(settings=Settings(_env_file=None))
        assert svc.generator.name == "extractive"

    def test_answer_contract_with_stub_backend(self, monkeypatch: pytest.MonkeyPatch) -> None:
        svc = RagService(settings=Settings(_env_file=None))
        backend = StubBackend([StubHit("c1", PASSAGE, 0.9)])
        query = RetrievalQuery("test")
        # Exercise the public pieces of the contract without the search index.
        result = retrieve(
            _FakeSession(),  # type: ignore[arg-type]
            query,
            backend=backend,
            model_name="kb-dummy",
        )
        answer, notes, grounded = generate_answer(
            query.question, result.sources, generator=svc.generator, config=svc.config
        )
        assert grounded
        assert "[S1]" in answer
        assert result.sources[0].reference  # human-readable citation present
