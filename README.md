# SafeRoute AI — Beginner Prototype

## What this demo does
- Geocodes place names in Bangladesh.
- Requests walking routes from OpenRouteService.
- Compares routes against a supplied CSV of road-condition observations.
- Displays a transparent *provisional indicator*, not a crime probability.
- Lets the user prepare an SOS message and open WhatsApp to share it manually.

## Important safety and data limitations
- `sample_safety_data.csv` contains FICTIONAL PLACEHOLDER RECORDS. They are not real reports and must not be used for real travel decisions.
- No route can be guaranteed safe. No incident records does not mean a route is safe.
- SOS does not automatically track a phone, send a message, call 999, or contact police.
- Do not upload identifiable survivor data, personal addresses, phone numbers, or unverified accusations.
- Before public deployment, replace the placeholder User-Agent in `app.py` with a contact email and review service terms, rate limits, privacy, and security.

## Step 1 — Install Python
Install Python 3.11 or a compatible recent version from https://www.python.org/downloads/
During installation on Windows, tick "Add Python to PATH" if offered.

## Step 2 — Unzip and open the folder
Extract `SafeRouteAI.zip`. Open a terminal / Command Prompt in the `saferoute_ai` folder.

## Step 3 — Create a virtual environment (recommended)
Windows:
```powershell
py -m venv .venv
.venv\Scripts\activate
```
macOS/Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Step 4 — Install packages
```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Step 5 — Get a walking routing API key
Create an account at https://openrouteservice.org/dev/#/signup and obtain an API key.
Check current plan limits and terms. Do not post your key in public code.

Create `.streamlit/secrets.toml` inside the project folder with:
```toml
OPENROUTESERVICE_API_KEY = "PASTE_YOUR_OWN_KEY_HERE"
```
Do not upload `secrets.toml` to GitHub. It is excluded by the suggested `.gitignore` below.

The geocoder uses Nominatim. Follow its usage policy, including identifying your app properly, caching requests, and avoiding bulk or high-volume queries. For a public project, consider a geocoding provider suitable for your expected traffic.

## Step 6 — Run the app
```bash
streamlit run app.py
```
Your browser should open the app. If it doesn't, visit the local URL printed in the terminal, usually http://localhost:8501.

## Step 7 — Replace fictional sample data
Use the sidebar CSV uploader to upload your own appropriately sourced, non-identifying dataset. Required columns:
- `name`
- `latitude`
- `longitude`
- `lighting_poor` (0 or 1)
- `verified_incidents_90d` (non-negative count; use only trustworthy, appropriately aggregated data)
- `public_places_nearby` (non-negative count)
- `confidence` (0–1 with a documented definition)

Use blank/unknown values when you do not know something; do not invent incident counts. The included sample records are fictional and only demonstrate how the interface works.

## Step 8 — Publish for the public
1. Create a GitHub repository and upload `app.py`, `requirements.txt`, and `sample_safety_data.csv`.
2. Do NOT upload `.streamlit/secrets.toml`.
3. Open https://share.streamlit.io/ and connect your GitHub account.
4. Choose the repository, branch, and `app.py` as the main file.
5. In app settings / Secrets, add:
   `OPENROUTESERVICE_API_KEY = "your-key"`
6. Deploy and test the public link in a private/incognito browser window.
7. Review usage limits, API terms, privacy disclosures, and whether the app is suitable for public access.

## Troubleshooting
- `ModuleNotFoundError`: activate the virtual environment and rerun `pip install -r requirements.txt`.
- Routing API error: check the key, provider limits, and service status.
- Location not found: try a more specific address or nearby landmark.
- No safety data: the app will show "Insufficient data." This is intentional and is not a safety rating.
- Public deployment fails: check Streamlit logs and confirm that all required packages are in `requirements.txt`.

## .gitignore
Create a `.gitignore` file containing:
```gitignore
.venv/
__pycache__/
.streamlit/secrets.toml
.env
```
