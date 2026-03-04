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
    # General semantic relationships
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
    # Strict hierarchical types — Wikidata-style
    INSTANCE_OF = "INSTANCE_OF"       # specific entity → its class
    SUBCLASS_OF = "SUBCLASS_OF"       # class → its superclass
    PART_OF_HIERARCHY = "PART_OF_HIERARCHY"  # structural containment in org hierarchy


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

    @model_validator(mode="before")
    @classmethod
    def coerce_missing_name(
        cls, values: Any,
    ) -> Any:
        """
        Robustness shim for local LLMs that produce `name_he` or `canonical_name`
        instead of the required `name` field.
        """
        if isinstance(values, dict):
            if not values.get("name"):
                # Prefer name_he, then canonical_name, then surface_form of first term
                fallback = (
                    values.get("name_he")
                    or values.get("canonical_name")
                    or values.get("canonical")
                )
                if not fallback and values.get("terms"):
                    first_term = values["terms"][0]
                    if isinstance(first_term, dict):
                        fallback = first_term.get("surface_form")
                    elif hasattr(first_term, "surface_form"):
                        fallback = first_term.surface_form
                if fallback:
                    values["name"] = fallback
            if not values.get("description"):
                # Fall back to description_he or empty string
                values["description"] = values.get("description_he") or ""
        return values

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
        default="",
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


# ── Hierarchical ontology models (Wikidata-style inheritance) ────────────────────

class StatementValue(BaseModel):
    """
    A single property-value statement on a concept, modelled after Wikidata statements.
    Holds exactly one value depending on value_type.
    """
    property_id: str = Field(
        description="Property identifier, e.g. 'instance_of', 'inception', 'parent_unit'"
    )
    property_label: str = Field(
        description="Human-readable property label in English"
    )
    value_type: str = Field(
        description="'concept_ref' | 'string' | 'date' | 'number' | 'multilingual'"
    )
    # Exactly one of the following is populated:
    concept_ref_id: Optional[str] = Field(
        default=None,
        description="If value_type='concept_ref': canonical name of the referenced concept"
    )
    string_value: Optional[str] = Field(
        default=None,
        description="If value_type='string' | 'date' | 'number': raw value as string"
    )
    multilingual_values: Optional[dict[str, str]] = Field(
        default=None,
        description="If value_type='multilingual': lang_code → value, e.g. {'en': 'Brigade', 'he': 'חטיבה'}"
    )
    confidence: Confidence = Field(default=0.8)
    source_quote: Optional[str] = Field(
        default=None, description="Source sentence supporting this statement"
    )


class MultilingualLabel(BaseModel):
    """
    A label (name) for a concept in a specific language.
    Mirrors Wikidata's label/description/alias structure per language.
    """
    language: str = Field(description="BCP-47 language code: 'en', 'he', 'ar'")
    label: str = Field(description="Primary label in this language")
    description: Optional[str] = Field(
        default=None,
        description="Short disambiguating description in this language (1 sentence)"
    )
    aliases: list[str] = Field(
        default_factory=list,
        description="Additional names/aliases in this language"
    )


class HierarchyRelation(BaseModel):
    """Explicit hierarchical relationship — strictly typed, separate from RELATED_TO."""
    relation: str = Field(
        description="'INSTANCE_OF' | 'SUBCLASS_OF' | 'PART_OF_HIERARCHY'"
    )
    target_concept_name: str = Field(
        description="Canonical name of the parent class or type concept"
    )
    confidence: Confidence
    source_quote: Optional[str] = None


class HierarchicalConcept(BaseModel):
    """
    Extends ExtractedConcept with Wikidata-style hierarchical statements
    and per-language multilingual labels.

    IMPORTANT extraction rules for the LLM:
    - INSTANCE_OF: use when this concept is a SPECIFIC named entity/instance of a class.
      Example: 'Judea Territorial Brigade' INSTANCE_OF 'Territorial Brigade'
    - SUBCLASS_OF: use when this concept is a CATEGORY that specialises a broader category.
      Example: 'Territorial Brigade' SUBCLASS_OF 'Brigade'
    - PART_OF_HIERARCHY: use for structural containment in org/system hierarchy.
      Example: 'Alpha Squadron' PART_OF_HIERARCHY 'Delta Battalion'
    - is_class=True when this concept is a type/category others are instances of.
    """

    # Core fields (same meaning as ExtractedConcept)
    name: str = Field(description="Canonical English name")
    description: str = Field(description="1-3 sentence definition from source text")
    concept_type: ConceptType
    domain: list[str]
    confidence: Confidence
    source_quote: str

    @model_validator(mode="before")
    @classmethod
    def coerce_missing_name(
        cls, values: Any,
    ) -> Any:
        """Same robustness shim as ExtractedConcept — coerce name_he → name."""
        if isinstance(values, dict):
            if not values.get("name"):
                fallback = (
                    values.get("name_he")
                    or values.get("canonical_name")
                    or values.get("canonical")
                )
                if not fallback and values.get("multilingual_labels"):
                    first = values["multilingual_labels"][0]
                    if isinstance(first, dict):
                        fallback = first.get("label")
                if fallback:
                    values["name"] = fallback
            if not values.get("description"):
                values["description"] = values.get("description_he") or ""
        return values

    # Hierarchical extensions
    multilingual_labels: list[MultilingualLabel] = Field(
        default_factory=list,
        description=(
            "All language variants of this concept's name, description, and aliases. "
            "Include every language present in the source. "
            "Example: [{language: 'he', label: 'חטיבת יהודה', aliases: ['חטמ\"ר יהודה', 'חטיבת חברון']}]"
        )
    )
    hierarchy: list[HierarchyRelation] = Field(
        default_factory=list,
        description=(
            "Hierarchical position of this concept. Use INSTANCE_OF for specific named entities, "
            "SUBCLASS_OF for categories. PART_OF_HIERARCHY for structural containment."
        )
    )
    statements: list[StatementValue] = Field(
        default_factory=list,
        description=(
            "Structured property-value facts: inception, dissolution, parent_unit, "
            "location, commander, capacity, status, classification, version, owner. "
            "Example: {property_id: 'inception', value_type: 'date', string_value: '1988'}"
        )
    )
    is_class: bool = Field(
        default=False,
        description=(
            "True if this concept is a CLASS or TYPE (a category that other things are instances of). "
            "Example: 'Brigade' is a class. 'Judea Territorial Brigade' is NOT a class."
        )
    )
    is_deprecated: bool = Field(
        default=False,
        description="True if the source states this concept is obsolete or decommissioned"
    )
    superseded_by: Optional[str] = Field(
        default=None,
        description="If is_deprecated=True: canonical name of the replacement concept, if stated"
    )

    @field_validator("domain")
    @classmethod
    def domain_must_not_be_empty(cls, v: list[str]) -> list[str]:
        return v if v else ["General"]


class HierarchicalExtractionOutput(BaseModel):
    """
    Superset of LLMExtractionOutput — adds Wikidata-style hierarchy to extracted concepts.
    Used when document_type=PDF_DICTIONARY/CATALOG, or when chunk content contains
    at least 2 hierarchy-signal keywords.

    Fallback: if hierarchy/statements fields are empty lists, this is functionally
    identical to LLMExtractionOutput — using it on flat content is always safe.
    """
    concepts: list[HierarchicalConcept] = Field(
        description="All organizational concepts found in this text chunk. Empty list if none."
    )
    relationships: list[ExtractedRelationship] = Field(
        description="Non-hierarchical relationships (same as LLMExtractionOutput)."
    )
    data_mappings: list[ExtractedDataMapping] = Field(
        description="Data asset mappings (same as LLMExtractionOutput)."
    )
    chunk_summary: str = Field(
        default="",
        description="One sentence describing what this chunk is about."
    )
    extraction_notes: Optional[str] = Field(
        default=None,
        description="Ambiguities, conflicts, or low-confidence items to flag for review."
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
    weight: Optional[float] = None
    meaning: Optional[str] = None


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


class HierarchyPathStep(BaseModel):
    """One hop in an ancestor chain — used in LookupResult.ancestor_path."""
    concept_id: str
    concept_name: str
    relation: str   # INSTANCE_OF | SUBCLASS_OF | PART_OF_HIERARCHY


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

    # ── Hierarchical fields (Wikidata-style) ──────────────────────────────
    is_class: bool = False
    is_deprecated: bool = False
    superseded_by: Optional[str] = None
    ancestor_path: list[HierarchyPathStep] = Field(
        default_factory=list,
        description="Full chain from this concept up to root class, nearest-first."
    )
    subclasses: list[ConceptRef] = Field(
        default_factory=list,
        description="Direct subclasses of this concept (populated when is_class=True)"
    )
    instances: list[ConceptRef] = Field(
        default_factory=list,
        description="Direct instances of this concept (populated when is_class=True)"
    )
    multilingual_labels: list["MultilingualLabel"] = Field(
        default_factory=list,
        description="All language variants: labels, descriptions, aliases"
    )
    statements: list["StatementValue"] = Field(
        default_factory=list,
        description="Structured property-value facts: inception, parent_unit, etc."
    )
    inherited_context: Optional[str] = Field(
        default=None,
        description=(
            "Auto-assembled context block from ancestor concepts (bounded ~500 tokens). "
            "Agents use this as additional context inherited from class membership."
        )
    )

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
    # ── Hierarchical fields ──────────────────────────────────────────────
    is_class: bool = False
    is_deprecated: bool = False
    ancestor_ids: list[str] = Field(default_factory=list)    # pre-computed for O(1) class-scoped search
    ancestor_names: list[str] = Field(default_factory=list)
    instance_of: Optional[str] = None      # direct parent class name
    subclass_of: Optional[str] = None      # direct superclass name (if itself a class)
    hierarchy_depth: int = 0               # 0 = root class, increases downward
    labels: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Nested multilingual label objects: {language, label, description, aliases}"
    )
    statements: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Nested statement objects: {property_id, property_label, value_type, value}"
    )


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


# ═══════════════════════════════════════════════════════════════════════════════
# IMPACT ANALYSIS & CONSEQUENCE MAPPING DOMAIN MODELS
# Implements the Five-Layer Impact Stack from the spec.
# These models extend the existing ontology layer — every impact entity is also
# a Concept node; these models describe the operational properties added on top.
# ═══════════════════════════════════════════════════════════════════════════════


# ── Impact Enumerations ───────────────────────────────────────────────────────

class OperationalStatus(str, Enum):
    """Operational lifecycle state of a project or entity.
    PLANNED status is the most important discriminator — it halts severity
    propagation in the engine (spec Part 1.2, Part 10).
    """
    ACTIVE = "ACTIVE"
    PLANNED = "PLANNED"       # never been operational — delays only, not harm
    SUSPENDED = "SUSPENDED"   # was operational, now paused
    CLOSED = "CLOSED"         # permanently decommissioned


class ImpactCriticality(str, Enum):
    """Criticality level for impact entities and dependency edges."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NEGLIGIBLE = "NEGLIGIBLE"


class ClientTier(str, Enum):
    """Client/stakeholder tier for SLA prioritisation."""
    TIER_1 = "TIER_1"   # highest priority, shortest SLA breach window
    TIER_2 = "TIER_2"
    TIER_3 = "TIER_3"


class PropagationMode(str, Enum):
    """How impact propagates across a dependency edge."""
    DIRECT = "DIRECT"           # immediate and certain
    CONDITIONAL = "CONDITIONAL" # depends on a condition string
    TIME_DELAYED = "TIME_DELAYED"  # appears after N hours/days
    PARTIAL = "PARTIAL"         # only some functions affected


class ImpactEntityType(str, Enum):
    """Entity types in the impact domain (maps to Concept node subtypes)."""
    LOCATION = "LOCATION"
    DEPARTMENT = "DEPARTMENT"
    PROJECT = "PROJECT"
    CLIENT = "CLIENT"
    ASSET = "ASSET"
    SYSTEM = "SYSTEM"
    PROCESS = "PROCESS"
    PERSONNEL = "PERSONNEL"
    OBLIGATION = "OBLIGATION"


class DependencyEdgeType(str, Enum):
    """Typed dependency relationship types between impact entities."""
    HOSTS = "HOSTS"           # Location -> Department | Asset | System | Personnel
    RUNS = "RUNS"             # Department -> Project | Process
    OPERATES = "OPERATES"     # Department -> Asset | System
    SERVES = "SERVES"         # Project -> Client | Obligation
    USES = "USES"             # Project | Process -> Asset | System
    REPORTS_TO = "REPORTS_TO" # Department -> Department
    BACKUP_FOR = "BACKUP_FOR" # Asset | Location | System -> Asset | Location | System
    FEEDS = "FEEDS"           # System -> System
    BLOCKS = "BLOCKS"         # Project -> Project (sequencing)
    STAFFED_BY = "STAFFED_BY" # Department | Project -> Personnel
    # Extended edge types for facility/site Excel schema
    CONTAINS = "CONTAINS"               # Site -> Facility, Facility -> Component
    PART_OF_SYSTEM = "PART_OF_SYSTEM"   # Facility/Component -> System
    OPERATED_BY = "OPERATED_BY"         # Facility -> ResponsibleBody
    POWERED_BY = "POWERED_BY"           # Facility -> PowerStation
    FUELED_BY = "FUELED_BY"             # Facility -> FuelReserve
    PROTECTED_BY = "PROTECTED_BY"       # Facility -> DefenseSystem (Iron Dome, etc.)
    AERIAL_DEFENSE_ZONE = "AERIAL_DEFENSE_ZONE"  # Facility -> AerialDefenseZone
    RELATED_TO = "RELATED_TO"           # Facility -> RelatedFacility (generic)
    AFFECTS = "AFFECTS"                 # Facility -> Facility (operational impact)


class ImpactNodeType(str, Enum):
    """Node types specific to the facility/site impact domain."""
    SITE = "SITE"                       # Top-level site (site_name column)
    FACILITY = "FACILITY"               # Facility within a site (facility_name column)
    COMPONENT = "COMPONENT"             # Component within a facility (component_name column)
    SYSTEM = "SYSTEM"                   # Named system (system column)
    RESPONSIBLE_BODY = "RESPONSIBLE_BODY"  # Organization operating a facility
    POWER_STATION = "POWER_STATION"     # Power station (connected_power_station)
    FUEL_RESERVE = "FUEL_RESERVE"       # Fuel reserve (connection_to_strategic_fuel_reserves)
    DEFENSE_SYSTEM = "DEFENSE_SYSTEM"   # Defense system (Iron Dome, upper layer, etc.)
    AERIAL_DEFENSE_ZONE = "AERIAL_DEFENSE_ZONE"  # Aerial defense zone


class DisruptionType(str, Enum):
    """Type of disruption to the trigger entity."""
    PHYSICAL = "PHYSICAL"
    POWER = "POWER"
    ACCESS = "ACCESS"
    COMMUNICATIONS = "COMMUNICATIONS"
    CYBER = "CYBER"
    UNKNOWN = "UNKNOWN"


# ── Impact Entity Properties ──────────────────────────────────────────────────

class ImpactEntityProperties(BaseModel):
    """Operational properties added to existing Concept nodes.
    These are SET directly on the Concept node in Neo4j (not a separate node).
    """
    entity_type: ImpactEntityType = Field(
        description="Impact-domain entity type (LOCATION, PROJECT, CLIENT, etc.)"
    )
    operational_status: OperationalStatus = Field(
        default=OperationalStatus.ACTIVE,
        description="Lifecycle state. PLANNED halts severity propagation in the engine.",
    )
    criticality_level: ImpactCriticality = Field(
        default=ImpactCriticality.MEDIUM,
        description="Inherent criticality of this entity to the organisation",
    )
    # Client-specific
    client_tier: Optional[ClientTier] = None
    sla_breach_hours: Optional[int] = Field(
        default=None,
        description="SLA breach threshold in hours (for CLIENT and OBLIGATION entities)"
    )
    has_active_clients: bool = False

    # Location-specific
    backup_location_ref: Optional[str] = Field(
        default=None, description="Name of backup Location concept"
    )
    can_operate_remotely: bool = False   # DEPARTMENT flag

    # Asset/System-specific
    has_backup: bool = False
    backup_asset_ref: Optional[str] = None
    has_failover: bool = False
    failover_time_hours: Optional[int] = None
    is_shared: bool = False   # system used by many entities — SPOF candidate

    # Personnel
    has_designated_backup: bool = False

    # Graph metrics (pre-computed, refreshed after every dependency graph change)
    downstream_count: int = Field(
        default=0,
        description="Total number of entities downstream in the dependency graph"
    )
    is_single_point_of_failure: bool = Field(
        default=False,
        description="True when this entity has no backup/failover and downstream_count > 0"
    )


# ── Dependency Edge Properties ────────────────────────────────────────────────

class DependencyEdgeProperties(BaseModel):
    """Properties on a typed dependency edge between two impact entities."""
    edge_type: DependencyEdgeType
    criticality: ImpactCriticality
    propagation_mode: PropagationMode = PropagationMode.DIRECT
    mitigation_available: bool = False
    recovery_time_hours: Optional[int] = None
    condition: Optional[str] = Field(
        default=None,
        description="If propagation_mode=CONDITIONAL, the condition that triggers impact"
    )
    notes: Optional[str] = None


# ── Propagation Result Models ─────────────────────────────────────────────────

class ImpactedEntity(BaseModel):
    """A single entity found during propagation traversal."""
    name: str
    entity_type: ImpactEntityType
    operational_status: OperationalStatus
    criticality: ImpactCriticality
    hop_distance: int = Field(description="Number of hops from the trigger entity")
    propagation_path: list[str] = Field(
        description="Ordered list of entity names from trigger to this entity"
    )
    # Edge metadata along the final hop
    edge_type: Optional[DependencyEdgeType] = None
    propagation_mode: PropagationMode = PropagationMode.DIRECT
    mitigation_available: bool = False
    recovery_time_hours: Optional[int] = None
    # Computed tier (based on criticality + operational status + mitigation)
    impact_tier: str = Field(
        description="CRITICAL | HIGH | MONITOR — assigned by propagation engine"
    )
    # Client-specific enrichment
    client_tier: Optional[ClientTier] = None
    sla_breach_hours: Optional[int] = None
    # Metadata
    is_single_point_of_failure: bool = False
    notes: Optional[str] = None


class MitigationOption(BaseModel):
    """A concrete mitigation option for an affected entity."""
    entity_name: str
    option_type: str = Field(
        description="'backup_location' | 'redundant_asset' | 'alternative_dept' | 'historical_precedent' | 'documented_fallback'"
    )
    description: str
    source: str = Field(description="Where this option came from (node name, document title, etc.)")
    estimated_recovery_hours: Optional[int] = None
    confidence: Confidence = 0.8


class PropagationResult(BaseModel):
    """Complete result of an impact propagation computation."""
    trigger_entity: str
    trigger_entity_type: ImpactEntityType
    disruption_type: DisruptionType = DisruptionType.UNKNOWN
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_simulation: bool = False   # True for impact_scenario_model calls

    # Tiered entity lists
    critical_entities: list[ImpactedEntity] = Field(default_factory=list)
    high_entities: list[ImpactedEntity] = Field(default_factory=list)
    monitor_entities: list[ImpactedEntity] = Field(default_factory=list)

    # Metadata
    total_affected: int = 0
    max_depth_reached: int = 0
    traversal_complete: bool = True   # False if max_depth cut off the traversal
    mitigations: list[MitigationOption] = Field(default_factory=list)
    historical_context: list[Any] = Field(default_factory=list)  # list[HistoricalIncident]

    # Quality
    coverage_confidence: Confidence = Field(
        default=0.8,
        description="How complete is the dependency data for this trigger entity"
    )
    low_coverage_entities: list[str] = Field(
        default_factory=list,
        description="Entity names with incomplete dependency data (lower confidence)"
    )


# ── Situation Report (Part 6 contract) ───────────────────────────────────────

class SituationReport(BaseModel):
    """Structured situation report — the Part 6 output format contract.
    The LLM is prompted to produce EXACTLY this shape.
    A vague summary without named entities is a quality failure (spec Part 10).
    """
    location_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    is_simulation: bool = False

    # Part 6 sections — each must name specific entities from the graph
    situation: str = Field(
        description=(
            "2-3 sentences: what happened, what is directly affected, overall severity. "
            "Must name specific entities — not vague summaries."
        )
    )
    critical_immediate: list[str] = Field(
        description=(
            "Numbered list. CRITICAL entities with no available mitigation only. "
            "Each item: entity name, why critical, specific action, time window."
        )
    )
    high_time_sensitive: list[str] = Field(
        description=(
            "Numbered list. HIGH entities. Include available mitigation if known."
        )
    )
    monitor_no_action: list[str] = Field(
        description=(
            "Brief list. Pre-operational entities, low-criticality impacts, well-mitigated items. "
            "MUST explain WHY each does not need immediate action. "
            "Example: 'Project B is pre-operational, Client G is not yet being served.'"
        )
    )
    historical_context: str = Field(
        description=(
            "Most relevant past incident and outcome (one paragraph), "
            "OR 'No closely matching historical incidents found in knowledge base.'"
        )
    )
    confidence: str = Field(
        description="HIGH | MEDIUM | LOW"
    )
    confidence_reason: str = Field(
        description=(
            "One sentence explaining the confidence rating. "
            "Example: 'MEDIUM: dependency data for 3 of 8 directly hosted entities is incomplete.'"
        )
    )

    # Entities named in the report — used for hallucination checking
    named_entities: list[str] = Field(
        default_factory=list,
        description="All entity names explicitly mentioned in this report (for validation)"
    )


# ── Historical Incident (not a Concept — standalone node) ────────────────────

class HistoricalIncident(BaseModel):
    """A past incident record — immutable after ingestion.
    Stored as HistoricalIncident nodes in Neo4j, NOT as Concept nodes.
    Agents cannot create, modify, or delete these — write path is ingestion only.
    """
    id: str = Field(default_factory=lambda: str(uuid4()))
    incident_date: Optional[str] = Field(
        default=None,
        description="ISO date string if found in source, else None"
    )
    title: str = Field(description="Short incident title")
    description: str
    # Entity references (matched to Concept node names in the graph)
    location_refs: list[str] = Field(
        default_factory=list,
        description="Names of location Concept nodes involved"
    )
    entity_refs: list[str] = Field(
        default_factory=list,
        description="Names of other Concept nodes involved"
    )
    # What happened
    disruption_type: Optional[DisruptionType] = None
    actions_taken: list[str] = Field(default_factory=list)
    outcome: str = ""
    recovery_time_hours: Optional[int] = None
    lessons_recorded: list[str] = Field(default_factory=list)
    # Provenance
    source_document: str = Field(description="Source document title")
    source_chunk_id: Optional[str] = None
    ingested_at: datetime = Field(default_factory=datetime.utcnow)
    confidence: Confidence = 0.8


class HistoricalIncidentExtractionOutput(BaseModel):
    """LLM extraction output for historical incident files.
    Used by HistoricalIncidentExtractor — fed to with_structured_output.
    """
    incidents: list[HistoricalIncident] = Field(
        description=(
            "All historical incidents found in this text chunk. "
            "Focus on: named incidents with dates, affected locations, "
            "actions taken, outcomes, recovery times, and lessons recorded. "
            "Empty list if no incidents are described."
        )
    )
    summary: str = Field(
        default="",
        description="One sentence describing what this chunk is about"
    )


# ── Excel Connector Models ────────────────────────────────────────────────────

class DetectedColumnRole(str, Enum):
    """Role a column plays in the Excel dependency schema."""
    LOCATION_ID = "LOCATION_ID"         # primary location identifier (site_name)
    FACILITY_ID = "FACILITY_ID"         # facility name within a site
    COMPONENT_ID = "COMPONENT_ID"       # component name within a facility
    LOCATION_DESC = "LOCATION_DESC"     # location description/notes
    DEPENDENCY = "DEPENDENCY"           # free-text dependency string
    STRUCTURED_REF = "STRUCTURED_REF"  # structured reference to another node (FK-like)
    FREE_TEXT = "FREE_TEXT"             # free-text field for LLM extraction
    CATEGORICAL = "CATEGORICAL"         # categorical/dropdown value
    META = "META"                       # region, tier, status metadata
    GEO = "GEO"                         # geographic/coordinate column
    UNKNOWN = "UNKNOWN"


class DetectedColumn(BaseModel):
    """A single column from the schema detection pass."""
    column_name: str
    detected_role: DetectedColumnRole
    sample_values: list[str] = Field(default_factory=list)
    confidence: Confidence = 0.8
    notes: Optional[str] = None


class DetectedSchema(BaseModel):
    """Output of ExcelConnector.detect_schema() — shown to operator for confirmation
    before any ingestion runs. The operator can override any column assignment.
    This is the key UX gate that prevents bad data from silently entering the graph.
    """
    columns: list[DetectedColumn]
    location_column: str = Field(description="Name of the column identified as location ID")
    dependency_columns: list[str] = Field(description="Columns that contain dependency strings")
    description_columns: list[str] = Field(description="Columns with free-text descriptions")
    meta_columns: list[str] = Field(description="Columns with metadata (region, tier, status, etc.)")
    total_rows: int
    sample_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="First 5 rows for operator preview"
    )
    detection_confidence: Confidence = 0.9
    warnings: list[str] = Field(
        default_factory=list,
        description="Detected issues: merged cells, multi-sheet, partial rows, etc."
    )


class ExtractedImpactEdge(BaseModel):
    """A single edge extracted from a free-text column in the facility Excel schema."""
    from_entity: str = Field(description="Source entity name")
    from_type: str = Field(description="Source node type: SITE | FACILITY | COMPONENT | SYSTEM")
    to_entity: str = Field(description="Target entity name")
    to_type: str = Field(description="Target node type: SITE | FACILITY | SYSTEM | RESPONSIBLE_BODY | POWER_STATION | etc.")
    edge_type: str = Field(
        description=(
            "Edge type: CONTAINS | PART_OF_SYSTEM | OPERATED_BY | POWERED_BY | FUELED_BY | "
            "PROTECTED_BY | AERIAL_DEFENSE_ZONE | RELATED_TO | BACKUP_FOR | AFFECTS | USES | SUPPORTS"
        )
    )
    weight: Optional[float] = Field(default=None, description="Numerical weight for this edge, usually between 0.0 and 1.0, or absolute integer weight")
    meaning: Optional[str] = Field(default=None, description="The meaning of the weight (e.g. urgency, importance, support effort)")
    criticality: str = Field(default="MEDIUM", description="CRITICAL | HIGH | MEDIUM | LOW")
    notes: Optional[str] = None
    source_column: str = Field(description="Name of the column this edge was extracted from")
    confidence: Confidence = Field(default=0.8)


class FacilityRowExtractionOutput(BaseModel):
    """LLM-extracted edges from free-text columns of a single facility Excel row.
    Produced by FacilityRowImpactExtractor.extract() using with_structured_output.
    Only the free-text columns are analyzed; structured columns produce edges directly.
    """
    facility_name: str = Field(description="Facility name from this row (for reference)")
    edges: list[ExtractedImpactEdge] = Field(
        description=(
            "All dependency edges extracted from the free-text columns. "
            "Each edge describes a relationship between entities mentioned in the text."
        )
    )
    nodes: list[ExtractedConcept] = Field(
        default_factory=list,
        description="Any new explicit entities discovered entirely within the free text that are not the existing site/facility/component."
    )
    normalized_categoricals: dict[str, Any] = Field(
        default_factory=dict,
        description="Normalized categorical values parsed from the row's raw values (e.g., standardizing text into clear boolean or enum categories)"
    )
    geo_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Processed and normalized geographic data extracted from polygon, central_point, or refined_coordinate columns"
    )
    entity_refs: list[str] = Field(
        default_factory=list,
        description="All entity names mentioned in free-text columns (for resolution)"
    )
    operational_significance: Optional[str] = Field(
        default=None,
        description="Brief summary of operational significance if damaged (for display)"
    )
    mitigation_procedures: Optional[str] = Field(
        default=None,
        description="Brief summary of SOP/mitigation if damaged"
    )
    review_needed: bool = Field(
        default=False,
        description="True if row is ambiguous, partial, or confidence is low"
    )
    review_reason: Optional[str] = None
    confidence: Confidence = 0.8


class ExcelDependencyExtraction(BaseModel):
    """LLM-extracted dependencies from a single Excel row.
    Produced by with_structured_output on the dependency column text.
    Kept for backward compatibility with original generic schema.
    """
    location_name: str = Field(description="Cleaned, canonical location name from this row")
    entities: list[dict[str, Any]] = Field(
        description=(
            "List of extracted entities. Each: "
            "{entity_name: str, entity_type: str, edge_type: str, "
            "edge_criticality: str, notes: str}"
        )
    )
    operational_status_hints: dict[str, str] = Field(
        default_factory=dict,
        description="entity_name -> operational status if inferable (ACTIVE/PLANNED/SUSPENDED)"
    )
    review_needed: bool = Field(
        default=False,
        description="True if row is ambiguous, partial, or confidence is low"
    )
    review_reason: Optional[str] = None
    confidence: Confidence = 0.8


class ExcelIngestionResult(BaseModel):
    """Result of a full Excel file ingestion run."""
    file_name: str
    total_rows: int
    committed_rows: int
    review_queue_rows: int
    new_entities: int
    updated_entities: int
    new_edges: int
    entity_resolution_matched: int
    entity_resolution_new: int
    entity_resolution_ambiguous: int
    errors: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0
    coverage_score_after: float = Field(
        default=0.0,
        description="Percentage of locations with fully-resolved dependency graphs after this run"
    )


# ── Impact Query Request/Response shapes (for API layer) ─────────────────────

class ImpactPropagateRequest(BaseModel):
    """Request body for POST /impact/propagate and POST /impact/scenario."""
    entity_name: str = Field(description="Name of the trigger entity (typically a Location)")
    disruption_type: DisruptionType = DisruptionType.UNKNOWN
    max_depth: int = Field(default=5, ge=1, le=10)
    include_mitigation: bool = True
    include_historical: bool = True
    hypothetical: bool = Field(
        default=False,
        description="If True, no state is written and output is labeled SIMULATION"
    )


class ImpactReverseRequest(BaseModel):
    """Request for POST /impact/reverse — 'what depends on this?'"""
    entity_name: str
    entity_type: Optional[ImpactEntityType] = None
    max_depth: int = Field(default=3, ge=1, le=10)


class ImpactCompareRequest(BaseModel):
    """Request for POST /impact/compare — blast radius comparison."""
    location_names: list[str] = Field(min_length=2, max_length=10)
    metric: str = Field(
        default="downstream_count",
        description="'downstream_count' | 'critical_project_count' | 'tier1_client_count'"
    )


class ImpactMitigationsRequest(BaseModel):
    """Request for POST /impact/mitigations."""
    entity_name: str
    scenario_context: Optional[str] = Field(
        default=None,
        description="Free text describing the current situation for context-aware mitigations"
    )


class ImpactHistoricalRequest(BaseModel):
    """Request for POST /impact/historical."""
    entity_names: list[str] = Field(default_factory=list)
    location_names: list[str] = Field(default_factory=list)
    since_date: Optional[str] = Field(
        default=None,
        description="ISO date string — only return incidents after this date"
    )
