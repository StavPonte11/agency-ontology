"""
LLM Extractor — Agency Ontology Pipeline
Extracts structured organizational knowledge from Hebrew military text using
LangChain with_structured_output + Pydantic v2. Instructor as fallback.

Domain: Hebrew military-operational terminology
Primary language: Hebrew (עברית)
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import ValidationError

from ..models.ontology import LLMExtractionOutput, TermType, Language

logger = logging.getLogger(__name__)

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

    Primary: LangChain ChatOpenAI with with_structured_output(method="json_schema")
    Fallback: instructor library with OpenAI-compatible client

    Hebrew military domain:
    - Expects Hebrew primary language in chunks
    - Prompts are bilingual (Hebrew + English instructions)
    - Abbreviation detection and expansion built into prompts
    """

    def __init__(
        self,
        openai_base_url: str,
        model: str,
        langfuse_client: Any,           # langfuse.Langfuse
        max_retries: int = 1,
        temperature: float = 0.0,
    ) -> None:
        self._model_name = model
        self._langfuse = langfuse_client
        self._max_retries = max_retries

        # Primary: LangChain + ChatOpenAI with JSON schema structured output
        self._llm = ChatOpenAI(
            base_url=openai_base_url,
            model=model,
            temperature=temperature,
            model_kwargs={"num_ctx": 8192},
        )
        self._structured_llm = self._llm.with_structured_output(
            LLMExtractionOutput,
            method="json_schema",   # OpenAI JSON schema constrained generation
            include_raw=True,       # Capture raw response for LangFuse token counting
        )
        self._prompt = ChatPromptTemplate.from_messages([
            ("system", EXTRACTION_SYSTEM_PROMPT),
            ("human", EXTRACTION_HUMAN_PROMPT),
        ])
        self._chain = self._prompt | self._structured_llm

        # Fallback: instructor
        self._openai_base_url = openai_base_url

    async def extract(
        self,
        chunk_content: str,
        document_title: str,
        section_title: str,
        page_range: str,
        job_id: str,
        trace_id: str,
        primary_language: str = "he",
    ) -> LLMExtractionOutput:
        """
        Extract ontology entities from a text chunk.
        Returns validated LLMExtractionOutput.
        On repeated failure: returns empty extraction and signals review queue.
        """
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
                result = await self._chain.ainvoke(
                    {
                        "document_title": document_title,
                        "section_title": section_title or "לא ידוע / Unknown",
                        "page_range": page_range or "N/A",
                        "primary_language": primary_language,
                        "chunk_content": chunk_content,
                    },
                    config={"callbacks": callbacks} if callbacks else {},
                )

                # include_raw=True → {"raw": AIMessage, "parsed": Model, "parsing_error": ...}
                if isinstance(result, dict):
                    parsing_error = result.get("parsing_error")
                    parsed = result.get("parsed")

                    if parsing_error:
                        raise ValueError(f"Parsing error: {parsing_error}")
                    if parsed is None:
                        raise ValueError("Structured output returned None")

                    # Log token usage to LangFuse
                    raw_msg = result.get("raw")
                    if raw_msg and hasattr(raw_msg, "usage_metadata") and self._langfuse:
                        self._langfuse.score(
                            trace_id=trace_id,
                            name="extraction_tokens",
                            value=raw_msg.usage_metadata.get("total_tokens", 0),
                        )

                    return parsed

                elif isinstance(result, LLMExtractionOutput):
                    return result

                else:
                    raise ValueError(f"Unexpected result type: {type(result)}")

            except (ValidationError, ValueError) as exc:
                last_exc = exc
                if attempt < self._max_retries:
                    logger.warning(
                        f"Extraction validation failed (attempt {attempt + 1}/{self._max_retries + 1}), retrying",
                        extra={"job_id": job_id, "error": str(exc)[:200]},
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
        logger.info(f"Attempting instructor fallback for trace={trace_id}")
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
                _OpenAI(base_url=f"{self._openai_base_url}/v1", api_key="openai"),
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
