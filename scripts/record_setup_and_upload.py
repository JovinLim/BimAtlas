#!/usr/bin/env python3
"""
Record a video of: creating a project/branch and uploading the sample IFC file
from apps/sample_files into a project branch.

Prerequisites: DB, API (port 8000), and frontend (port 5173) must be running.
Install: pip install playwright httpx && playwright install chromium
"""
import asyncio
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
SAMPLE_IFC = WORKSPACE / "apps" / "sample_files" / "Ifc4_SampleHouse.ifc"
VIDEO_DIR = WORKSPACE / "recordings"
FRONTEND_URL = "http://localhost:5173"
API_URL = "http://localhost:8000"


async def create_project_and_branch():
    """Create project via GraphQL; returns (project_id, branch_id)."""
    import httpx

    query = """
    mutation CreateProject($name: String!, $description: String) {
        createProject(name: $name, description: $description) {
            id
            branches { id name }
        }
    }
    """
    async with httpx.AsyncClient(base_url=API_URL, timeout=30) as client:
        r = await client.post(
            "/graphql",
            json={"query": query, "variables": {"name": "Demo Project", "description": "Setup and upload demo"}},
        )
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            raise RuntimeError(data["errors"])
        proj = data["data"]["createProject"]
        branch = proj["branches"][0]  # main is auto-created
        return proj["id"], branch["id"]


async def main():
    VIDEO_DIR.mkdir(exist_ok=True)
    if not SAMPLE_IFC.exists():
        print(f"Error: Sample file not found: {SAMPLE_IFC}")
        sys.exit(1)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Install: pip install playwright httpx && playwright install chromium")
        sys.exit(1)

    # Create project via API (fast, reliable)
    print("Creating project and branch via API...")
    project_id, branch_id = await create_project_and_branch()
    print(f"  Project: {project_id}, Branch: {branch_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=str(VIDEO_DIR),
            record_video_size={"width": 1280, "height": 720},
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        try:
            # Open app
            print("Opening BimAtlas...")
            await page.goto(FRONTEND_URL, wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # Select the project we created (click on it in the list)
            print("Selecting project...")
            project_item = page.locator(f'button.project-item-main:has-text("Demo Project")')
            await project_item.click()
            await page.wait_for_timeout(2000)

            # Click Import IFC
            print("Opening Import IFC...")
            import_btn = page.get_by_role("button", name="Import IFC")
            await import_btn.click()
            await page.wait_for_timeout(1000)

            # Set file on the hidden input
            print("Selecting sample IFC file...")
            file_input = page.locator('#ifc-file-input')
            await file_input.set_input_files(str(SAMPLE_IFC))
            await page.wait_for_timeout(800)

            # Click Import in modal
            print("Uploading...")
            modal_import = page.locator('button.btn-primary:has-text("Import")')
            await modal_import.click()

            # Wait for upload/ingestion to complete
            await page.wait_for_timeout(12000)

            print("Recording complete.")
        finally:
            await context.close()
            await browser.close()

    # Rename video to a known name
    videos = list(VIDEO_DIR.glob("*.webm"))
    if videos:
        dest = VIDEO_DIR / "setup_and_upload.webm"
        videos[-1].rename(dest)
        print(f"Video saved to: {dest}")
    else:
        print("Video was recorded; check recordings/ for .webm files.")


if __name__ == "__main__":
    asyncio.run(main())
