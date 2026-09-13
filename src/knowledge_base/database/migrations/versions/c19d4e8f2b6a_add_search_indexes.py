"""Add full-text search indexes

Revision ID: c19d4e8f2b6a
Revises: b62e5a8c1d7f
Create Date: 2026-09-13

Search over the knowledge base is served by two index families:

* ``tsvector`` (GIN) full-text search over chunk documents, ayahs (and their
  translations) and hadiths. Every vector concatenates the language-aware
  stemmed component with a ``simple`` (verbatim-token) component so queries
  match consistently whatever language the document is in.
* ``pg_trgm`` (GIN) trigram indexes for substring/prefix matching over the
  short catalog fields: book title/subtitle, author names, chapter and
  section titles.

The vector columns are populated by BEFORE INSERT/UPDATE triggers so they can
never drift from the source text; existing rows are backfilled here.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c19d4e8f2b6a"
down_revision = "b62e5a8c1d7f"
branch_labels = None
depends_on = None


_REG = "CREATE OR REPLACE FUNCTION kb_search_config(lang kb_language) RETURNS regconfig LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT CASE lang WHEN 'ar'::kb_language THEN 'arabic'::regconfig WHEN 'en'::kb_language THEN 'english'::regconfig ELSE 'simple'::regconfig END $$;"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # --- config seam: kb_language enum -> regconfig -------------------------
    op.execute(_REG)
    op.execute(
        "CREATE OR REPLACE FUNCTION kb_search_config_code(code text) RETURNS regconfig "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ "
        "SELECT CASE lower(code) WHEN 'ar' THEN 'arabic'::regconfig "
        "WHEN 'en' THEN 'english'::regconfig ELSE 'simple'::regconfig END $$;"
    )

    # --- search_documents: title + body -------------------------------------
    op.execute(
        "CREATE OR REPLACE FUNCTION kb_tsvector_search_documents() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN "
        "NEW.search_vector := to_tsvector(kb_search_config(NEW.language), "
        "coalesce(NEW.title, '') || ' ' || NEW.body_text) || "
        "to_tsvector('simple'::regconfig, coalesce(NEW.title, '') || ' ' || NEW.body_text); "
        "RETURN NEW; END $$;"
    )
    op.execute(
        "CREATE TRIGGER trg_search_documents_tsvector BEFORE INSERT OR UPDATE OF "
        "body_text, language, title ON search_documents FOR EACH ROW "
        "EXECUTE FUNCTION kb_tsvector_search_documents();"
    )
    op.drop_constraint(
        "search_documents_content_chunk_id_fkey", "search_documents", type_="foreignkey"
    )
    op.create_foreign_key(
        "search_documents_content_chunk_id_fkey",
        "search_documents",
        "content_chunks",
        ["content_chunk_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- ayahs (Arabic) ------------------------------------------------------
    op.add_column("ayahs", sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True))
    op.execute(
        "CREATE OR REPLACE FUNCTION kb_tsvector_ayah() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN NEW.search_vector := to_tsvector('arabic'::regconfig, NEW.text) || "
        "to_tsvector('simple'::regconfig, NEW.text); RETURN NEW; END $$;"
    )
    op.execute(
        "CREATE TRIGGER trg_ayahs_tsvector BEFORE INSERT OR UPDATE OF text ON ayahs "
        "FOR EACH ROW EXECUTE FUNCTION kb_tsvector_ayah();"
    )
    op.execute(
        "UPDATE ayahs SET search_vector = to_tsvector('arabic', text) || "
        "to_tsvector('simple', text)"
    )
    op.create_index("ix_ayahs_search_vector", "ayahs", ["search_vector"], postgresql_using="gin")

    # --- ayah translations ----------------------------------------------------
    op.add_column(
        "ayah_translations", sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True)
    )
    op.execute(
        "CREATE OR REPLACE FUNCTION kb_tsvector_ayah_translation() RETURNS trigger "
        "LANGUAGE plpgsql AS $$ BEGIN NEW.search_vector := "
        "to_tsvector(kb_search_config_code(NEW.language), NEW.text) || "
        "to_tsvector('simple'::regconfig, NEW.text); RETURN NEW; END $$;"
    )
    op.execute(
        "CREATE TRIGGER trg_ayah_translations_tsvector BEFORE INSERT OR UPDATE OF text, "
        "language ON ayah_translations FOR EACH ROW "
        "EXECUTE FUNCTION kb_tsvector_ayah_translation();"
    )
    op.execute(
        "UPDATE ayah_translations SET search_vector = "
        "to_tsvector(kb_search_config_code(language), text) || "
        "to_tsvector('simple', text)"
    )
    op.create_index(
        "ix_ayah_translations_search_vector", "ayah_translations", ["search_vector"],
        postgresql_using="gin",
    )

    # --- hadiths: English text + Arabic original -----------------------------
    op.add_column("hadiths", sa.Column("search_vector", postgresql.TSVECTOR(), nullable=True))
    op.execute(
        "CREATE OR REPLACE FUNCTION kb_tsvector_hadith() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN NEW.search_vector := to_tsvector('english'::regconfig, coalesce(NEW.text, '')) "
        "|| to_tsvector('arabic'::regconfig, coalesce(NEW.text_arabic, '')) || "
        "to_tsvector('simple'::regconfig, coalesce(NEW.text, '') || ' ' "
        "|| coalesce(NEW.text_arabic, '')); RETURN NEW; END $$;"
    )
    op.execute(
        "CREATE TRIGGER trg_hadiths_tsvector BEFORE INSERT OR UPDATE OF text, text_arabic "
        "ON hadiths FOR EACH ROW EXECUTE FUNCTION kb_tsvector_hadith();"
    )
    op.execute(
        "UPDATE hadiths SET search_vector = to_tsvector('english', coalesce(text, '')) || "
        "to_tsvector('arabic', coalesce(text_arabic, '')) || "
        "to_tsvector('simple', coalesce(text, '') || ' ' || coalesce(text_arabic, ''))"
    )
    op.create_index("ix_hadiths_search_vector", "hadiths", ["search_vector"], postgresql_using="gin")

    # --- trigram indexes for catalog substring search ------------------------
    op.execute("CREATE INDEX ix_books_title_trgm ON books USING gin (lower(title) gin_trgm_ops)")
    op.execute("CREATE INDEX ix_books_subtitle_trgm ON books USING gin (lower(subtitle) gin_trgm_ops)")
    op.execute("CREATE INDEX ix_authors_name_trgm ON authors USING gin (lower(name) gin_trgm_ops)")
    op.execute(
        "CREATE INDEX ix_authors_name_arabic_trgm ON authors USING gin "
        "(lower(name_arabic) gin_trgm_ops)"
    )
    op.execute("CREATE INDEX ix_chapters_title_trgm ON chapters USING gin (lower(title) gin_trgm_ops)")
    op.execute("CREATE INDEX ix_sections_title_trgm ON sections USING gin (lower(title) gin_trgm_ops)")


def downgrade() -> None:
    for name, _table in (
        ("ix_books_title_trgm", "books"),
        ("ix_books_subtitle_trgm", "books"),
        ("ix_authors_name_trgm", "authors"),
        ("ix_authors_name_arabic_trgm", "authors"),
        ("ix_chapters_title_trgm", "chapters"),
        ("ix_sections_title_trgm", "sections"),
        ("ix_hadiths_search_vector", "hadiths"),
        ("ix_ayah_translations_search_vector", "ayah_translations"),
        ("ix_ayahs_search_vector", "ayahs"),
    ):
        op.execute(f"DROP INDEX IF EXISTS {name}")

    op.execute("DROP TRIGGER IF EXISTS trg_hadiths_tsvector ON hadiths")
    op.execute("DROP TRIGGER IF EXISTS trg_ayah_translations_tsvector ON ayah_translations")
    op.execute("DROP TRIGGER IF EXISTS trg_ayahs_tsvector ON ayahs")
    op.execute("DROP TRIGGER IF EXISTS trg_search_documents_tsvector ON search_documents")
    op.execute("DROP FUNCTION IF EXISTS kb_tsvector_hadith()")
    op.execute("DROP FUNCTION IF EXISTS kb_tsvector_ayah_translation()")
    op.execute("DROP FUNCTION IF EXISTS kb_tsvector_ayah()")
    op.execute("DROP FUNCTION IF EXISTS kb_tsvector_search_documents()")
    op.execute("DROP FUNCTION IF EXISTS kb_search_config_code(text)")
    op.execute("DROP FUNCTION IF EXISTS kb_search_config(kb_language)")

    op.drop_constraint(
        "search_documents_content_chunk_id_fkey", "search_documents", type_="foreignkey"
    )
    op.create_foreign_key(
        "search_documents_content_chunk_id_fkey",
        "search_documents",
        "content_chunks",
        ["content_chunk_id"],
        ["id"],
    )
    op.drop_column("hadiths", "search_vector")
    op.drop_column("ayah_translations", "search_vector")
    op.drop_column("ayahs", "search_vector")