import os
import math
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

# --- Config & Auth ---
load_dotenv()
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

# --- Data Models (Input from your React frontend) ---
class LiftStats(BaseModel):
    exercise_id: str
    one_rep_max: float
    is_upper_body: bool

class WendlerRequest(BaseModel):
    user_id: str
    weeks: int = 12 # 12 weeks = 3 cycles
    smallest_plate_increment: float = 5.0 # For rounding (e.g., 5 lbs or 2.5 kg)
    lifts: dict[str, LiftStats] # Keys: "squat", "bench", "deadlift", "ohp"

# --- Wendler Constants ---
WENDLER_PERCENTAGES = {
    1: [(5, 0.65), (5, 0.75), (5, 0.85)], # Week 1: 3x5
    2: [(3, 0.70), (3, 0.80), (3, 0.90)], # Week 2: 3x3
    3: [(5, 0.75), (3, 0.85), (1, 0.95)], # Week 3: 5/3/1
    4: [(5, 0.40), (5, 0.50), (5, 0.60)]  # Week 4: Deload
}

# --- Helper Function: Rounding Weights ---
def round_weight(weight: float, increment: float) -> float:
    """Rounds the calculated weight to the nearest available plate increment."""
    return increment * round(weight / increment)

# --- The Generator Endpoint ---
@app.post("/api/generate/wendler")
async def generate_wendler_program(req: WendlerRequest):
    if req.weeks % 4 != 0:
        raise HTTPException(status_code=400, detail="Wendler programs must be in 4-week multiples.")

    cycles = req.weeks // 4
    
    # 1. Create the Routine in Supabase
    routine_res = supabase.table('routines').insert({
        "user_id": req.user_id,
        "name": f"Wendler 5/3/1 ({req.weeks} Weeks)",
        "weeks": req.weeks
    }).execute()
    routine_id = routine_res.data[0]['id']

    # 2. Calculate Initial Training Maxes (90% of 1RM)
    training_maxes = {
        name: data.one_rep_max * 0.9 
        for name, data in req.lifts.items()
    }

    # 3. Generate the Cycles
    for cycle in range(cycles):
        for week in range(1, 5):
            absolute_week = (cycle * 4) + week
            
            # 4 Days per week in standard Wendler
            for day_idx, (lift_name, lift_data) in enumerate(req.lifts.items()):
                
                # Create the Day (e.g., "Week 1, Day 1: Squat")
                day_res = supabase.table('days').insert({
                    "routine_id": routine_id,
                    "day_of_week": day_idx + 1, 
                    "description": f"Week {absolute_week} - {lift_name.title()}"
                }).execute()
                day_id = day_res.data[0]['id']

                # Create the Slot (Slot 1 is always the main compound lift)
                slot_res = supabase.table('slots').insert({
                    "day_id": day_id,
                    "exercise_id": lift_data.exercise_id,
                    "sort_order": 1
                }).execute()
                slot_id = slot_res.data[0]['id']

                # Generate the Sets (Slot Entries)
                current_tm = training_maxes[lift_name]
                sets_to_insert = []
                
                for set_num, (reps, percentage) in enumerate(WENDLER_PERCENTAGES[week]):
                    raw_weight = current_tm * percentage
                    working_weight = round_weight(raw_weight, req.smallest_plate_increment)
                    
                    sets_to_insert.append({
                        "slot_id": slot_id,
                        "set_number": set_num + 1,
                        "reps": reps,
                        "weight": working_weight,
                        "rest_seconds": 180 # 3 minutes rest for heavy compounds
                    })
                
                # Bulk insert the working sets for this day
                supabase.table('slot_entries').insert(sets_to_insert).execute()

        # After Week 4 of a cycle, increment the Training Maxes for the next cycle
        for lift_name, lift_data in req.lifts.items():
            increase = 5.0 if lift_data.is_upper_body else 10.0
            training_maxes[lift_name] += increase

    return {"status": "success", "routine_id": routine_id, "message": f"Generated {req.weeks} weeks of 5/3/1"}