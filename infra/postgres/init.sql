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
