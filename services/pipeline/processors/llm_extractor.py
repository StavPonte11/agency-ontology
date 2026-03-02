"""
LLM Extractor — Agency Ontology Pipeline
Extracts structured organizational knowledge from Hebrew military text using
LangChain with_structured_output + Pydantic v2. Instructor as fallback.

Domain: Hebrew military-operational terminology
Primary language: Hebrew (עברית)
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from ..models.ontology import (
    LLMExtractionOutput,
    HierarchicalExtractionOutput,
    DocumentType,
    TermType,
    Language,
)

logger = logging.getLogger(__name__)

# ── Hierarchical extraction model selection ────────────────────────────────────

# Document types that always use the hierarchical extraction model
HIERARCHICAL_DOCUMENT_TYPES = {DocumentType.PDF_DICTIONARY, DocumentType.CATALOG}

# Keyword signals in chunk content indicating classifiable, typed entities
HIERARCHICAL_CONTENT_SIGNALS: list[str] = [
    # English signals
    "instance of", "subclass of", "type of", "is a", "category",
    "class of", "kind of", "brigade", "division", "department",
    "system type", "policy type", "role type", "inception", "founded",
    # Hebrew signals
    "חטיבה", "סוג", "מחלקה", "פיקוד", "יחידה", "נוסד",
]


def select_extraction_model(
    chunk_content: str,
    document_type: str | DocumentType | None,
) -> type:
    """
    Choose flat (LLMExtractionOutput) or hierarchical (HierarchicalExtractionOutput)
    extraction model based on document type and content signals.

    Strategy:
    - Always use HierarchicalExtractionOutput for PDF_DICTIONARY and CATALOG documents.
    - Use it for other documents when chunk content contains >= 2 hierarchy signals.
    - Hierarchical model is a strict superset — using it on flat content is safe;
      hierarchy/statements fields will simply be empty lists.
    """
    # Normalise document_type
    if isinstance(document_type, str):
        try:
            document_type = DocumentType(document_type)
        except ValueError:
            document_type = None

    if document_type in HIERARCHICAL_DOCUMENT_TYPES:
        logger.debug(f"Hierarchical model selected: document_type={document_type}")
        return HierarchicalExtractionOutput

    content_lower = chunk_content.lower()
    signal_count = sum(1 for s in HIERARCHICAL_CONTENT_SIGNALS if s in content_lower)
    if signal_count >= 2:
        logger.debug(f"Hierarchical model selected: {signal_count} content signals detected")
        return HierarchicalExtractionOutput

    return LLMExtractionOutput


# ── System prompt — Hebrew military domain ─────────────────────────────────────
# Written with explicit Hebrew domain awareness: nikud, acronyms (ר"מ, מפ"ג),
# codenames, unit names, operational terminology, and classified sensitivity levels.

EXTRACTION_SYSTEM_PROMPT = """\
אתה מומחה לחילוץ ידע ארגוני ממסמכים מבצעיים צבאיים.
תפקידך לחלץ ידע מובנה ממסמכים פנימיים של הארגון לבניית גרף ידע ארגוני.

You are an expert at extracting structured organizational knowledge from Hebrew military operational documents.
Your task is to extract structured knowledge to build a corporate knowledge graph.

DOMAIN CONTEXT — Israeli Military Operational Terminology:
- Documents are in Hebrew (primary) and may contain English technical terms
- Terminology includes: unit names, system codenames, operational processes, roles, metrics, and policies
- Hebrew military abbreviations use the format: ר"מ, מפ"ג, קמ"ן, אג"ם (letters separated by geresh ״)
- Sensitivity is CRITICAL — classify all military codenames and classified systems as CONFIDENTIAL or SECRET
- Many terms have both a Hebrew canonical name and an English alias

EXTRACTION RULES — follow strictly:
1. Hebrew is the PRIMARY language. Extract Hebrew names as canonical names when present.
2. Extract ONLY what is explicitly stated or strongly implied. Do NOT invent or infer beyond the text.
3. If a concept appears in both Hebrew and English, use the Hebrew as canonical name, English as ALIAS term.
4. Military abbreviations (ר"מ, מפ"ג, etc.): extract the abbreviation as ABBREVIATION term type, include expanded form separately.
5. Codenames (שם קוד, מבצע X, מערכת X): set term_type=CODENAME and concept_type=CODENAME or SYSTEM.
6. Sensitivity: default to CONFIDENTIAL for military systems, processes, and codenames. Use SECRET only when document explicitly marks content as classified.
7. If uncertain about a concept's definition: set confidence < 0.6 and note it in extraction_notes.
8. Every concept MUST have at least one term matching its canonical name.
9. Relationships: use the most specific relation_type. Use RELATED_TO only as last resort.
10. Data mappings: only extract if source explicitly states "concept X lives in table/system Y".
11. Return empty lists if nothing was found — NEVER omit required fields.
12. source_quote is REQUIRED for every concept and relationship — copy exact text.
13. For Hebrew concepts: set language="he". For English: "en". Mixed: "mixed".
"""

HIERARCHICAL_SYSTEM_PROMPT_ADDITION = """\

HIERARCHICAL EXTRACTION RULES — additional rules when using HierarchicalExtractionOutput:
14. HIERARCHY — extract the taxonomic position of EVERY concept:
    - INSTANCE_OF: use when this concept is a SPECIFIC named entity/instance of a class.
      Example: 'Judea Territorial Brigade' INSTANCE_OF 'Territorial Brigade'
      Example: 'System X v2.1' INSTANCE_OF 'System X'
    - SUBCLASS_OF: use when this concept is a CATEGORY specialising a broader category.
      Example: 'Territorial Brigade' SUBCLASS_OF 'Brigade'
      Example: 'Brigade' SUBCLASS_OF 'Military Unit'
    - PART_OF_HIERARCHY: use for structural/organisational containment.
      Example: 'Alpha Squadron' PART_OF_HIERARCHY 'Delta Battalion'
    - NEVER use INSTANCE_OF and SUBCLASS_OF for the same concept/target pair.
    - NEVER point INSTANCE_OF at a specific named entity (that would be PART_OF_HIERARCHY).
    - If you cannot place a concept in the hierarchy: leave hierarchy=[] (do NOT guess).
15. is_class=True ONLY for generic types/categories (Brigade, System Type, Role, Policy Type).
    Specific named entities are NEVER classes.
16. MULTILINGUAL LABELS — for EVERY concept:
    - Include a label for each language found in the source
    - If source has both Hebrew and English: add both language entries
    - Put ALL aliases (official abbreviations, nicknames, codenames) in the aliases list
      for their respective language entry
17. STATEMENTS — extract explicit factual properties:
    - inception / founded → value_type='date'
    - parent_unit / parent_org → value_type='concept_ref', concept_ref_id = parent concept name
    - location, commander, capacity, status, classification → value_type='string'
    - Leave statements=[] if no properties are explicitly stated
18. CIRCULAR HIERARCHY CHECK: do NOT create a hierarchy where a concept is its own
    ancestor. If you detect a potential cycle, omit the problematic hierarchy entry.
"""


EXTRACTION_HUMAN_PROMPT = """\
חלץ את כל מושגי הארגון, הקשרים ומיפויי הנתונים מהטקסט הבא.
Extract all organizational concepts, relationships, and data mappings from the following text chunk.

Document: {document_title}
Section: {section_title}
Page(s): {page_range}
Primary Language: {primary_language}

TEXT:
{chunk_content}

Extract now. Return valid JSON matching the schema exactly. Use Hebrew for Hebrew concepts, English for English ones.
"""

CORRECTION_PROMPT = """\
Your previous response had validation errors: {errors}

Please correct and return valid JSON matching the required schema exactly.
Remember:
- confidence must be between 0.0 and 1.0
- All required fields must be present (never omit concepts, relationships, or data_mappings — use empty lists)
- For Hebrew terms: language="he", for English: language="en"
- term_type for Hebrew abbreviations (ר"מ etc.): ABBREVIATION
- concept_type: TERM | SYSTEM | PROCESS | METRIC | ENTITY | CODENAME | ROLE | DATASET | POLICY

Original chunk (for reference):
{chunk_content}
"""


class LLMExtractor:
    """
    Extracts structured ontology entities from text chunks.

    Primary: LangChain ChatOpenAI with with_structured_output
    Supports both:
      - OpenAI (api_key required, base_url=None)
      - Ollama (base_url="http://localhost:11434/v1", api_key="ollama")

    Ollama uses json_mode (not json_schema) since open-weight models
    don't support the full OpenAI function-calling schema protocol.

    Hebrew military domain:
    - Expects Hebrew primary language in chunks
    - Prompts are bilingual (Hebrew + English instructions)
    - Abbreviation detection and expansion built into prompts
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        langfuse_client: Any,           # langfuse.Langfuse
        max_retries: int = 1,
        temperature: float = 0.0,
        base_url: Optional[str] = None,  # Set to Ollama URL to use local model
    ) -> None:
        self._model_name = model
        self._langfuse = langfuse_client
        self._max_retries = max_retries
        self._api_key = api_key

        # Detect backend: Ollama (base_url set) vs OpenAI
        using_ollama = bool(base_url)
        if using_ollama:
            logger.info(f"LLMExtractor: using Ollama at {base_url} with model={model}")
        else:
            logger.info(f"LLMExtractor: using OpenAI with model={model}")

        # Build the ChatOpenAI client — works for both OpenAI and Ollama
        # (Ollama serves an OpenAI-compatible REST API at /v1)
        llm_kwargs: dict = dict(
            model=model,
            temperature=temperature,
        )
        if base_url:
            # Ollama: dummy key required by LangChain but ignored server-side
            llm_kwargs["base_url"] = base_url
            llm_kwargs["api_key"] = api_key or "ollama"
        else:
            llm_kwargs["api_key"] = api_key

        self._llm = ChatOpenAI(**llm_kwargs)

        # Ollama open-weight models don't support json_schema tool-calling,
        # use json_mode (prompt-based) instead.
        output_method = "json_mode" if using_ollama else "json_schema"
        logger.debug(f"Structured output method: {output_method}")

        # Flat chain — used for general documents
        self._structured_llm = self._llm.with_structured_output(
            LLMExtractionOutput,
            method=output_method,
        )
        # Hierarchical chain — used for PDF_DICTIONARY, CATALOG, or signal-heavy content
        self._hierarchical_llm = self._llm.with_structured_output(
            HierarchicalExtractionOutput,
            method=output_method,
        )
        
        system_prompt = EXTRACTION_SYSTEM_PROMPT
        hier_system_prompt = EXTRACTION_SYSTEM_PROMPT + HIERARCHICAL_SYSTEM_PROMPT_ADDITION
        
        if using_ollama:
            # In json_mode, the LLM needs to see the schema to follow it
            schema_flat = json.dumps(LLMExtractionOutput.model_json_schema(), separators=(',', ':'))
            schema_hier = json.dumps(HierarchicalExtractionOutput.model_json_schema(), separators=(',', ':'))
            
            # Escape curly braces so LangChain's PromptTemplate doesn't treat them as variables
            schema_flat = schema_flat.replace("{", "{{").replace("}", "}}")
            schema_hier = schema_hier.replace("{", "{{").replace("}", "}}")
            
            instruction = "\n\nYou MUST return a JSON object that strictly matches this JSON Schema:\n```json\n{schema}\n```"
            system_prompt += instruction.format(schema=schema_flat)
            hier_system_prompt += instruction.format(schema=schema_hier)

        self._prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", EXTRACTION_HUMAN_PROMPT),
        ])
        self._hierarchical_prompt = ChatPromptTemplate.from_messages([
            ("system", hier_system_prompt),
            ("human", EXTRACTION_HUMAN_PROMPT),
        ])
        self._chain = self._prompt | self._structured_llm
        self._hierarchical_chain = self._hierarchical_prompt | self._hierarchical_llm


    async def extract(
        self,
        chunk_content: str,
        document_title: str,
        section_title: str,
        page_range: str,
        job_id: str,
        trace_id: str,
        primary_language: str = "he",
        document_type: str | DocumentType | None = None,
    ) -> LLMExtractionOutput | HierarchicalExtractionOutput:
        """
        Extract ontology entities from a text chunk.

        Automatically selects between flat LLMExtractionOutput and
        HierarchicalExtractionOutput based on document_type and content signals.

        Returns validated extraction output. On repeated failure returns an empty
        extraction and signals review queue.
        """
        chosen_model = select_extraction_model(chunk_content, document_type)
        use_hierarchical = chosen_model is HierarchicalExtractionOutput
        chain = self._hierarchical_chain if use_hierarchical else self._chain

        logger.info(
            f"Starting extraction for chunk {trace_id} (doc={document_title}, "
            f"model={'hierarchical' if use_hierarchical else 'flat'})"
        )
        # Build LangFuse callback handler if available
        callbacks = []
        try:
            from langfuse.callback import CallbackHandler
            callbacks = [CallbackHandler(
                trace_id=trace_id,
                metadata={"job_id": job_id, "stage": "llm_extract"},
            )]
        except Exception:
            pass

        last_exc: Optional[Exception] = None

        for attempt in range(self._max_retries + 1):
            try:
                result = await chain.ainvoke(
                    {
                        "document_title": document_title,
                        "section_title": section_title or "לא ידוע / Unknown",
                        "page_range": page_range or "N/A",
                        "primary_language": primary_language,
                        "chunk_content": chunk_content,
                    },
                    config={"callbacks": callbacks} if callbacks else {},
                )

                # Chain returns the parsed model directly (no include_raw)
                if isinstance(result, (LLMExtractionOutput, HierarchicalExtractionOutput)):
                    logger.info(
                        f"Extracted {len(result.concepts)} concepts, "
                        f"{len(result.relationships)} relationships for trace={trace_id}"
                    )
                    return result

                else:
                    raise ValueError(f"Unexpected result type from chain: {type(result)}")

            except (ValidationError, ValueError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    logger.warning(
                        f"Extraction validation failed for {trace_id} (attempt {attempt + 1}/{self._max_retries + 1}): {exc}",
                        extra={"job_id": job_id},
                    )
                    # Append correction hint to next attempt
                    chunk_content = (
                        chunk_content
                        + f"\n\n[CORRECTION NEEDED: {str(exc)[:300]}]"
                    )
                else:
                    logger.error(
                        f"Primary extractor failed after {self._max_retries + 1} attempts",
                        extra={"job_id": job_id},
                    )

        # Try instructor fallback before giving up
        logger.info(f"Primary extractor failed for {trace_id}. Attempting instructor fallback.")
        return await self._extract_with_instructor(
            chunk_content, document_title, section_title, page_range, trace_id
        )

    async def _extract_with_instructor(
        self,
        chunk_content: str,
        document_title: str,
        section_title: str,
        page_range: str,
        trace_id: str,
    ) -> LLMExtractionOutput:
        """Instructor fallback — wraps OpenAI-compatible client with auto retry+validation."""
        try:
            import instructor
            from openai import OpenAI as _OpenAI

            client = instructor.from_openai(
                _OpenAI(api_key=self._api_key),
                mode=instructor.Mode.JSON,
            )
            result: LLMExtractionOutput = client.chat.completions.create(
                model=self._model_name,
                response_model=LLMExtractionOutput,
                max_retries=2,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": EXTRACTION_HUMAN_PROMPT.format(
                            document_title=document_title,
                            section_title=section_title or "לא ידוע",
                            page_range=page_range or "N/A",
                            primary_language="he",
                            chunk_content=chunk_content,
                        ),
                    },
                ],
            )
            logger.info(f"Instructor fallback succeeded for trace={trace_id}")
            return result

        except Exception as exc:
            logger.error(f"Instructor fallback also failed for trace={trace_id}: {exc}")
            # Return empty extraction — caller will route to review queue
            return LLMExtractionOutput(
                concepts=[],
                relationships=[],
                data_mappings=[],
                chunk_summary="Extraction failed — routed to review queue",
                extraction_notes=(
                    f"Both primary extractor (LangChain) and fallback (instructor) failed. "
                    f"Error: {str(exc)[:500]}"
                ),
            )
