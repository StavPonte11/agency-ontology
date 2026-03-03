from __future__ import annotations

import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from config import settings
from services.pipeline.orchestrator import PipelineOrchestrator

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/ingest/excel")
async def ingest_excel(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """
    Upload an Excel spreadsheet containing facility/site dependency data 
    and kick off an asynchronous ingestion job using the PipelineOrchestrator.
    """
    if not file.filename or not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only .xlsx or .xls files are supported")
        
    job_id = str(uuid.uuid4())
    temp_dir = Path(f"/tmp/agency_ontology_ingest_{job_id}")
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    # Safe filename fallback
    safe_filename = file.filename or "uploaded.xlsx"
    temp_path = temp_dir / safe_filename
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as exc:
        raise HTTPException(500, f"Failed to save uploaded file: {exc}")
        
    async def process_file(path: Path, filename: str, directory: Path) -> None:
        logger.info(f"Starting background Excel ingestion for {filename} (job {job_id})")
        
        # Instantiate orchestrator. We use the settings module from the API
        try:
            orch = PipelineOrchestrator(
                neo4j_uri=settings.neo4j_uri,
                neo4j_user=settings.neo4j_user,
                neo4j_password=settings.neo4j_password,
                openai_api_key=settings.openai_api_key,
                model="gpt-4o",  # or settings.embedding_model depending on what's configured, but gpt-4o is standard
            )
            result = await orch.run_excel(file_path=str(path), llm_extraction=True)
            logger.info(f"Completed Excel ingestion for {filename}: {result.committed_rows} committed rows.")
        except Exception as e:
            logger.error(f"Error during Excel ingestion for {filename}: {e}", exc_info=True)
        finally:
            if 'orch' in locals():
                await orch.close()
            # Cleanup temp files
            try:
                shutil.rmtree(directory)
            except OSError as e:
                logger.warning(f"Failed to clean up temp directory {directory}: {e}")
                
    # Run the processing in the background so the HTTP request completes quickly
    background_tasks.add_task(process_file, temp_path, safe_filename, temp_dir)
    
    return {
        "message": "Excel ingestion started in background",
        "job_id": job_id,
        "filename": safe_filename,
    }
