import pandas as pd
import random
from uuid import uuid4

locations = [f'LOCATION-{i:03d}' for i in range(1, 151)]
departments = [f'DEPT-{i}' for i in range(1, 60)]
projects = [f'PROJ-{i}' for i in range(1, 250)]
clients = [f'CLIENT-{i}' for i in range(1, 600)]
statuses = ["ACTIVE", "ACTIVE", "ACTIVE", "PLANNED", "SUSPENDED"]

data = []
for i in range(100):
    loc_id = locations[i]
    deps = random.sample(departments, k=random.randint(1, 4))
    projs = random.sample(projects, k=random.randint(2, 6))
    cls = random.sample(clients, k=random.randint(3, 10))
    region = random.choice(["North", "South", "Central", "HQ"])
    capacity = random.randint(100, 1000)
    
    # Intentionally format dependencies as a complex string for the LLM to parse
    dep_str = f"Hosts {len(deps)} departments: {', '.join(deps)}. Runs {len(projs)} projects ({', '.join(projs)}). Serves {len(cls)} units including {', '.join(cls[:3])}."
    
    # Add status complexities for the LLM occasionally
    status = random.choice(statuses)
    if status != "ACTIVE":
        dep_str += f" NOTE: Entire site is currently {status}."
        
    data.append({
        'Location ID': loc_id,
        'Operational Dependencies': dep_str,
        'Site Description': f'{region} regional site with capacity {capacity}',
        'Region': region,
        'Capacity': capacity
    })

# Add a few intentionally broken / empty rows to test the Review Queue logic
data.append({'Location ID': '', 'Operational Dependencies': 'Missing location data', 'Site Description': 'Broken row', 'Region': 'Unknown', 'Capacity': 0})
data.append({'Location ID': 'LOC-X', 'Operational Dependencies': 'Invalid data format that makes no sense 1234', 'Site Description': '', 'Region': '', 'Capacity': 0})

df = pd.DataFrame(data)
out_path = 'c:/Users/User/AppData/Local/Temp/large_e2e_test_data.xlsx'
df.to_excel(out_path, index=False)
print(f'Generated {out_path} with {len(df)} rows')
