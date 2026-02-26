# BimAtlas Scripts

## Full Setup and Upload (with Video Recording)

This workflow sets up the environment, uploads the sample IFC file to a project branch, and records a video of the process.

### Prerequisites

- Docker (for PostgreSQL + Apache AGE)
- Python 3.11+ with `pip` or `uv`
- Node.js 20+ with `pnpm`
- Playwright: `pip install playwright httpx && playwright install chromium`

### Quick Run (services already running)

If the database, API, and frontend are already running:

```bash
python3 scripts/record_setup_and_upload.py
```

The video is saved to `recordings/setup_and_upload.webm`.

### Full Setup from Scratch

1. **Start the database:**
   ```bash
   cd infra && docker compose up -d
   ```
   Wait a few seconds for PostgreSQL to initialize.

2. **Start the API:**
   ```bash
   cd apps/api && uv sync && source .venv/bin/activate && ./run.sh
   ```
   (Run in a separate terminal or in background.)

3. **Start the frontend:**
   ```bash
   cd apps/web && pnpm install && pnpm run dev
   ```
   (Run in a separate terminal or in background.)

4. **Run the recording script:**
   ```bash
   python3 scripts/record_setup_and_upload.py
   ```

### What the Recording Script Does

1. Creates a project named "Demo Project" via the GraphQL API (with auto-created `main` branch).
2. Opens the BimAtlas frontend in a headless browser.
3. Selects the new project.
4. Opens the Import IFC modal and uploads `apps/sample_files/Ifc4_SampleHouse.ifc`.
5. Records the browser session as a WebM video.

### Output

- **Video:** `recordings/setup_and_upload.webm` (WebM format, ~1280×720)
- The sample house model is ingested into the project's main branch and can be viewed in the 3D viewport and graph.
