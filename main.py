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
    
    # Maps for Wger ID -> Supabase DB ID
    maps = {'cat': {}, 'eq': {}, 'mus': {}}

    # 1. Seed Categories
    print("Seeding Categories...")
    for item in fetch_all_wger_data("exercisecategory"):
        res = supabase.table('exercise_categories').upsert({"id": item['id'], "name": item['name']}).execute()
        maps['cat'][item['id']] = item['id']

    # 2. Seed Equipment
    print("Seeding Equipment...")
    for item in fetch_all_wger_data("equipment"):
        res = supabase.table('equipment').upsert({"id": item['id'], "name": item['name']}).execute()
        maps['eq'][item['id']] = item['id']

    # 3. Seed Muscles
    print("Seeding Muscles...")
    for item in fetch_all_wger_data("muscle"):
        res = supabase.table('muscles').upsert({
            "id": item['id'], 
            "name": item['name_en'] if item.get('name_en') else item['name'],
            "is_front": item['is_front'],
            "image_url_main": item['image_url_main']
        }).execute()
        maps['mus'][item['id']] = item['id']

   # 4. Seed Exercises (English Only)
    print("Seeding Exercises & Junctions...")
    exercises = fetch_all_wger_data("exercise", params={"language": 2})
    
    for ex in exercises:
        # 1. DEFENSIVE CHECK: Skip if the exercise has no name
        ex_name = ex.get('name')
        if not ex_name:
            print(f"⚠️ Skipping malformed exercise (Missing Name). ID: {ex.get('id', 'Unknown')}")
            continue

        try:
            # Determine metrics flags based on category
            category_id = ex.get('category')
            is_cardio = True if category_id == 'Cardio' else False
            
            # Safely get the first equipment ID if it exists
            equipment_list = ex.get('equipment')
            equipment_id = equipment_list[0] if equipment_list and len(equipment_list) > 0 else None

            supa_exercise = {
                "name": ex_name,
                "description": ex.get('description', ''),
                "category_id": category_id,
                "equipment_id": equipment_id,
                "tracks_weight": not is_cardio,
                "tracks_distance": is_cardio,
                "tracks_time": is_cardio
            }
            
            # Insert Exercise
            ex_res = supabase.table('exercises').insert(supa_exercise).execute()
            
            # Make sure we got data back before proceeding
            if not ex_res.data:
                print(f"⚠️ Failed to insert {ex_name}, skipping muscles.")
                continue
                
            supa_ex_id = ex_res.data[0]['id']
            
            # Insert Muscle Junctions
            muscle_payload = []
            for m_id in ex.get('muscles', []):
                muscle_payload.append({"exercise_id": supa_ex_id, "muscle_id": m_id, "recruitment_level": "Primary"})
            for m_id in ex.get('muscles_secondary', []):
                muscle_payload.append({"exercise_id": supa_ex_id, "muscle_id": m_id, "recruitment_level": "Secondary"})
                
            if muscle_payload:
                supabase.table('exercise_muscles').insert(muscle_payload).execute()
                
        except Exception as e:
            # If ONE exercise causes a database error, catch it and keep going!
            print(f"❌ Error inserting '{ex_name}': {e}")
            continue

    print("✅ Database Seeded Successfully!")

# ==========================================
# 5. Execution
# ==========================================
if __name__ == "__main__":
    build_database_schema()
    seed_database()