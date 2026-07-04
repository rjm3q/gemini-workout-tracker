import os
import psycopg2
import requests
from supabase import create_client, Client
from dotenv import load_dotenv

# ==========================================
# 1. Configuration & Auth
# ==========================================
load_dotenv()
DB_URL = os.environ.get("DATABASE_URL")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
WGER_BASE = "https://wger.de/api/v2/"

# ==========================================
# 2. Schema Creation (Direct Postgres)
# ==========================================
def build_database_schema():
    print("--- Building Supabase Schema ---")
    
    # The consolidated SQL schema
    schema_sql = """
    -- Enable UUID generation
    CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

    -- 1. Core Dictionaries
    CREATE TABLE IF NOT EXISTS languages (
        id SERIAL PRIMARY KEY,
        short_name VARCHAR(10) UNIQUE,
        full_name TEXT
    );

    CREATE TABLE IF NOT EXISTS muscles (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        is_front BOOLEAN,
        image_url_main TEXT
    );

    CREATE TABLE IF NOT EXISTS equipment (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS exercise_categories (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS exercises (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        category_id INT REFERENCES exercise_categories(id),
        equipment_id INT REFERENCES equipment(id),
        name TEXT NOT NULL,
        description TEXT,
        tracks_weight BOOLEAN DEFAULT TRUE,
        tracks_distance BOOLEAN DEFAULT FALSE,
        tracks_time BOOLEAN DEFAULT FALSE
    );

    CREATE TABLE IF NOT EXISTS exercise_muscles (
        exercise_id UUID REFERENCES exercises(id) ON DELETE CASCADE,
        muscle_id INT REFERENCES muscles(id) ON DELETE CASCADE,
        recruitment_level TEXT,
        PRIMARY KEY (exercise_id, muscle_id)
    );

    -- 2. Workout Programming (The Planner)
    CREATE TABLE IF NOT EXISTS routines (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        user_id UUID, -- References auth.users later
        name TEXT NOT NULL,
        weeks INT DEFAULT 4,
        is_public_template BOOLEAN DEFAULT FALSE
    );

    CREATE TABLE IF NOT EXISTS days (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        routine_id UUID REFERENCES routines(id) ON DELETE CASCADE,
        day_of_week INT,
        description TEXT
    );

    CREATE TABLE IF NOT EXISTS slots (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        day_id UUID REFERENCES days(id) ON DELETE CASCADE,
        exercise_id UUID REFERENCES exercises(id),
        sort_order INT NOT NULL
    );

    -- This replaces the 10+ Wger config tables
    CREATE TABLE IF NOT EXISTS slot_entries (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        slot_id UUID REFERENCES slots(id) ON DELETE CASCADE,
        set_number INT NOT NULL,
        reps INT,
        weight NUMERIC,
        rir INT,
        rest_seconds INT
    );
    """

    try:
        # Connect directly to Postgres
        conn = psycopg2.connect(DB_URL)
        cursor = conn.cursor()
        
        # Execute the schema DDL
        cursor.execute(schema_sql)
        conn.commit()
        
        cursor.close()
        conn.close()
        print("✅ Schema built successfully!")
    except Exception as e:
        print(f"❌ Failed to build schema: {e}")
        raise e

# ==========================================
# 3. Fetching Helper
# ==========================================
def fetch_all_wger_data(endpoint, params=None):
    url = f"{WGER_BASE}{endpoint}/"
    results = []
    while url:
        print(f"Fetching: {url}")
        response = requests.get(url, params=params).json()
        results.extend(response.get('results', []))
        url = response.get('next')
        params = None
    return results

# ==========================================
# 4. Data Seeding (Supabase REST API)
# ==========================================
def seed_database():
    print("\n--- Seeding Core Data from Wger ---")
    
    # 1. Fetch and store our lookup IDs first to satisfy Foreign Keys
    cat_map = {}
    print("Seeding Categories...")
    for item in fetch_all_wger_data("exercisecategory"):
        supabase.table('exercise_categories').upsert({"id": item['id'], "name": item['name']}).execute()
        cat_map[item['id']] = item['id']

    eq_map = {}
    print("Seeding Equipment...")
    for item in fetch_all_wger_data("equipment"):
        supabase.table('equipment').upsert({"id": item['id'], "name": item['name']}).execute()
        eq_map[item['id']] = item['id']

    # 2. Seed Exercises
    print("\nSeeding Exercises via /exerciseinfo/ ...")
    exercises_info = fetch_all_wger_data("exerciseinfo")
    
    success_count = 0
    fail_count = 0

    for ex in exercises_info:
        # --- NEW: Extract Name and Description from Translations ---
        translations = ex.get('translations', [])
        
        # Try to find the English translation (Language ID 2)
        english_trans = next((t for t in translations if t.get('language') == 2), None)
        
        # Fallback to the first available translation if English doesn't exist
        if not english_trans and translations:
            english_trans = translations[0]
            
        # If there are NO translations, we have to skip it
        if not english_trans:
            continue
            
        ex_name = english_trans.get('name')
        description = english_trans.get('description', '')
        
        if not ex_name:
            continue

        # --- Extract Nested Relationships ---
        category_data = ex.get('category', {})
        category_id = category_data.get('id')
        
        equipment_list = ex.get('equipment', [])
        equipment_id = equipment_list[0].get('id') if equipment_list else None

        # Verify Foreign Keys
        safe_cat_id = category_id if category_id in cat_map else None
        safe_eq_id = equipment_id if equipment_id in eq_map else None

        try:
            is_cardio = True if category_data.get('name') == 'Cardio' else False

            supa_exercise = {
                "name": ex_name,
                "description": description,
                "category_id": safe_cat_id,
                "equipment_id": safe_eq_id,
                "tracks_weight": not is_cardio,
                "tracks_distance": is_cardio,
                "tracks_time": is_cardio
            }
            
            ex_res = supabase.table('exercises').insert(supa_exercise).execute()
            
            if ex_res.data:
                success_count += 1
                supa_ex_id = ex_res.data[0]['id']
                
                # --- Map Muscles (With Deduplication) ---
                muscle_payload = []
                seen_muscles = set() # Track muscles to prevent duplicates

                # 1. Add Primary Muscles
                for m in ex.get('muscles', []):
                    m_id = m.get('id')
                    if m_id and m_id not in seen_muscles:
                        muscle_payload.append({
                            "exercise_id": supa_ex_id, 
                            "muscle_id": m_id, 
                            "recruitment_level": "Primary"
                        })
                        seen_muscles.add(m_id)

                # 2. Add Secondary Muscles
                for m in ex.get('muscles_secondary', []):
                    m_id = m.get('id')
                    # Only add if Wger hasn't already listed it as a primary muscle
                    if m_id and m_id not in seen_muscles:
                        muscle_payload.append({
                            "exercise_id": supa_ex_id, 
                            "muscle_id": m_id, 
                            "recruitment_level": "Secondary"
                        })
                        seen_muscles.add(m_id)
                
                if muscle_payload:
                    supabase.table('exercise_muscles').insert(muscle_payload).execute()
                    
        except Exception as e:
            fail_count += 1
            print(f"❌ Failed to insert '{ex_name}': {e}")
            continue

    print(f"\n✅ Seeding Complete! Successfully inserted: {success_count}. Failed: {fail_count}.")

# ==========================================
# 5. Execution
# ==========================================
if __name__ == "__main__":
    build_database_schema()
    seed_database()