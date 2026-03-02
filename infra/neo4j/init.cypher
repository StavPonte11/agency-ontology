// Neo4j initialization — Agency Ontology schema
// Run via: cypher-shell -u neo4j -p changeme < init.cypher
// Or mount as /var/lib/neo4j/conf/init.cypher and run on startup

// ── Unique constraints ────────────────────────────────────────────────────────
CREATE CONSTRAINT concept_id_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT term_id_unique IF NOT EXISTS FOR (t:Term) REQUIRE t.id IS UNIQUE;
CREATE CONSTRAINT dataasset_id_unique IF NOT EXISTS FOR (d:DataAsset) REQUIRE d.id IS UNIQUE;
CREATE CONSTRAINT document_id_unique IF NOT EXISTS FOR (doc:Document) REQUIRE doc.id IS UNIQUE;
CREATE CONSTRAINT dataasset_external_id_unique IF NOT EXISTS FOR (d:DataAsset) REQUIRE d.externalId IS UNIQUE;
CREATE CONSTRAINT connector_id_unique IF NOT EXISTS FOR (c:SourceConnector) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT job_id_unique IF NOT EXISTS FOR (j:IngestionJob) REQUIRE j.id IS UNIQUE;
// Hierarchical nodes
CREATE CONSTRAINT label_unique IF NOT EXISTS FOR (l:Label) REQUIRE (l.conceptId, l.language) IS UNIQUE;
CREATE CONSTRAINT statement_unique IF NOT EXISTS FOR (s:Statement) REQUIRE (s.conceptId, s.propertyId) IS UNIQUE;

// ── Full-text indexes (lexical — supplementary to Elasticsearch) ──────────────
CREATE FULLTEXT INDEX concept_fulltext IF NOT EXISTS FOR (c:Concept) ON EACH [c.name, c.description, c.nameHe, c.descriptionHe];
CREATE FULLTEXT INDEX term_fulltext IF NOT EXISTS FOR (t:Term) ON EACH [t.surfaceForm, t.normalizedForm];

// ── Standard lookup indexes ───────────────────────────────────────────────────
CREATE INDEX concept_status IF NOT EXISTS FOR (c:Concept) ON (c.status);
CREATE INDEX concept_type IF NOT EXISTS FOR (c:Concept) ON (c.conceptType);
CREATE INDEX concept_domain IF NOT EXISTS FOR (c:Concept) ON (c.domain);
CREATE INDEX concept_sensitivity IF NOT EXISTS FOR (c:Concept) ON (c.sensitivity);
CREATE INDEX concept_updated IF NOT EXISTS FOR (c:Concept) ON (c.updatedAt);
CREATE INDEX concept_usage IF NOT EXISTS FOR (c:Concept) ON (c.usageCount);
CREATE INDEX concept_is_class IF NOT EXISTS FOR (c:Concept) ON (c.isClass);
CREATE INDEX term_normalized IF NOT EXISTS FOR (t:Term) ON (t.normalizedForm);
CREATE INDEX term_language IF NOT EXISTS FOR (t:Term) ON (t.language);
CREATE INDEX dataasset_qualified IF NOT EXISTS FOR (d:DataAsset) ON (d.qualifiedName);
CREATE INDEX dataasset_type IF NOT EXISTS FOR (d:DataAsset) ON (d.assetType);
CREATE INDEX document_hash IF NOT EXISTS FOR (doc:Document) ON (doc.hash);
CREATE INDEX document_connector IF NOT EXISTS FOR (doc:Document) ON (doc.connectorId);
// Hierarchical node indexes
CREATE INDEX label_language IF NOT EXISTS FOR (l:Label) ON (l.language);
CREATE INDEX label_value IF NOT EXISTS FOR (l:Label) ON (l.label);
CREATE FULLTEXT INDEX label_fulltext IF NOT EXISTS FOR (l:Label) ON EACH [l.label, l.description];
CREATE INDEX statement_property IF NOT EXISTS FOR (s:Statement) ON (s.propertyId);

// ── NOTE: No vector index in Neo4j ────────────────────────────────────────────
// All semantic search is handled by Elasticsearch.
// Neo4j is used EXCLUSIVELY for graph traversal (Cypher queries).
// See infra/elasticsearch/concepts_mapping.json for vector index configuration.

// ── Relationship types (documentation — Neo4j relationship types are schema-less) ──
// :IS_A             — concept subtype/supertype
// :PART_OF          — composition / containment
// :DEPENDS_ON       — dependency
// :USES             — usage relationship
// :GOVERNS          — governance / policy
// :REPLACES         — replaces deprecated concept
// :REPORTS_TO       — org hierarchy
// :OWNED_BY         — ownership
// :PRODUCES         — produces artifact/output
// :CONSUMES         — consumes input
// :RELATED_TO       — unspecified relationship (with optional label property)
// :HAS_TERM         — Concept → Term (surface form)
// :MAPS_TO          — Concept → DataAsset (with mappingType property)
// :SOURCED_FROM     — Concept → Document (provenance)
// :EXTRACTED_FROM   — Concept → IngestionJob (traceability)
