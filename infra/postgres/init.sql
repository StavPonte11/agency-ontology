-- PostgreSQL initialization script
-- Creates additional databases needed by LangFuse and GlitchTip
-- Run by docker-entrypoint-initdb.d on first startup

-- LangFuse database
CREATE DATABASE langfuse
  WITH OWNER = agency
  ENCODING = 'UTF8'
  LC_COLLATE = 'en_US.utf8'
  LC_CTYPE = 'en_US.utf8';

-- GlitchTip database
CREATE DATABASE glitchtip
  WITH OWNER = agency
  ENCODING = 'UTF8'
  LC_COLLATE = 'en_US.utf8'
  LC_CTYPE = 'en_US.utf8';

-- Extensions for main DB
\c agency_ontology;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- Trigram search for fuzzy matching

-- ── Hierarchical ontology: ancestor path materialization ──────────────────────
-- Stores pre-computed ancestor chains per concept for O(1) class-scoped ES queries.
-- Recomputed whenever INSTANCE_OF / SUBCLASS_OF edges change in Neo4j.
CREATE TABLE IF NOT EXISTS concept_ancestor_cache (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_id     TEXT NOT NULL,
  ancestor_id    TEXT NOT NULL,
  depth          INT  NOT NULL CHECK (depth > 0 AND depth <= 10),
  relation_path  TEXT NOT NULL,  -- e.g. 'INSTANCE_OF>SUBCLASS_OF>SUBCLASS_OF'
  computed_at    TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_concept_ancestor UNIQUE (concept_id, ancestor_id)
);
CREATE INDEX IF NOT EXISTS idx_anc_cache_concept  ON concept_ancestor_cache (concept_id);
CREATE INDEX IF NOT EXISTS idx_anc_cache_ancestor ON concept_ancestor_cache (ancestor_id);
CREATE INDEX IF NOT EXISTS idx_anc_cache_depth    ON concept_ancestor_cache (depth);
