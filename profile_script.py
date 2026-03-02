import asyncio
import cProfile
import pstats
import io
import os
from services.pipeline.orchestrator import PipelineOrchestrator

async def main():
    orch = PipelineOrchestrator(
        neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
        neo4j_password=os.environ.get("NEO4J_PASSWORD", "changeme"),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        model=os.environ.get("PIPELINE_MODEL", "qwen2.5:3b"),
        max_concurrent_chunks=2,
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
    )
    
    # We will just process a single small valid PDF or just trace the process.
    pdf_path = os.environ.get("PDF_PATH", r"C:\Users\User\OneDrive\שולחן העבודה\Stav\Agents\agency-ontology\docs\בחינה במודלים חישוביים 2024 קיץ  מועד ב.pdf")
    
    if not os.path.exists(pdf_path):
        print("PDF not found!")
        return
        
    print(f"Profiling pipeline on {pdf_path}")
    result = await orch.run_pdf(
        pdf_path=pdf_path,
        document_title="Profile Test",
        connector_id="profile",
        job_id="profile"
    )
    print(result)
    await orch.close()

def run_profiler():
    pr = cProfile.Profile()
    pr.enable()
    asyncio.run(main())
    pr.disable()
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats('cumtime')
    ps.print_stats(30)
    print(s.getvalue())

if __name__ == "__main__":
    run_profiler()
