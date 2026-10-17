import os
import math
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

st.set_page_config(
    page_title="SafeRoute AI",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.block-container {padding-top: 1.4rem; padding-bottom: 2rem;}
.hero {padding: 1.2rem 1.4rem; border-radius: 1rem; background: linear-gradient(120deg,#e9f4ff,#f2fbf6);}
.small-note {font-size: .9rem; color: #555;}
</style>
""", unsafe_allow_html=True)

st.title("🧭 SafeRoute AI")
st.markdown(
    '<div class="hero"><h3>Safety-aware route planning for more informed journeys</h3>'
    '<p>Compare routes using available local evidence, understand uncertainty, and prepare an emergency check-in.</p></div>',
    unsafe_allow_html=True,
)
st.warning(
    "Prototype notice: SafeRoute AI cannot predict or guarantee whether a road is safe. "
    "Risk indicators are only as reliable as the data entered. Missing reports do not mean a road is safe. "
    "For an immediate emergency in Bangladesh, call 999 if available."
)

# ---------------------- helpers ----------------------
USER_AGENT = "SafeRouteAI-educational-prototype/1.0 (contact: add-your-email-before-public-deployment)"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
ORS_URL = "https://api.openrouteservice.org/v2/directions/foot-walking/geojson"

def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2-lat1)
    dl = math.radians(lon2-lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.asin(math.sqrt(a))

@st.cache_data(ttl=3600, show_spinner=False)
def geocode(query):
    headers = {"User-Agent": USER_AGENT}
    response = requests.get(
        NOMINATIM_URL,
        params={"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "bd"},
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()
    items = response.json()
    if not items:
        return None
    item = items[0]
    return {
        "lat": float(item["lat"]),
        "lon": float(item["lon"]),
        "display_name": item.get("display_name", query),
    }

def load_safety_data(uploaded_file):
    if uploaded_file is not None:
        df = pd.read_csv(uploaded_file)
        source = "uploaded dataset"
    else:
        df = pd.read_csv(os.path.join(os.path.dirname(__file__), "sample_safety_data.csv"))
        source = "included sample dataset"
    needed = {
        "name", "latitude", "longitude", "lighting_poor",
        "verified_incidents_90d", "public_places_nearby", "confidence"
    }
    missing = needed.difference(df.columns)
    if missing:
        raise ValueError("Dataset is missing columns: " + ", ".join(sorted(missing)))
    for col in ["latitude", "longitude", "lighting_poor", "verified_incidents_90d",
                "public_places_nearby", "confidence"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    df["lighting_poor"] = df["lighting_poor"].fillna(0).clip(0, 1)
    df["verified_incidents_90d"] = df["verified_incidents_90d"].fillna(0).clip(lower=0)
    df["public_places_nearby"] = df["public_places_nearby"].fillna(0).clip(lower=0)
    df["confidence"] = df["confidence"].fillna(0).clip(0, 1)
    return df, source

def nearest_evidence(lat, lon, df, radius_m=600):
    if df.empty:
        return pd.DataFrame()
    work = df.copy()
    work["distance_m"] = work.apply(
        lambda r: haversine_m(lat, lon, r["latitude"], r["longitude"]), axis=1
    )
    return work[work["distance_m"] <= radius_m].sort_values("distance_m")

def assess_route(coords_lonlat, df):
    """Transparent provisional indicator, not a crime probability."""
    if not coords_lonlat:
        return None
    # Sample up to ~30 route points so the prototype remains responsive.
    stride = max(1, len(coords_lonlat) // 30)
    samples = coords_lonlat[::stride]
    if samples[-1] != coords_lonlat[-1]:
        samples.append(coords_lonlat[-1])

    evidence_rows = []
    for lon, lat in samples:
        nearby = nearest_evidence(lat, lon, df, radius_m=600)
        if not nearby.empty:
            # Use closest record to avoid counting the same record many times.
            evidence_rows.append(nearby.iloc[0].to_dict())

    if not evidence_rows:
        return {
            "score": None,
            "label": "Insufficient data",
            "confidence": "Low",
            "reasons": ["No safety records were found within 600 m of sampled route points."],
            "records": 0,
        }

    ev = pd.DataFrame(evidence_rows).drop_duplicates(subset=["name", "latitude", "longitude"])
    # A transparent heuristic score, not a statistically validated risk model.
    incident = (ev["verified_incidents_90d"].clip(0, 5) / 5).mean() * 45
    lighting = ev["lighting_poor"].mean() * 30
    isolation = (1 - (ev["public_places_nearby"].clip(0, 5) / 5)).mean() * 15
    # Lower confidence increases uncertainty, not the claim that the area is dangerous.
    score = round(min(100, incident + lighting + isolation), 1)
    avg_conf = float(ev["confidence"].mean())
    if avg_conf < 0.4:
        confidence = "Low"
    elif avg_conf < 0.7:
        confidence = "Moderate"
    else:
        confidence = "Higher (within this dataset only)"

    if score >= 60:
        label = "More caution indicators"
    elif score >= 30:
        label = "Some caution indicators"
    else:
        label = "Fewer indicators in available data"

    reasons = [
        f"Nearby records considered: {len(ev)}.",
        f"Poor-lighting indicator average: {ev['lighting_poor'].mean():.2f} (0–1).",
        f"Reported incidents in records: {int(ev['verified_incidents_90d'].sum())} across the selected records (90-day field).",
        f"Nearby public-place count field average: {ev['public_places_nearby'].mean():.1f}.",
        f"Data confidence level: {confidence}.",
    ]
    return {"score": score, "label": label, "confidence": confidence, "reasons": reasons, "records": len(ev)}

def get_walking_routes(start, end, api_key):
    # OpenRouteService walking profile. Requires the user's own API key.
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    body = {
        "coordinates": [[start["lon"], start["lat"]], [end["lon"], end["lat"]]],
        "alternative_routes": {"share_factor": 0.6, "target_count": 3, "weight_factor": 1.4},
        "instructions": False,
    }
    response = requests.post(ORS_URL, json=body, headers=headers, timeout=35)
    if response.status_code == 401:
        raise RuntimeError("OpenRouteService rejected the API key. Check your key in Streamlit secrets.")
    if response.status_code == 429:
        raise RuntimeError("Routing service rate limit reached. Please wait and try again.")
    response.raise_for_status()
    data = response.json()
    routes = []
    for feature in data.get("features", []):
        coords = feature["geometry"]["coordinates"]
        summary = feature.get("properties", {}).get("summary", {})
        routes.append({
            "coordinates": coords,
            "distance_km": summary.get("distance", 0) / 1000,
            "duration_min": summary.get("duration", 0) / 60,
        })
    return routes

def risk_color(score):
    if score is None:
        return "gray"
    if score >= 60:
        return "red"
    if score >= 30:
        return "orange"
    return "green"

# ---------------------- sidebar ----------------------
st.sidebar.header("Project settings")
st.sidebar.caption("For the public demo, use only data you have permission to publish.")
uploaded = st.sidebar.file_uploader("Upload safety data CSV (optional)", type=["csv"])
radius = st.sidebar.slider("Nearby evidence radius (metres)", 200, 1200, 600, 100)
st.sidebar.markdown("---")
st.sidebar.markdown("**Emergency support**")
st.sidebar.caption("SOS below is a user-triggered demo. It does not automatically contact police or track anyone.")

try:
    safety_df, data_source = load_safety_data(uploaded)
    if data_source == "included sample dataset":
        st.sidebar.info("Sample records are fictional placeholders. They are not real reports and must not be used for real travel decisions.")
except Exception as exc:
    st.error(f"Could not load safety dataset: {exc}")
    st.stop()

tab_route, tab_sos, tab_data, tab_about = st.tabs(
    ["🗺️ Route planner", "🆘 Emergency support", "📊 Data & methodology", "ℹ️ About"]
)

with tab_route:
    st.subheader("Compare walking routes")
    st.caption("Enter place names or addresses in Bangladesh. Geocoding and routing require an internet connection.")
    col1, col2 = st.columns(2)
    with col1:
        start_text = st.text_input("Starting point", value="University of Chittagong, Bangladesh")
    with col2:
        end_text = st.text_input("Destination", value="Chittagong University Railway Station, Bangladesh")

    ors_key = None
    try:
        ors_key = st.secrets.get("OPENROUTESERVICE_API_KEY", None)
    except Exception:
        ors_key = os.getenv("OPENROUTESERVICE_API_KEY")

    if not ors_key:
        st.info("To enable real walking routes, add a free OpenRouteService API key to `.streamlit/secrets.toml`. See README. Until then, the route planner will not invent route lines or risk rankings.")
    submitted = st.button("Find and compare routes", type="primary", use_container_width=True)

    if submitted:
        if not start_text.strip() or not end_text.strip():
            st.error("Enter both a starting point and destination.")
        elif not ors_key:
            st.error("Walking route service is not configured. Add your OpenRouteService API key, then restart the app.")
        else:
            try:
                with st.spinner("Finding locations and walking routes..."):
                    start = geocode(start_text.strip())
                    end = geocode(end_text.strip())
                    if not start or not end:
                        st.error("One or both locations could not be found. Try a more specific place name.")
                    else:
                        routes = get_walking_routes(start, end, ors_key)
                        if not routes:
                            st.warning("The routing service did not return a route. Try different locations.")
                        else:
                            assessed = []
                            for idx, route in enumerate(routes, start=1):
                                assessment = assess_route(route["coordinates"], safety_df)
                                route["assessment"] = assessment
                                route["route_name"] = f"Route {idx}"
                                assessed.append(route)

                            m = folium.Map(location=[start["lat"], start["lon"]], zoom_start=14, control_scale=True)
                            folium.Marker(
                                [start["lat"], start["lon"]],
                                tooltip="Start",
                                popup=folium.Popup(f"<b>Start</b><br>{start['display_name']}", max_width=300),
                                icon=folium.Icon(color="blue", icon="play"),
                            ).add_to(m)
                            folium.Marker(
                                [end["lat"], end["lon"]],
                                tooltip="Destination",
                                popup=folium.Popup(f"<b>Destination</b><br>{end['display_name']}", max_width=300),
                                icon=folium.Icon(color="purple", icon="flag"),
                            ).add_to(m)

                            for route in assessed:
                                coords_latlon = [(lat, lon) for lon, lat in route["coordinates"]]
                                ass = route["assessment"]
                                color = risk_color(ass["score"] if ass else None)
                                folium.PolyLine(
                                    coords_latlon,
                                    color=color,
                                    weight=6,
                                    opacity=0.8,
                                    tooltip=f"{route['route_name']} — {ass['label'] if ass else 'Not assessed'}",
                                ).add_to(m)

                            st_folium(m, use_container_width=True, height=480, returned_objects=[])

                            st.subheader("Route comparison")
                            for route in assessed:
                                ass = route["assessment"]
                                with st.container(border=True):
                                    a, b, c = st.columns([2, 1, 1])
                                    a.markdown(f"**{route['route_name']}**")
                                    a.caption(f"{route['distance_km']:.2f} km · {route['duration_min']:.0f} min estimated")
                                    if ass and ass["score"] is not None:
                                        b.metric("Provisional indicator", f"{ass['score']}/100")
                                        c.markdown(f"**{ass['label']}**")
                                        c.caption(f"Data confidence: {ass['confidence']}")
                                        with st.expander("Why this assessment?"):
                                            for reason in ass["reasons"]:
                                                st.write("• " + reason)
                                    else:
                                        b.metric("Assessment", "Unavailable")
                                        c.markdown("**Insufficient data**")
                                        st.caption("No nearby safety records were available. This does not mean the route is safe.")

                            st.info(
                                "How to read this: the score is a prototype heuristic based on the uploaded dataset, "
                                "not a validated probability of crime and not a guarantee of safety. Route colours must not "
                                "be used as the sole basis for a real-world safety decision."
                            )
            except requests.exceptions.RequestException as exc:
                st.error(f"A mapping service request failed: {exc}")
            except RuntimeError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Something went wrong: {exc}")

with tab_sos:
    st.subheader("SOS and trusted-contact support")
    st.warning("This is a prototype. It does not automatically track your phone, contact police, or dispatch emergency services.")
    st.markdown("If you are in immediate danger in Bangladesh, call **999** where available.")
    with st.form("sos_form"):
        st.write("Prepare an alert to share with a trusted contact.")
        name = st.text_input("Your preferred name (optional)")
        location_text = st.text_input("Your current location or a map link")
        contact = st.text_input("Trusted contact phone number (optional, for your own reference)")
        message = st.text_area(
            "Emergency message",
            value="I may need assistance. Please contact me and help me reach emergency services.",
        )
        consent = st.checkbox("I understand this only prepares a message; it will not automatically send or call anyone.")
        make_alert = st.form_submit_button("Prepare SOS message", type="primary")
    if make_alert:
        if not consent:
            st.error("Please confirm that you understand the prototype limitation.")
        elif not location_text.strip():
            st.error("Add a location or map link so your contact knows where you may need help.")
        else:
            alert_text = (
                f"EMERGENCY / CHECK-IN ALERT\n"
                f"Name: {name.strip() or 'Not provided'}\n"
                f"Location: {location_text.strip()}\n"
                f"Message: {message.strip()}\n"
                f"Please contact me and call official emergency services if needed."
            )
            st.text_area("Copy and share this alert", value=alert_text, height=150)
            wa_url = "https://wa.me/?text=" + quote(alert_text)
            st.link_button("Open WhatsApp to share", wa_url)
            st.caption("Review the recipient and message before sending. No message has been sent by this app.")

with tab_data:
    st.subheader("Data preview")
    st.write(f"Dataset loaded from: **{data_source}**")
    st.write(f"Records: **{len(safety_df)}**")
    if data_source == "included sample dataset":
        st.error("These are fictional example records for software demonstration only. They do not describe actual roads or incidents.")
    st.dataframe(safety_df, use_container_width=True, hide_index=True)
    st.markdown("""
    **Expected CSV columns**
    - `name`: a short segment or observation label.
    - `latitude`, `longitude`: coordinates for the observation.
    - `lighting_poor`: 1 if poor lighting was observed, 0 if not; use blank if unknown.
    - `verified_incidents_90d`: count of appropriately verified incidents in the prior 90 days, if a trustworthy source exists.
    - `public_places_nearby`: approximate count of accessible public places; define a consistent radius and method.
    - `confidence`: data-quality value between 0 and 1, assigned using a documented rule.

    Never upload identifiable survivor information, personal addresses, private phone numbers, or unverified accusations.
    """)

with tab_about:
    st.subheader("About SafeRoute AI")
    st.markdown("""
    SafeRoute AI is an educational prototype exploring how local data and AI-assisted explanations could support more informed route choices.

    **What it does:** maps walking routes through a configured routing provider; compares them against nearby records in a supplied dataset; explains the provisional indicator; prepares an SOS message for a user to share.

    **What it does not do:** predict an individual's likelihood of being assaulted; guarantee a route is safe; verify reports automatically; continuously track users; automatically contact police; or replace emergency services.

    **Data quality matters:** reports may be incomplete, outdated, geographically biased, or unverified. The absence of reports is not evidence of safety. Test the app with fictional data and clearly labelled demonstrations before considering any real-world deployment.
    """)
    st.markdown("Map data © OpenStreetMap contributors. Geocoding: Nominatim. Walking directions: OpenRouteService (when configured).")
