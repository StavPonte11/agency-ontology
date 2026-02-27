/**
 * Agency Ontology — Zod Schemas (TypeScript)
 * Single source of truth for all TypeScript ontology types.
 * All tRPC procedure I/O and MCP tool definitions derive types from these schemas.
 * TypeScript types are derived via z.infer<typeof Schema> — never manually defined.
 */
import { z } from "zod"

// ── Enumerations ──────────────────────────────────────────────────────────────

export const ConceptTypeSchema = z.enum([
    "TERM",
    "SYSTEM",
    "PROCESS",
    "METRIC",
    "ENTITY",
    "CODENAME",
    "ROLE",
    "DATASET",
    "POLICY",
])
export type ConceptType = z.infer<typeof ConceptTypeSchema>

export const ConceptStatusSchema = z.enum([
    "CANDIDATE",
    "REVIEWED",
    "VERIFIED",
    "DEPRECATED",
])
export type ConceptStatus = z.infer<typeof ConceptStatusSchema>

export const SensitivityLevelSchema = z.enum([
    "PUBLIC",
    "INTERNAL",
    "CONFIDENTIAL",
    "SECRET",
])
export type SensitivityLevel = z.infer<typeof SensitivityLevelSchema>

export const TermTypeSchema = z.enum([
    "OFFICIAL",
    "ALIAS",
    "ABBREVIATION",
    "CODENAME",
    "DEPRECATED",
    "COLLOQUIAL",
    "TECHNICAL",
])
export type TermType = z.infer<typeof TermTypeSchema>

export const RelationTypeSchema = z.enum([
    "IS_A",
    "PART_OF",
    "DEPENDS_ON",
    "USES",
    "GOVERNS",
    "REPLACES",
    "REPORTS_TO",
    "OWNED_BY",
    "PRODUCES",
    "CONSUMES",
    "RELATED_TO",
])
export type RelationType = z.infer<typeof RelationTypeSchema>

export const DataAssetTypeSchema = z.enum([
    "TABLE",
    "COLUMN",
    "VIEW",
    "API",
    "REPORT",
    "DASHBOARD",
    "PIPELINE",
    "METRIC",
])
export type DataAssetType = z.infer<typeof DataAssetTypeSchema>

export const MappingTypeSchema = z.enum(["PRIMARY", "PARTIAL", "DERIVED"])
export type MappingType = z.infer<typeof MappingTypeSchema>

export const LanguageSchema = z.enum(["en", "he", "mixed"])
export type Language = z.infer<typeof LanguageSchema>

export const IngestionJobStatusSchema = z.enum([
    "QUEUED",
    "RUNNING",
    "EXTRACTING",
    "RESOLVING",
    "REVIEW",
    "COMMITTED",
    "FAILED",
    "SKIPPED",
])
export type IngestionJobStatus = z.infer<typeof IngestionJobStatusSchema>

export const FeedbackTypeSchema = z.enum([
    "POSITIVE",
    "NEGATIVE",
    "INCORRECT",
    "INCOMPLETE",
    "WRONG_MAPPING",
    "OUTDATED",
])
export type FeedbackType = z.infer<typeof FeedbackTypeSchema>

export const SearchModeSchema = z.enum(["lexical", "semantic", "hybrid"])
export type SearchMode = z.infer<typeof SearchModeSchema>

// ── Confidence ────────────────────────────────────────────────────────────────

export const ConfidenceSchema = z.number().min(0).max(1)

// ── Core entity schemas ───────────────────────────────────────────────────────

export const ConceptRefSchema = z.object({
    id: z.string().uuid(),
    name: z.string(),
    concept_type: ConceptTypeSchema,
    domain: z.array(z.string()),
})
export type ConceptRef = z.infer<typeof ConceptRefSchema>

export const RelatedConceptRefSchema = z.object({
    name: z.string(),
    relation: z.string(),
    direction: z.enum(["outbound", "inbound"]),
    confidence: ConfidenceSchema,
})
export type RelatedConceptRef = z.infer<typeof RelatedConceptRefSchema>

export const DataAssetRefSchema = z.object({
    qualified_name: z.string(),
    asset_type: DataAssetTypeSchema,
    mapping_type: MappingTypeSchema,
    description: z.string().nullable(),
})
export type DataAssetRef = z.infer<typeof DataAssetRefSchema>

export const TermSchema = z.object({
    surface_form: z.string(),
    term_type: TermTypeSchema,
    language: LanguageSchema,
})
export type Term = z.infer<typeof TermSchema>

export const ConceptDetailSchema = z.object({
    id: z.string().uuid(),
    name: z.string(),
    name_he: z.string().nullable(),
    description: z.string(),
    description_he: z.string().nullable(),
    domain: z.array(z.string()),
    concept_type: ConceptTypeSchema,
    sensitivity: SensitivityLevelSchema,
    status: ConceptStatusSchema,
    confidence: ConfidenceSchema,
    verified_by: z.string().nullable(),
    verified_at: z.string().datetime().nullable(),
    sources: z.array(z.string()),
    usage_count: z.number().int(),
    last_used_at: z.string().datetime().nullable(),
    created_at: z.string().datetime(),
    updated_at: z.string().datetime(),
    terms: z.array(TermSchema).optional(),
    data_assets: z.array(DataAssetRefSchema).optional(),
    related: z.array(RelatedConceptRefSchema).optional(),
})
export type ConceptDetail = z.infer<typeof ConceptDetailSchema>

// ── Lookup response (discriminated union) ─────────────────────────────────────

export const LookupFoundSchema = z.object({
    found: z.literal(true),
    concept: ConceptRefSchema,
    definition: z.string(),
    aliases: z.array(z.string()),
    related: z.array(RelatedConceptRefSchema),
    data_assets: z.array(DataAssetRefSchema),
    provenance: z.object({
        primary_source: z.string(),
        sources_count: z.number().int(),
        last_updated: z.string().datetime(),
    }),
    confidence: ConfidenceSchema,
    status: ConceptStatusSchema,
    low_confidence: z.boolean(),
    degraded_mode: z.boolean(),
    degraded_reason: z.string().nullable(),
})
export type LookupFound = z.infer<typeof LookupFoundSchema>

export const LookupNotFoundSchema = z.object({
    found: z.literal(false),
    closest_candidates: z.array(ConceptRefSchema),
    degraded_mode: z.boolean(),
})
export type LookupNotFound = z.infer<typeof LookupNotFoundSchema>

export const LookupResponseSchema = z.discriminatedUnion("found", [
    LookupFoundSchema,
    LookupNotFoundSchema,
])
export type LookupResponse = z.infer<typeof LookupResponseSchema>

// ── tRPC + MCP input schemas ──────────────────────────────────────────────────

export const LookupInputSchema = z.object({
    term: z.string().min(1).max(500),
    context: z.string().max(2000).optional(),
    agent_id: z.string().optional(),
    session_id: z.string().optional(),
    max_hops: z.number().int().min(1).max(5).default(2),
    include_data_assets: z.boolean().default(true),
})
export type LookupInput = z.infer<typeof LookupInputSchema>

export const SearchInputSchema = z.object({
    q: z.string().min(1).max(500),
    concept_types: z.array(ConceptTypeSchema).optional(),
    domains: z.array(z.string()).optional(),
    status: z.array(ConceptStatusSchema).optional(),
    confidence_min: ConfidenceSchema.optional(),
    has_data_assets: z.boolean().optional(),
    limit: z.number().int().min(1).max(100).default(20),
    offset: z.number().int().min(0).default(0),
    search_mode: SearchModeSchema.default("hybrid"),
})
export type SearchInput = z.infer<typeof SearchInputSchema>

export const EnrichInputSchema = z.object({
    text: z.string().min(1).max(10000),
    max_concepts: z.number().int().min(1).max(20).default(10),
    max_tokens_budget: z.number().int().min(100).max(4000).default(2000),
    agent_id: z.string().optional(),
    session_id: z.string().optional(),
})
export type EnrichInput = z.infer<typeof EnrichInputSchema>

export const SchemaContextInputSchema = z.object({
    concepts: z.array(z.string()).min(1).max(10),
    include_lineage: z.boolean().default(false),
    agent_id: z.string().optional(),
    session_id: z.string().optional(),
})
export type SchemaContextInput = z.infer<typeof SchemaContextInputSchema>

export const FeedbackInputSchema = z.object({
    concept_id: z.string().uuid(),
    feedback_type: FeedbackTypeSchema,
    agent_id: z.string().optional(),
    session_id: z.string().optional(),
    trace_id: z.string().optional(),
    context: z.string().max(1000).optional(),
    notes: z.string().max(2000).optional(),
})
export type FeedbackInput = z.infer<typeof FeedbackInputSchema>

// ── Pipeline / admin schemas ──────────────────────────────────────────────────

export const IngestionJobProgressSchema = z.object({
    stage: z.string(),
    pct: z.number().int().min(0).max(100),
    processed: z.number().int(),
    total: z.number().int(),
})
export type IngestionJobProgress = z.infer<typeof IngestionJobProgressSchema>

export const IngestionJobStatsSchema = z.object({
    concepts_extracted: z.number().int(),
    terms_extracted: z.number().int(),
    relationships_extracted: z.number().int(),
    review_items: z.number().int(),
    conflicts: z.number().int(),
    errors: z.number().int(),
})
export type IngestionJobStats = z.infer<typeof IngestionJobStatsSchema>

export const IngestionJobSchema = z.object({
    id: z.string().uuid(),
    connector_id: z.string(),
    connector_type: z.string(),
    source_ref: z.string(),
    status: IngestionJobStatusSchema,
    progress: IngestionJobProgressSchema.nullable(),
    stats: IngestionJobStatsSchema.nullable(),
    langfuse_trace_id: z.string().nullable(),
    started_at: z.string().datetime().nullable(),
    completed_at: z.string().datetime().nullable(),
    created_at: z.string().datetime(),
})
export type IngestionJob = z.infer<typeof IngestionJobSchema>

export const ConnectorTypeSchema = z.enum([
    "PDF",
    "OPENMETADATA",
    "CUSTOM_API",
    "CONFLUENCE",
    "GIT",
])
export type ConnectorType = z.infer<typeof ConnectorTypeSchema>

export const SourceConnectorSchema = z.object({
    id: z.string().uuid(),
    connector_type: ConnectorTypeSchema,
    name: z.string(),
    description: z.string().nullable(),
    enabled: z.boolean(),
    schedule: z.string().nullable(),
    last_run_at: z.string().datetime().nullable(),
    last_run_status: z.string().nullable(),
    created_at: z.string().datetime(),
    updated_at: z.string().datetime(),
})
export type SourceConnector = z.infer<typeof SourceConnectorSchema>

// ── Review item schemas ───────────────────────────────────────────────────────

export const ReviewItemStatusSchema = z.enum([
    "PENDING",
    "IN_REVIEW",
    "APPROVED",
    "REJECTED",
    "MERGED",
])
export type ReviewItemStatus = z.infer<typeof ReviewItemStatusSchema>

export const ReviewItemPrioritySchema = z.enum(["LOW", "MEDIUM", "HIGH", "CRITICAL"])
export type ReviewItemPriority = z.infer<typeof ReviewItemPrioritySchema>

export const ReviewItemSchema = z.object({
    id: z.string().uuid(),
    item_type: z.string(),
    status: ReviewItemStatusSchema,
    priority: ReviewItemPrioritySchema,
    source_job_id: z.string(),
    payload: z.record(z.unknown()),
    auto_extracted: z.record(z.unknown()),
    source_evidence: z.record(z.unknown()),
    conflicts_with: z.array(z.string()),
    similar_to: z.record(z.unknown()).nullable(),
    assigned_to: z.string().nullable(),
    reviewed_by: z.string().nullable(),
    reviewed_at: z.string().datetime().nullable(),
    reviewer_notes: z.string().nullable(),
    resolution: z.record(z.unknown()).nullable(),
    created_at: z.string().datetime(),
    updated_at: z.string().datetime(),
})
export type ReviewItem = z.infer<typeof ReviewItemSchema>

// ── Kafka / pipeline monitoring schemas ───────────────────────────────────────

export const KafkaConsumerLagSchema = z.object({
    topic: z.string(),
    partition: z.number().int(),
    consumer_group: z.string(),
    current_offset: z.number().int(),
    log_end_offset: z.number().int(),
    lag: z.number().int(),
})
export type KafkaConsumerLag = z.infer<typeof KafkaConsumerLagSchema>

export const PipelineStageHealthSchema = z.object({
    stage: z.string(),
    topic: z.string(),
    consumer_group: z.string(),
    total_lag: z.number().int(),
    worker_count: z.number().int(),
    processing_rate_per_min: z.number(),
    dlq_depth: z.number().int(),
    status: z.enum(["healthy", "degraded", "critical"]),
})
export type PipelineStageHealth = z.infer<typeof PipelineStageHealthSchema>

// ── Analytics schemas ─────────────────────────────────────────────────────────

export const OntologyStatsSchema = z.object({
    total_concepts: z.number().int(),
    by_type: z.record(ConceptTypeSchema, z.number().int()),
    by_status: z.record(ConceptStatusSchema, z.number().int()),
    by_domain: z.array(z.object({ domain: z.string(), count: z.number().int() })),
    total_terms: z.number().int(),
    total_relationships: z.number().int(),
    total_data_mappings: z.number().int(),
    total_sources: z.number().int(),
    low_confidence_count: z.number().int(),
    pending_review_count: z.number().int(),
    last_ingestion_at: z.string().datetime().nullable(),
})
export type OntologyStats = z.infer<typeof OntologyStatsSchema>
