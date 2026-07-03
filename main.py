import os
import requests
from supabase import create_client, Client
from dotenv import load_dotenv

# ==========================================
# 1. Setup and Authentication
# ==========================================
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Wger API Base URL
WGER_BASE = "https://wger.de/api/v2/"

# ==========================================
# 2. Helper Function: Handle API Pagination
# ==========================================
def fetch_all_wger_data(endpoint, params=None):
    """Fetches all pages of data from a given Wger API endpoint."""
    url = f"{WGER_BASE}{endpoint}/"
    results = []
    
    while url:
        print(f"Fetching: {url}")
        response = requests.get(url, params=params).json()
        results.extend(response.get('results', []))
        url = response.get('next') # Wger provides a 'next' URL if there are more pages
        params = None # Only pass params on the first request; 'next' URL includes them
        
    return results

# ==========================================
# 3. Fetch and Seed Lookup Tables
# ==========================================
def seed_lookups():
    print("--- Fetching Lookup Data from Wger ---")
    
    # Fetch Data
    wger_categories = fetch_all_wger_data("exercisecategory")
    wger_equipment = fetch_all_wger_data("equipment")
    wger_muscles = fetch_all_wger_data("muscle")
    
    # We will map Wger's native IDs to Supabase UUIDs
    wger_to_supa_category = {}
    wger_to_supa_equipment = {}
    wger_to_supa_muscle = {}
    
    # Insert Categories
    print("Inserting Categories...")
    for cat in wger_categories:
        res = supabase.table('exercise_categories').insert({"name": cat['name']}).execute()
        wger_to_supa_category[cat['id']] = res.data[0]['id']
        
    # Insert Equipment
    print("Inserting Equipment...")
    for eq in wger_equipment:
        res = supabase.table('equipment').insert({"name": eq['name']}).execute()
        wger_to_supa_equipment[eq['id']] = res.data[0]['id']

    # Insert Muscles
    print("Inserting Muscles...")
    for mus in wger_muscles:
        res = supabase.table('muscles').insert({
            "name": mus['name_en'] if mus.get('name_en') else mus['name'],
            "general_group": "Unknown" # Wger doesn't easily map this, update manually later if needed
        }).execute()
        wger_to_supa_muscle[mus['id']] = res.data[0]['id']

    return wger_to_supa_category, wger_to_supa_equipment, wger_to_supa_muscle

# ==========================================
# 4. Fetch and Seed Exercises
# ==========================================
def seed_exercises(cat_map, eq_map, muscle_map):
    print("--- Fetching Exercises from Wger ---")
    
    # Fetch only English exercises (language=2 in Wger API)
    wger_exercises = fetch_all_wger_data("exercise", params={"language": 2})
    
    exercises_payload = []
    exercise_muscle_payload = []
    
    print(f"Processing {len(wger_exercises)} exercises...")
    
    for ex in wger_exercises:
        # Determine tracking flags. Wger doesn't explicitly state if it tracks time/distance, 
        # but we can infer based on the category string (e.g., if category is "Cardio")
        cat_name = ""
        for wger_id, supa_id in cat_map.items():
            if ex['category'] == wger_id:
                # Need the original Wger category name for logic
                # For brevity in this script, we'll assume default weightlifting unless noted
                cat_name = "Cardio" if ex['category'] == 9 else "Weightlifting" 

        # Build Exercise object for Supabase
        # Wger allows multiple equipment IDs; we will just grab the first one if it exists
        equipment_id = ex['equipment'][0] if ex['equipment'] else None
        
        supa_exercise = {
            "name": ex['name'],
            "category_id": cat_map.get(ex['category']),
            "equipment_id": eq_map.get(equipment_id) if equipment_id else None,
            "mechanic": "Compound", # Defaulting, as Wger doesn't provide isolation vs compound
            "tracks_weight": True if cat_name != "Cardio" else False,
            "tracks_distance": True if cat_name == "Cardio" else False,
            "tracks_time": True if cat_name == "Cardio" else False
        }
        
        # Insert Exercise individually so we can get its UUID for the muscle mapping
        ex_res = supabase.table('exercises').insert(supa_exercise).execute()
        supa_ex_id = ex_res.data[0]['id']
        
        # Map Primary Muscles (Wger array: 'muscles')
        for m_id in ex.get('muscles', []):
            if m_id in muscle_map:
                exercise_muscle_payload.append({
                    "exercise_id": supa_ex_id,
                    "muscle_id": muscle_map[m_id],
                    "recruitment_level": "Primary"
                })
                
        # Map Secondary Muscles (Wger array: 'muscles_secondary')
        for m_id in ex.get('muscles_secondary', []):
            if m_id in muscle_map:
                exercise_muscle_payload.append({
                    "exercise_id": supa_ex_id,
                    "muscle_id": muscle_map[m_id],
                    "recruitment_level": "Secondary"
                })

    # Bulk insert all the muscle relationships
    print(f"Inserting {len(exercise_muscle_payload)} muscle relationships...")
    
    # Supabase limits bulk inserts, chunk it if necessary
    chunk_size = 200
    for i in range(0, len(exercise_muscle_payload), chunk_size):
        chunk = exercise_muscle_payload[i:i + chunk_size]
        supabase.table('exercise_muscles').insert(chunk).execute()

    print("✅ Database Seeded Successfully!")

# ==========================================
# 5. Execute Pipeline
# ==========================================
if __name__ == "__main__":
    try:
        cat_map, eq_map, muscle_map = seed_lookups()
        seed_exercises(cat_map, eq_map, muscle_map)
    except Exception as e:
        print(f"Error during seeding: {e}")