import asyncio
import os
import pandas as pd
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from services.pipeline.orchestrator import PipelineOrchestrator
from services.retrieval_api.services.neo4j_service import Neo4jService

async def main():
    # 1. Create Synthetic Excel File
    print("Creating synthetic Excel test file...")
    data = {
        # Nodes
        "site_name": ["Northern Command HQ", "Ramat David Airbase", "Haifa Port"],
        "facility_name": ["Command Center Alpha", "Hangar 4", "Fuel Depot"],
        "component_name": ["Main Server Rack", "Jet Storage", "Pump Substation"],
        "category": ["Command Post", "Storage", "Logistics"],
        "responsible_body": ["Northern Comm", "Air Force", "Navy Transport"],
        "system": ["C2 System", "Avionics System", "Fuel Delivery System"],
        
        # Efforts
        "support_for_attack_effort": [0.9, 0.4, 0.2],
        "support_for_defende_control_effort": [0.8, 0.2, 0.1],
        "support_for_intelligence_effort": [0.6, 0.1, 0.0],
        "support_for_allert_effort": [0.7, 0.5, 0.0],
        "support_for_national_effort": [0.5, 0.3, 0.8],
        
        # Geography
        "polygon": ["POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))", "POLYGON((2 2, 3 2, 3 3, 2 3, 2 2))", "POLYGON((5 5, 6 5, 6 6, 5 6, 5 5))"],
        "central_point": ["POINT(0.5 0.5)", "POINT(2.5 2.5)", "POINT(5.5 5.5)"],
        "refined_coordinate": ["POINT(0.5 0.5)", "POINT(2.5 2.5)", "POINT(5.5 5.5)"],
        
        # Categorical / Meta
        "deffence_with_iron_dome": ["TRUE", "FALSE", "TRUE"],
        "level_for_deffense_with_upper_layer": ["HIGH", "LOW", "MEDIUM"],
        "hardening": ["Level 3 Reinforced", "Basic", "Bunker"],
        "concealments": ["None", "Camouflage Netting", "Underground"],
        "distribution": ["Centralized", "Distributed", "Node"],
        "recovery_capability": ["24 hours", "1 Week", "48 Hours"],
        "redundancy": ["Dual Active", "Cold Standby", "Hot Standby"],
        "mobility": ["Fixed", "Mobile Deployable", "Fixed"],
        
        # Free Text
        "details_on_facilty_purpose": [
            "This center coordinates all northern front operations and acts as the primary C4I node containing the 'Zeus' AI targeting server.",
            "Stores critical F-35 fighter jets and connects directly to the underground fuel reservoir network.",
            "Key national logistics hub for strategic fuel. The main control station interfaces with the national grid directly."
        ],
        "operational_significance_if_damaged": ["Critical loss of northern C2.", "Loss of 4 F-35s.", "National fuel crisis."],
        "sop_if_damaged": ["Evacuate to backup bunker B.", "Use secondary hangar 5.", "Route fuel from Ashdod."],
        "system_information": [
            "The C2 System integrates radar feeds from Hermon and issues direct attack vectors.",
            "Independent avionics testing lab is located inside.",
            "Pumping mechanism uses the Delta-V control loop."
        ],
        "component_importance_to_system": ["Critical processing unit.", "Storage only.", "Main flow valve."],
        "distribution_details": ["Feeds 5 sub-commands.", "Local use only.", "National pipeline feed."],
        "redundency_details": ["Has satellite auto-failover.", "None.", "Backup diesel generators."],

        # Structured References
        "primary_backup": ["Backup Site B", "Hangar 5", "Ashdod Depot"],
        "secondary_primary": ["Backup Site C", "Hangar 6", "Eilat Depot"],
        "related_facilty": ["Command Center Beta", "Base Security HQ", "Port Authority"],
        "connected_power_station": ["Power Station A, Power Station B\nPower Station C", "Power Station Z", "Grid Substation 4"],
        "connection_to_strategic_fuel_reserves": ["No", "Reserve Alpha", "Main Terminal"],
        "site_by_aerial_defense": ["Patriot Unit 1", "David Sling Unit", "Iron Dome Battery 4"]
    }

    df = pd.DataFrame(data)
    test_file_path = "test_impact_ingestion_v2.xlsx"
    df.to_excel(test_file_path, index=False)
    print(f"Created {test_file_path}")

    # Configuration for integration (Assumes local DB or environment vars)
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "changeme")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "ollama")

    # 2. Run Pipeline
    try:
        print("Starting orchestrator ingestion...")
        orchestrator = PipelineOrchestrator(
            neo4j_uri=NEO4J_URI,
            neo4j_user=NEO4J_USER,
            neo4j_password=NEO4J_PASS,
            openai_api_key=OPENAI_API_KEY,
            model="gpt-4o-mini" # Using a fast model for tests
        )
        
        result = await orchestrator.run_excel(
            file_path=str(Path(test_file_path).resolve()),
            connector_id="test",
            llm_extraction=True
        )
        print("Ingestion complete:")
        print(f"Entities: {result.new_entities}, Edges: {result.new_edges}")

        await orchestrator.close()

        # 3. Verify in Neo4j Service
        print("\nVerifying using Retrieval API (Neo4jService)...")
        service = Neo4jService(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASS)
        await service.connect()

        lookup_alpha = await service.lookup_concept("Command Center Alpha")
        print(f"\nLookup 'Command Center Alpha': found={lookup_alpha.found}")
        if lookup_alpha.found:
            print(f"Definition (+ injected Geo/Attrs): {lookup_alpha.definition}")
            for r in lookup_alpha.related:
                print(f" - Related [{r.relation}]: {r.name} (wt: {getattr(r, 'weight', None)}, meaning: {getattr(r, 'meaning', None)})")

        lookup_hangar = await service.lookup_concept("Hangar 4")
        print(f"\nLookup 'Hangar 4': found={lookup_hangar.found}")
        if lookup_hangar.found:
            for r in lookup_hangar.related:
                print(f" - Related [{r.relation}]: {r.name}")

        await service.close()

    except Exception as e:
        import traceback
        print(f"Test failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
