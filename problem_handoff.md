# Problem Handoff to Claude: CivicProof UI Redesign

## Current Status (What I have completed)
The entire CivicProof microservice architecture has been successfully deployed to Google Cloud Platform and is 100% functional end-to-end. 
- **Frontend** (Next.js) is deployed on Cloud Run and correctly pointing to the API. (`https://civicproof-frontend-1094138601527.us-central1.run.app`)
- **API** (FastAPI) is deployed on Cloud Run with Cloud SQL Auth Proxy. (`https://civicproof-api-1094138601527.us-central1.run.app/api/docs`)
- **Worker** (Celery) is running on Cloud Run, connected to Redis (Memorystore) and Cloud SQL.
- **Gateway** (LLM routing) is running on Cloud Run, securely pulling OpenRouter API keys from Secret Manager.
- **Database** (PostgreSQL) has been seeded via a custom Alembic migrator Cloud Run job.

**The functional pipeline (Ingest -> Search -> Investigate -> Agentic Processing -> Results) now works flawlessly in production.**

## The Remaining Problem (What you need to do)
The user is dissatisfied with the current UI/UX of the frontend dashboard. 

The user stated: *"looks vibecoded, unusable"*

**Your task is to completely redesign and rewrite the Next.js frontend to have a cleaner, more usable, and more premium aesthetic.** 
This involves:
1. Moving away from the current generic "vibecoded" / standard tailwind aesthetic.
2. Implementing a more modern, minimalist, highly usable, and data-dense design suited for a professional intelligence platform.
3. Ensuring all interactive elements are functional, intuitive, and visually distinct.

## Where to find things
- The entire frontend codebase is located in `frontend/`. It uses Next.js 16 (App Router) with standard CSS modules/Tailwind.
- The `frontend/app/globals.css` currently contains a lot of custom UI styles that need to be overhauled.
- The API client definitions are in `frontend/app/lib/api.js`.

Good luck!
