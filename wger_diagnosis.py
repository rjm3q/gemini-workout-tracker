import os
import requests
import time
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
# CRITICAL: Verify this is the SERVICE_ROLE key, not the ANON key
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") 
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
WGER_BASE = "https://wger.de/api/v2/"

def fetch_all_wger_data(endpoint, params=None):
    url = f"{WGER_BASE}{endpoint}/"
    results = []
    
    while url:
        print(f"Fetching: {url}")
        response = requests.get(url, params=params)
        
        # 1. CHECK FOR RATE LIMITING
        if response.status_code == 429:
            print(f"🛑 WGER RATE LIMIT HIT! The API is blocking us. Sleeping for 5 seconds...")
            time.sleep(5)
            continue # Try the exact same URL again
            
        if response.status_code != 200:
            print(f"🛑 WGER API ERROR: {response.status_code} - {response.text}")
            break

        data = response.json()
        
        # 2. CHECK FOR MALFORMED DATA
        if 'results' not in data:
            print(f"🛑 UNEXPECTED WGER RESPONSE (No 'results' key found): {data}")
            break
            
        results.extend(data.get('results', []))
        url = data.get('next')
        params = None # Only pass params on first run
        
    return results

def seed_database():
    print("\n--- Diagnostic Seeding Started ---")
    
    exercises_info = fetch_all_wger_data("exerciseinfo")
    print(f"\n📊 TOTAL EXERCISES DOWNLOADED FROM WGER: {len(exercises_info)}")
    
    if len(exercises_info) == 0:
        print("🛑 FATAL: No exercises downloaded. The script cannot continue.")
        return

    success_count = 0
    fail_count = 0

    print("Attempting to insert first 5 exercises as a test...")
    
    # We will only try 5 exercises first so we don't spam the database while testing
    for ex in exercises_info[:5]:
        ex_name = ex.get('name')
        if not ex_name:
            continue
            
        try:
            # We will force nulls for categories/equipment to rule out Foreign Key issues
            supa_exercise = {
                "name": ex_name,
                "description": ex.get('description', ''),
                "tracks_weight": True,
                "tracks_distance": False,
                "tracks_time": False
            }
            
            print(f"Trying to insert: {ex_name}...")
            ex_res = supabase.table('exercises').insert(supa_exercise).execute()
            
            # 3. CHECK FOR SILENT SUPABASE FAILURES (RLS)
            if not ex_res.data or len(ex_res.data) == 0:
                print(f"🛑 SUPABASE SILENT FAILURE! Data was sent, but Supabase returned nothing. Check Row Level Security (RLS) or your API Key.")
                fail_count += 1
            else:
                print(f"✅ Successfully inserted: {ex_name} (ID: {ex_res.data[0]['id']})")
                success_count += 1
                
        except Exception as e:
            fail_count += 1
            print(f"❌ SUPABASE EXCEPTION on '{ex_name}': {e}")
            continue

    print(f"\nDiagnostic Complete! Success: {success_count} | Fail: {fail_count}")

if __name__ == "__main__":
    seed_database()