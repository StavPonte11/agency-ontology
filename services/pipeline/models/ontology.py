"""
Agency Ontology — Pydantic v2 Data Models
Single source of truth for all ontology entity shapes in Python.
All pipeline workers, LLM extractors, and retrieval services import from here.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# ── Enumerations ──────────────────────────────────────────────────────────────

class ConceptType(str, Enum):
    TERM = "TERM"
    SYSTEM = "SYSTEM"
    PROCESS = "PROCESS"
    METRIC = "METRIC"
    ENTITY = "ENTITY"
    CODENAME = "CODENAME"
    ROLE = "ROLE"
    DATASET = "DATASET"
    POLICY = "POLICY"


class TermType(str, Enum):
    OFFICIAL = "OFFICIAL"
    ALIAS = "ALIAS"
    ABBREVIATION = "ABBREVIATION"
    CODENAME = "CODENAME"
    DEPRECATED = "DEPRECATED"
    COLLOQUIAL = "COLLOQUIAL"
    TECHNICAL = "TECHNICAL"


class RelationType(str, Enum):
    IS_A = "IS_A"
    PART_OF = "PART_OF"
    DEPENDS_ON = "DEPENDS_ON"
    USES = "USES"
    GOVERNS = "GOVERNS"
    REPLACES = "REPLACES"
    REPORTS_TO = "REPORTS_TO"
    OWNED_BY = "OWNED_BY"
    PRODUCES = "PRODUCES"
    CONSUMES = "CONSUMES"
    RELATED_TO = "RELATED_TO"


class ConceptStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    REVIEWED = "REVIEWED"
    VERIFIED = "VERIFIED"
    DEPRECATED = "DEPRECATED"


class SensitivityLevel(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    SECRET = "SECRET"


class DataAssetType(str, Enum):
    TABLE = "TABLE"
    COLUMN = "COLUMN"
    VIEW = "VIEW"
    API = "API"
    REPORT = "REPORT"
    DASHBOARD = "DASHBOARD"
    PIPELINE = "PIPELINE"
    METRIC = "METRIC"


class MappingType(str, Enum):
    PRIMARY = "PRIMARY"
    PARTIAL = "PARTIAL"
    DERIVED = "DERIVED"


class DocumentType(str, Enum):
    PDF_DICTIONARY = "PDF_DICTIONARY"
    PDF_GENERAL = "PDF_GENERAL"
    CATALOG = "CATALOG"
    WIKI = "WIKI"
    CODE = "CODE"


class Language(str, Enum):
    EN = "en"
    HE = "he"
    MIXED = "mixed"


class PipelineStage(str, Enum):
    SOURCE_SCAN = "source_scan"
    EXTRACT = "extract"
    LLM_EXTRACT = "llm_extract"
    NORMALIZE = "normalize"
    COMMIT = "commit"
    REVIEW_QUEUE = "review_queue"
    INDEX_UPDATE = "index_update"
    FEEDBACK = "feedback"
    DLQ = "dlq"


class FeedbackType(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    INCORRECT = "INCORRECT"
    INCOMPLETE = "INCOMPLETE"
    WRONG_MAPPING = "WRONG_MAPPING"
    OUTDATED = "OUTDATED"


# ── Constrained types ─────────────────────────────────────────────────────────

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


# ── LLM Extraction Output Models (used with with_structured_output) ───────────

class ExtractedTerm(BaseModel):
    """A surface-form string by which a concept is referred to in source text."""

    surface_form: str = Field(
        description="The exact string as it appears in the source document"
    )
    term_type: TermType = Field(
        description=(
            "Classification: OFFICIAL name, ALIAS, ABBREVIATION, CODENAME, "
            "COLLOQUIAL, TECHNICAL, or DEPRECATED"
        )
    )
    language: Language = Field(
        default=Language.EN,
        description="Language of this term: 'en' for English, 'he' for Hebrew, 'mixed' for mixed",
    )

    model_config = {"use_enum_values": False}


class ExtractedRelationship(BaseModel):
    """A typed, directional relationship between two concepts."""

    from_concept_name: str = Field(
        description=(
            "Name of the source concept — must match a concept name in this response "
            "or be a well-known org concept"
        )
    )
    to_concept_name: str = Field(description="Name of the target concept")
    relation_type: RelationType = Field(
        description=(
            "Semantic type of relationship. Use RELATED_TO only if no more specific type applies."
        )
    )
    relation_label: Optional[str] = Field(
        default=None,
        description=(
            "Custom label if relation_type is RELATED_TO and a more specific description exists "
            "(e.g., 'is_used_by', 'feeds_into')"
        ),
    )
    confidence: Confidence = Field(
        description=(
            "Confidence 0.0–1.0 that this relationship is stated or strongly implied in the source"
        )
    )
    bidirectional: bool = Field(
        default=False,
        description="True only if the relationship is explicitly stated as bidirectional",
    )
    source_quote: str = Field(
        description="Exact sentence(s) from source text that support this relationship"
    )


class ExtractedDataMapping(BaseModel):
    """A mapping from a concept to a specific data asset (table, column, etc.)."""

    concept_name: str = Field(
        description="Name of the concept being mapped — must match a concept in this extraction"
    )
    data_asset_qualified_name: str = Field(
        description=(
            "Qualified name: 'database.schema.table' or 'schema.table' or 'table.column'"
        )
    )
    mapping_type: MappingType = Field(
        description=(
            "PRIMARY = concept primarily lives here; "
            "PARTIAL = one aspect lives here; "
            "DERIVED = computed/aggregated"
        )
    )
    confidence: Confidence = Field(
        description="Confidence 0.0–1.0 that this data mapping is stated in the source"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Any qualifying notes about this mapping",
    )


class ExtractedConcept(BaseModel):
    """
    A named organizational entity extracted from source text.
    Can be a system, project, process, metric, role, codename, dataset, policy, or term.
    """

    name: str = Field(
        description="Canonical English name — the most official or complete form of the name"
    )
    name_he: Optional[str] = Field(
        default=None,
        description="Hebrew name if explicitly present in the source text",
    )
    description: str = Field(
        description=(
            "1–3 sentence definition of this concept, drawn directly from the source text. "
            "Do not paraphrase beyond what the source states."
        )
    )
    description_he: Optional[str] = Field(
        default=None,
        description="Hebrew description if source contains it",
    )
    concept_type: ConceptType = Field(
        description=(
            "Best-fit type: TERM, SYSTEM, PROCESS, METRIC, ENTITY, CODENAME, ROLE, DATASET, or POLICY"
        )
    )
    domain: list[str] = Field(
        description=(
            "List of business domains this concept belongs to, "
            "e.g. ['Finance', 'Customer', 'Operations']"
        )
    )
    terms: list[ExtractedTerm] = Field(
        description="All surface forms of this concept seen in the source, including the canonical name"
    )
    confidence: Confidence = Field(
        description=(
            "Overall confidence 0.0–1.0 in this extraction. "
            "Reduce if definition is vague, ambiguous, or implied rather than explicit."
        )
    )
    source_quote: str = Field(
        description="The exact sentence(s) from the source text that define this concept. Required."
    )

    @field_validator("terms")
    @classmethod
    def terms_must_include_name(
        cls, v: list[ExtractedTerm], info: Any
    ) -> list[ExtractedTerm]:
        """Ensure the canonical name appears as an OFFICIAL term."""
        name = info.data.get("name", "")
        names_in_terms = [t.surface_form for t in v]
        if name and name not in names_in_terms:
            v.insert(
                0,
                ExtractedTerm(
                    surface_form=name,
                    term_type=TermType.OFFICIAL,
                    language=Language.EN,
                ),
            )
        return v

    @field_validator("domain")
    @classmethod
    def domain_must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            return ["General"]
        return v


class LLMExtractionOutput(BaseModel):
    """
    Complete structured output from the LLM extraction stage for a single document chunk.
    This model is passed directly to with_structured_output().
    All fields are required. Return empty lists if nothing was found — never omit fields.
    """

    concepts: list[ExtractedConcept] = Field(
        description="All organizational concepts found in this text chunk. Empty list if none."
    )
    relationships: list[ExtractedRelationship] = Field(
        description=(
            "All relationships between concepts found in this chunk. Empty list if none."
        )
    )
    data_mappings: list[ExtractedDataMapping] = Field(
        description=(
            "Any explicit mappings between concepts and data assets. Empty list if none."
        )
    )
    chunk_summary: str = Field(
        description=(
            "One sentence describing what this chunk is about "
            "(used for pipeline logging, not stored in graph)"
        )
    )
    extraction_notes: Optional[str] = Field(
        default=None,
        description=(
            "Any ambiguities, conflicts, or low-confidence items worth flagging for human review"
        ),
    )


# ── Internal graph node models ─────────────────────────────────────────────────

class ConceptNode(BaseModel):
    """Internal representation of a Concept node, before/after Neo4j persistence."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    name_he: Optional[str] = None
    description: str
    description_he: Optional[str] = None
    domain: list[str]
    concept_type: ConceptType
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    status: ConceptStatus = ConceptStatus.CANDIDATE
    confidence: Confidence
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    sources: list[str] = Field(default_factory=list)
    usage_count: int = 0
    last_used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # TODO(permissions): Add `accessible_to: list[str]` field here when
    # permission scoping is enforced. Check this against the requesting agent's
    # permission context before returning the node.


class TermNode(BaseModel):
    """A surface form / alias node linked to a Concept."""

    id: UUID = Field(default_factory=uuid4)
    surface_form: str
    normalized_form: str
    language: Language
    term_type: TermType
    frequency: int = 1
    first_seen_at: datetime = Field(default_factory=datetime.utcnow)
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("normalized_form", mode="before")
    @classmethod
    def auto_normalize(cls, v: str, info: Any) -> str:
        if not v:
            surface = info.data.get("surface_form", "")
            return surface.lower().strip().replace("-", " ").replace("_", " ")
        return v.lower().strip()


class DataAssetNode(BaseModel):
    """A data asset (table, column, API, etc.) mapped to a Concept."""

    id: UUID = Field(default_factory=uuid4)
    external_id: str
    name: str
    qualified_name: str
    asset_type: DataAssetType
    description: Optional[str] = None
    data_type: Optional[str] = None
    service: Optional[str] = None
    database: Optional[str] = None
    schema_name: Optional[str] = None
    tier: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    owner: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_synced_at: datetime = Field(default_factory=datetime.utcnow)


class DocumentNode(BaseModel):
    """A source document node — tracks provenance of concept extractions."""

    id: UUID = Field(default_factory=uuid4)
    external_id: str
    title: str
    document_type: DocumentType
    content_hash: str
    connector_id: str
    connector_type: str
    page_count: Optional[int] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_processed_at: datetime = Field(default_factory=datetime.utcnow)


# ── Pipeline message envelope ──────────────────────────────────────────────────

class PipelineMessage(BaseModel):
    """
    Envelope for all Kafka messages in the ontology pipeline.
    Partition key strategy:
    - EXTRACT, LLM_EXTRACT, NORMALIZE, COMMIT → key = document_id (ordered per document)
    - SOURCE_SCAN, INDEX_UPDATE → key = connector_id
    - DLQ → key = original_topic:original_partition
    """

    job_id: str = Field(description="IngestionJob UUID")
    correlation_id: str = Field(
        description="Tracks one document through all pipeline stages"
    )
    stage: str = Field(description="Current pipeline stage name — PipelineStage enum value")
    retry_count: int = Field(default=0, ge=0)
    langfuse_trace_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    payload: dict[str, Any] = Field(
        description="Stage-specific payload — typed by stage consumers"
    )


# ── Retrieval service response models ──────────────────────────────────────────

class ConceptRef(BaseModel):
    """Lightweight concept reference — used in lists/search results."""

    id: str
    name: str
    concept_type: ConceptType
    domain: list[str]


class RelatedConceptRef(BaseModel):
    """A related concept with relationship metadata."""

    name: str
    relation: str
    direction: str  # "outbound" | "inbound"
    confidence: Confidence


class DataAssetRef(BaseModel):
    """A data asset reference with mapping metadata."""

    qualified_name: str
    asset_type: DataAssetType
    mapping_type: MappingType
    description: Optional[str] = None


class ProvenanceInfo(BaseModel):
    """Provenance metadata for a concept."""

    primary_source: str
    sources_count: int
    last_updated: datetime


class LookupResult(BaseModel):
    """
    Successful concept lookup result.
    Returned when a term is found in the ontology.
    """

    found: bool = True
    concept: Optional[ConceptRef] = None
    definition: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    related: list[RelatedConceptRef] = Field(default_factory=list)
    data_assets: list[DataAssetRef] = Field(default_factory=list)
    provenance: Optional[ProvenanceInfo] = None
    confidence: Optional[Confidence] = None
    status: Optional[ConceptStatus] = None
    low_confidence: bool = False
    # Degraded mode: returned when Neo4j is unavailable but ES cache is available
    degraded_mode: bool = False
    degraded_reason: Optional[str] = None

    # TODO(permissions): Before returning, filter `data_assets` and `related`
    # based on the requesting agent's permission context. Remove CONFIDENTIAL/SECRET
    # assets from agents without sufficient clearance.


class NotFoundResult(BaseModel):
    """Returned when a term is not found in the ontology."""

    found: bool = False
    closest_candidates: list[ConceptRef] = Field(default_factory=list)
    degraded_mode: bool = False


# Discriminated union alias — use as response type in FastAPI
LookupResponse = LookupResult | NotFoundResult


class SearchResult(BaseModel):
    """A single search result with relevance score."""

    concept: ConceptRef
    description: str
    aliases: list[str] = Field(default_factory=list)
    score: float
    match_type: str  # "lexical" | "semantic" | "hybrid"


class SearchResponse(BaseModel):
    """Search endpoint response."""

    results: list[SearchResult]
    total: int
    query: str
    search_mode: str


class EnrichmentMatch(BaseModel):
    """A single concept match found during text enrichment."""

    term: str
    concept_id: str
    concept_name: str
    confidence: Confidence
    definition: str
    aliases: list[str] = Field(default_factory=list)


class EnrichResponse(BaseModel):
    """
    Context enrichment response.
    The context_block is pre-formatted for direct injection into an agent system prompt.
    """

    context_block: str
    matched_concepts: list[EnrichmentMatch]
    no_concepts_found: bool
    token_count_estimate: int


class SchemaContextColumn(BaseModel):
    """A database column with metadata."""

    name: str
    data_type: str
    description: Optional[str] = None
    is_primary_key: bool = False
    is_nullable: bool = True


class SchemaContextTable(BaseModel):
    """A database table with columns and relations — used by TextToSQL agents."""

    qualified_name: str
    description: Optional[str] = None
    columns: list[SchemaContextColumn]
    related_tables: list[dict[str, Any]] = Field(default_factory=list)


class SchemaContextResponse(BaseModel):
    """Response from the schema-context endpoint."""

    tables: list[SchemaContextTable]
    unmapped_concepts: list[str]


class FeedbackResponse(BaseModel):
    """Feedback acknowledgment."""

    acknowledged: bool
    feedback_id: str


# ── Elasticsearch document shapes (as written to/read from ES) ─────────────────

class ConceptESDocument(BaseModel):
    """Document shape for the agency-ontology-concepts Elasticsearch index."""

    concept_id: str
    name: str
    name_he: Optional[str] = None
    description: str
    description_he: Optional[str] = None
    aliases: list[str] = Field(default_factory=list)
    concept_type: str
    domain: list[str]
    status: str
    sensitivity: str
    confidence: float
    sources: list[str] = Field(default_factory=list)
    usage_count: int = 0
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    embedding: Optional[list[float]] = None  # 1024-dim, set by embedding stage


class ChunkESDocument(BaseModel):
    """Document shape for the agency-ontology-chunks Elasticsearch index."""

    chunk_id: str
    document_id: str
    concept_ids: list[str] = Field(default_factory=list)
    content: str
    section_title: Optional[str] = None
    page_range: Optional[str] = None
    connector_id: str
    document_title: str
    created_at: datetime
    embedding: Optional[list[float]] = None  # 1024-dim
