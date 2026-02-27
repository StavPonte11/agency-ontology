import asyncio
from services.pipeline.processors.pdf_processor import PDFProcessor
from services.pipeline.processors.llm_extractor import LLMExtractor
from tests.evaluation.evaluate_extraction import evaluate_extraction

async def run_pipeline_on_pdf(pdf_path: str):
    print(f"Starting pipeline on: {pdf_path}")
    
    # 1. Extact Text
    print("1. Extracting text via PDFProcessor...")
    pdf_processor = PDFProcessor()
    # Read the first few pages for the test to avoid burning tokens
    documents = [] # This would normally be emitted to Kafka
    with open(pdf_path, 'rb') as f:
        # Mocking the process method which usually writes to Kafka
        raw_text = ""
        import pdfplumber
        with pdfplumber.open(f) as pdf:
            # Just take pages 14-16 (random pages with acronyms)
            for i in range(13, min(16, len(pdf.pages))):
                page_text = pdf.pages[i].extract_text()
                if page_text:
                    normalized = pdf_processor.normalize_hebrew_text(page_text)
                    raw_text += normalized + "\n"
    
    print(f"Extracted {len(raw_text)} chars of normalized text.")
    
    # 2. LLM Extraction
    print("2. Running LLM Extractor...")
    extractor = LLMExtractor()
    
    # Process the text
    extraction_output = await extractor.extract_from_text(raw_text)
    
    print(f"Extracted {len(extraction_output.concepts)} concepts.")
    for concept in extraction_output.concepts:
         print(f" - {concept.nameHe} ({concept.type}): {concept.descriptionHe}")
    
    # 3. LangFuse Evaluation
    print("\n3. Running LangFuse LLM-as-a-judge Evaluation...")
    # we pass the pydantic model as json string
    concepts_json = extraction_output.model_dump_json(indent=2, exclude_unset=True)
    
    eval_result = await evaluate_extraction(
        source_text=raw_text,
        extracted_concepts=concepts_json,
        extraction_trace_id="test-run-pdf-001"
    )
    
    print("\n========= PIPELINE TEST COMPLETE =========")

if __name__ == "__main__":
    pdf_path = r"c:\Users\User\OneDrive\שולחן העבודה\Stav\Agents\agency-ontology\docs\idf-alias-and-names.pdf"
    asyncio.run(run_pipeline_on_pdf(pdf_path))
