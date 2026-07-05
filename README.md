# Fitness Backend API & Schema Seeding

This project serves as the robust backend engine for a data-driven workout tracker. It leverages **FastAPI** for dynamic workout generation and **Supabase (PostgreSQL)** for data persistence. The project is managed using **uv** for efficient dependency handling.

---

## Script Overview

### 1. `main.py`

This is your primary application server. It exposes the API endpoints that your React frontend will interact with to generate training programs.

* **Key Functionality:** The `/api/generate/wendler` endpoint.
* **Logic:** It takes a user's 1-Rep Maxes, automatically calculates training percentages (based on the 5/3/1 methodology), handles weight rounding for standard plates, and injects the entire cycle into your database hierarchy (`routines` → `days` → `slots` → `slot_entries`).

### 2. `db_schema_seed.py`

This is your foundational administration script. It handles the "Source of Truth" for your database.

* **Schema Build:** Contains the DDL instructions to create the relational tables (Exercises, Routines, Templates, etc.).
* **Data Ingestion:** Fetches extensive exercise data from the [wger.de](https://www.google.com/search?q=https://wger.de/) API.
* **Template & Routine Seeding:** Populates your database with pre-configured workout templates (PPL, Upper/Lower) and famous macrocycle macro-plans (e.g., Starting Strength, Juggernaut Method, StrongFirst Kettlebell routines).

### 3. `wger_diagnosis.py`

A diagnostic utility script designed for troubleshooting your data ingestion.

* **Purpose:** If you encounter issues with the API or database insertion (like rate limits, missing keys, or Row Level Security issues), this script tests the connection with a minimal subset of data (5 exercises).
* **Use Case:** Run this if you need to verify that your Supabase credentials, API permissions, and network connectivity are working without running the full, large-scale seed process.

---

## Architecture Summary

The system is built on a highly normalized relational structure:

| Layer | Components | Purpose |
| --- | --- | --- |
| **Catalog** | `exercises`, `muscles`, `equipment` | The foundation of all exercises. |
| **Planning** | `routines`, `days`, `slots` | Macrocycle and microcycle scheduling. |
| **Execution** | `workouts`, `workout_sets` | Tracking actual performance data. |
| **Templates** | `workout_templates`, `workout_template_targets` | Quick-start workout generation. |

---

## Setup & Running

1. **Dependencies:** Ensure `uv` is installed and the virtual environment is active.
```bash
uv sync
source .venv/bin/activate  # Or your system's equivalent

```


2. **Environment Variables:** Ensure your `.env` file contains the correct `SUPABASE_URL`, `SUPABASE_KEY` (use the `service_role` key for seeding), and `DATABASE_URL` (for `psycopg2` schema creation).
3. **Seeding:** Execute the seed script to prepare your database:
```bash
python db_schema_seed.py

```


4. **API:** Start the server for your frontend to consume:
```bash
uvicorn main:app --reload

```