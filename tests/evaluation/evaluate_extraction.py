import os
import asyncio
from langfuse import Langfuse
from langfuse.decorators import observe, langfuse_context
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

# Initialize Langfuse
langfuse = Langfuse()

# Model for structured LLM Judge output
class EvaluationResult(BaseModel):
    justification: str = Field(description="Detailed explanation of the score based on the rubric, finding specific evidence in the response before assigning a score.")
    factual_accuracy: int = Field(description="Score from 1 to 5 measuring factual accuracy based on the provided context.", ge=1, le=5)
    hebrew_language_compliance: int = Field(description="Score from 1 to 5 measuring whether the concepts are properly extracted primarily in Hebrew with correct acronym expansion if applicable.", ge=1, le=5)
    improvement: str = Field(description="One specific actionable improvement for the extraction logic.")

# The evaluation prompt, strictly implementing the Advanced Evaluation skill guidelines
eval_prompt = ChatPromptTemplate.from_messages([
    ("system", """You are an expert military intelligence evaluator assessing knowledge graph extraction quality.

## Task
Evaluate the extracted concepts against the original source text according to the following criteria.

## Criteria
1. Factual Accuracy (Weight: 0.6)
   - Description: Measures if the extracted concepts and definitions are factually accurate and directly supported by the source text without hallucination.
   - Scale 1-5: 1=Poor (hallucinations, contradictions), 3=Adequate (mostly correct, minor omissions), 5=Excellent (perfectly reflects text, precise definitions).

2. Hebrew Language Compliance (Weight: 0.4)
   - Description: Measures if concepts are strictly extracted in Hebrew (unless explicitly an English system name), acronyms are correctly identified, and language is formal military Hebrew.
   - Scale 1-5: 1=Poor (wrong language, failed acronyms), 3=Adequate (mostly Hebrew, some mixed formatting), 5=Excellent (perfect formal Hebrew, impeccable acronym handling).

## Instructions
For each criterion:
1. Find specific evidence in the response comparing to the original text.
2. Formulate your justification *before* assigning the score.
3. Score according to the rubric (1-5 scale).
4. Suggest one specific improvement for the extraction pipeline.

## Output Format
Respond with the structured JSON containing justification, the two numerical scores, and the suggested improvement.
"""),
    ("user", """
## Original Source Text
{source_text}

## Extracted Ontology Concepts (To Evaluate)
{extracted_concepts}
""")
])

# Use GPT-4 or Opus as the judge
judge_llm = ChatOpenAI(model="gpt-4-turbo-preview", temperature=0).with_structured_output(EvaluationResult)
eval_chain = eval_prompt | judge_llm

@observe()
async def evaluate_extraction(source_text: str, extracted_concepts: str, extraction_trace_id: str):
    """
    Evaluates an LLM extraction against the source text using an LLM-as-a-judge.
    Logs the scores back to Langfuse attached to the original extraction trace.
    """
    print(f"Running LLM Judge evaluation for trace {extraction_trace_id}...")
    
    # Run the evaluation chain
    result: EvaluationResult = await eval_chain.ainvoke({
        "source_text": source_text,
        "extracted_concepts": extracted_concepts
    })
    
    print(f"Evaluation Complete. Accuracy: {result.factual_accuracy}/5, Hebrew Compliance: {result.hebrew_language_compliance}/5")
    print(f"Reasoning: {result.justification}")
    
    # Log the scores back to the original trace in Langfuse
    # We use the internal langfuse client to attach a score to a specific trace/observation
    langfuse.score(
        trace_id=extraction_trace_id,
        name="factual_accuracy",
        value=result.factual_accuracy,
        comment=result.justification
    )
    
    langfuse.score(
        trace_id=extraction_trace_id,
        name="hebrew_compliance",
        value=result.hebrew_language_compliance,
        comment=result.improvement
    )
    
    return result

async def main():
    # Example manual trigger for testing the evaluator
    sample_text = "רמטכ\"ל צה\"ל, רב-אלוף הרצי הלוי, סייר בבסיס חיל רגלים והנחה על העלאת הכוננות."
    sample_extraction = '[{"nameHe": "רמטכ\"ל", "type": "ROLE", "description": "ראש המטה הכללי של צהל, רב אלוף הרצי הלוי."}, {"nameHe": "חיל רגלים", "type": "UNIT", "description": "בסיס צבאי."}]'
    
    # In a real scenario, extraction_trace_id comes from the pipeline
    dummy_trace_id = "test-eval-trace-001" 
    
    # Create a dummy trace just for this test script so the score has something to attach to
    langfuse.trace(id=dummy_trace_id, name="test-pipeline-extraction")
    
    await evaluate_extraction(sample_text, sample_extraction, dummy_trace_id)
    langfuse.flush()

if __name__ == "__main__":
    # Ensure env vars are set or default to local for testing
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    os.environ.setdefault("LANGFUSE_SECRET_KEY", "sk-lf-test")
    os.environ.setdefault("LANGFUSE_HOST", "http://localhost:3000")
    # For testing, we mock the OpenAI API key if not present so it doesn't crash on import
    if "OPENAI_API_KEY" not in os.environ:
         os.environ["OPENAI_API_KEY"] = "sk-placeholder"
         
    # asyncio.run(main()) # Uncomment to run this script standalone
