import asyncio
import os
import json
from rich.console import Console
from rich.progress import Progress

from services.pipeline.connectors.excel_connector import ExcelConnector
from services.pipeline.connectors.base import ConnectorType

console = Console()

async def run_e2e_excel_ingest():
    console.print("[bold blue]Starting E2E Impact Ingestion Test[/bold blue]")
    
    excel_path = "c:/Users/User/AppData/Local/Temp/large_e2e_test_data.xlsx"
    if not os.path.exists(excel_path):
        console.print(f"[bold red]File not found:[/bold red] {excel_path}")
        return

    connector = ExcelConnector(connector_id="e2e-test-connector", file_path=excel_path)
    
    # 1. Detect Schema
    console.print("\n[bold yellow]Step 1: Detecting Schema...[/bold yellow]")
    schema = await connector.detect_schema()
    console.print(f"Detected Location Column: [green]{schema.location_column}[/green]")
    console.print(f"Detected Dependency Columns: [green]{schema.dependency_columns}[/green]")
    console.print(f"Total Rows Detected: [cyan]{schema.total_rows}[/cyan]")
    
    from services.pipeline.connectors.excel_connector import ExcelDependencyExtractor
    from langchain_openai import ChatOpenAI
    
    # Needs a real LLM instance - point to local Ollama instance per spec
    llm = ChatOpenAI(
        model="llama3.1:8b", 
        temperature=0, 
        base_url="http://localhost:11434/v1", 
        api_key="ollama"  # Required by openai client, but ignored by ollama
    )
    extractor = ExcelDependencyExtractor(llm)
    
    # 2. Extract Dependencies (This calls LLM via structured output)
    console.print("\n[bold yellow]Step 2: Extracting Dependencies (Processing 102 rows via LLM)...[/bold yellow]")
    console.print("[dim]This may take a few minutes as it makes actual LLM calls against the local provider.[/dim]")
    
    committed_rows = 0
    review_queue = 0
    new_edges = 0
    
    with Progress() as progress:
        task = progress.add_task("[cyan]Processing rows...", total=schema.total_rows)
        
        async for doc in connector.list_documents(schema_overrides=schema):
            # If the row was totally broken, connector flags it immediately
            if doc.metadata.get("review_needed"):
                review_queue += 1
                progress.update(task, advance=1)
                continue
                
            dep_text = doc.raw_content
            loc_name = doc.metadata.get("fields", {}).get("LOCATION_ID", "Unknown")
            desc = doc.metadata.get("fields", {}).get("LOCATION_DESC", "")
            
            # The LLM Extraction call
            extraction_result = await extractor.extract(location_name=loc_name, dep_text=dep_text, description=desc)
            
            if extraction_result:
                committed_rows += 1
                new_edges += len(extraction_result.entities)
            else:
                review_queue += 1

            progress.update(task, advance=1)
            
    console.print("\n[bold green]E2E Extration Complete![/bold green]")
    console.print(f"Rows Committed: [green]{committed_rows}[/green]")
    console.print(f"Sent to Review Queue: [yellow]{review_queue}[/yellow]")
    console.print(f"Total New Dependency Edges Extracted: [cyan]{new_edges}[/cyan]")
    
    assert committed_rows > 50, "Expected majority of generated rows to pass LLM extraction cleanly."
    assert review_queue >= 2, "Expected at least 2 intentionally broken rows to hit the review queue."
    
    console.print("\n[bold green]All Assertions Passed! E2E workflow end-to-end verified.[/bold green]")

if __name__ == "__main__":
    asyncio.run(run_e2e_excel_ingest())
