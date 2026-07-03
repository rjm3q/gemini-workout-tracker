import os
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

# Load your raw dataset (e.g., from a CSV)
# Assuming columns like: 'Name', 'Type', 'Equipment', 'Primary_Muscle', 'Mechanic'
raw_data = pd.read_csv("raw_exercises.csv")

# Clean data: drop nulls in critical columns, standardize text to Title Case
raw_data['Name'] = raw_data['Name'].str.title()
raw_data['Equipment'] = raw_data['Equipment'].str.title()

def seed_lookups():
    # 1. Extract unique equipment
    unique_equipment = raw_data['Equipment'].dropna().unique().tolist()
    equipment_payload = [{"name": eq} for eq in unique_equipment]
    
    # Bulk insert and return the data
    eq_response = supabase.table('equipment').insert(equipment_payload).execute()
    
    # Create a mapping dictionary: {'Barbell': 1, 'Dumbbell': 2, ...}
    eq_map = {item['name']: item['id'] for item in eq_response.data}
    
    # (Repeat this exact process for exercise_categories and muscles)
    # category_map = ...
    # muscle_map = ...
    
    return eq_map # Return maps to use in Step 3

def seed_exercises(eq_map, category_map):
    exercises_payload = []
    
    for index, row in raw_data.iterrows():
        # Logic to determine tracking flags based on category or equipment
        tracks_weight = True if row['Type'] in ['Weightlifting', 'Powerlifting'] else False
        tracks_distance = True if row['Type'] == 'Cardio' or row['Equipment'] == 'Sled' else False
        tracks_time = True if row['Type'] in ['Cardio', 'Stretching'] else False

        exercise = {
            "name": row['Name'],
            "equipment_id": eq_map.get(row['Equipment']),
            "category_id": category_map.get(row['Type']),
            "mechanic": row['Mechanic'], # Compound, Isolation
            "tracks_weight": tracks_weight,
            "tracks_distance": tracks_distance,
            "tracks_time": tracks_time
        }
        exercises_payload.append(exercise)
        
    # Supabase allows bulk inserts up to a certain size. 
    # If your dataset is huge (1000+), chunk the payload into batches of 200.
    ex_response = supabase.table('exercises').insert(exercises_payload).execute()
    
    # Create a map of the new UUIDs for the final step
    ex_map = {item['name']: item['id'] for item in ex_response.data}
    return ex_map

def seed_exercise_muscles(ex_map, muscle_map):
    junction_payload = []
    
    for index, row in raw_data.iterrows():
        ex_id = ex_map.get(row['Name'])
        
        # Primary Muscle
        if pd.notna(row['Primary_Muscle']):
            primary_id = muscle_map.get(row['Primary_Muscle'])
            if primary_id:
                junction_payload.append({
                    "exercise_id": ex_id,
                    "muscle_id": primary_id,
                    "recruitment_level": "Primary"
                })
                
        # (Repeat logic for Secondary_Muscle if your CSV has it)

    # Bulk insert the relationships
    supabase.table('exercise_muscles').insert(junction_payload).execute()