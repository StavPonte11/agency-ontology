/**
 * MCP Tools Definitions — Agency Ontology
 * Registration payload for the Model Context Protocol (MCP) server.
 * Integrates directly with the FastAPI retrieval services.
 */
import { z } from "zod"
import {
    LookupInputSchema,
    SearchInputSchema,
    EnrichInputSchema,
    SchemaContextInputSchema,
    FeedbackInputSchema,
} from "../../shared-types/ontology"

// We use the zod-to-json-schema utility (standard in MCP implementations)
import { zodToJsonSchema } from "zod-to-json-schema"

export const ONTOLOGY_TOOLS = [
    {
        name: "ontology_lookup",
        description: `Lookup an organizational concept, military term, codename, acronym, or system name.
Use this when you encounter a specific term in the user's prompt that you don't fully understand, or when you need to know exactly which data assets (tables, views) correspond to a business concept.
Supports Hebrew abbreviations (e.g. ר"מ, קמ"ן) and military codenames.
Always use this before writing SQL or drawing conclusions about internal systems.`,
        inputSchema: zodToJsonSchema(LookupInputSchema, "LookupInput"),
    },
    {
        name: "ontology_search",
        description: `Search the organizational knowledge graph.
Use this when you are looking for concepts within a specific domain, or when lookup fails and you want to do a fuzzy semantic search (hybrid BM25 + kNN).
You can filter by concept_types (e.g., SYSTEM, ROLE, METRIC), domains, and status.
Returns ranked results with match scores.`,
        inputSchema: zodToJsonSchema(SearchInputSchema, "SearchInput"),
    },
    {
        name: "ontology_enrich",
        description: `Enrich a block of text with relevant context.
Pass the user's prompt or a section of text here. The tool will automatically extract recognized Hebrew and English military/organizational concepts and return a structured context block containing their definitions and aliases.
Use this at the beginning of complex reasoning tasks to ground yourself in the organization's terminology.`,
        inputSchema: zodToJsonSchema(EnrichInputSchema, "EnrichInput"),
    },
    {
        name: "ontology_schema_context",
        description: `Get exact database schema for business concepts.
CRITICAL for TextToSQL tasks. Pass the business concepts (e.g., ["budget", "active personnel", "unit readiness"]) and this tool will return the specific database tables and columns that store those concepts.
Do NOT guess table names — always use this tool first.`,
        inputSchema: zodToJsonSchema(SchemaContextInputSchema, "SchemaContextInput"),
    },
    {
        name: "ontology_feedback",
        description: `Submit feedback on the ontology.
If you find that a definition is wrong, a term is missing, or a data mapping is incorrect, use this tool to report it.
This flags the concept for human review and improves the system.`,
        inputSchema: zodToJsonSchema(FeedbackInputSchema, "FeedbackInput"),
    },
]
