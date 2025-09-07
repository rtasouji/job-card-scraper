import os
import re
import json
import requests
import streamlit as st
import time

# Firecrawl API key from Streamlit Secrets
API_KEY = st.secrets.get("FIRECRAWL_API_KEY")
API_URL = "https://api.firecrawl.dev/v1/extract"

st.set_page_config(page_title="Job Board Aggregator", layout="wide")
st.title("🌐 Multi Job Board Aggregator")
st.caption("Enter a job title and location to fetch top job listings from multiple job boards.")

# ----------------------------
# Helper functions
# ----------------------------
def hyphenate(s: str) -> str:
    return re.sub(r"\s+", "-", s.strip().lower())

def build_urls(job_title: str, location: str) -> dict:
    job_dash = hyphenate(job_title)
    loc_dash = hyphenate(location)

    return {
        "Adzuna": f"https://www.adzuna.co.uk/jobs/search?q={job_title}&w={location}",
        "CWJobs": f"https://www.cwjobs.co.uk/jobs/{job_dash}/in-{loc_dash}?radius=10&searchOrigin=Resultlist_top-search",
        "TotalJobs": f"https://www.totaljobs.com/jobs/{job_dash}/in-{loc_dash}",
        "Indeed": f"https://uk.indeed.com/jobs?q={job_title}&l={location}",
        "Reed": f"https://www.reed.co.uk/jobs/{job_dash}-jobs-in-{loc_dash}",
        "CVLibrary": f"https://www.cv-library.co.uk/{job_dash}-jobs-in-{loc_dash}",
        "Hays": f"https://www.hays.co.uk/job-search/{job_dash}-jobs-in-{loc_dash}-uk",
        "Breakroom": f"https://www.breakroom.cc/en-gb/{job_dash}-jobs-in-{loc_dash}"
    }

# ----------------------------
# Site-specific prompts
# ----------------------------
SITE_PROMPTS = {
    "Adzuna": """
Each job card is a <div> with class 'job-result'. 
Extract:
- Job title: element with class 'job-title'
- Company: element with class 'company'
- Location: element with class 'location'
- Salary: element with class 'salary'
Return a JSON array of objects: job_title, company_name, location, salary
""",
    "CWJobs": """
Each job card is an <article> with class 'job'. 
Extract:
- Job title: <h2> or <a> inside the article
- Company: element with class 'job-company'
- Location: element with class 'location'
- Salary: element with class 'salary'
Return JSON array of objects: job_title, company_name, location, salary
""",
    "TotalJobs": """
Each job card is a <div> with class 'job'. 
Extract job_title, company_name, location, salary for each.
Return as JSON array.
""",
    "Indeed": """
Each job card is a <div> with class 'job_seen_beacon'. 
Extract job_title, company_name, location, salary for each.
Return as JSON array.
""",
    "Reed": """
Each job card is an <article> with class containing 'job-card_jobCard'. 
Extract job_title, company_name, location, salary for each.
Return JSON array.
""",
    "CVLibrary": """
Each job card is a <div> with class 'job'. 
Extract job_title, company_name, location, salary for each.
Return JSON array.
""",
    "Hays": """
Each job card is a <div> with class 'job-card'. 
Extract job_title, company_name, location, salary for each.
Return JSON array.
""",
    "Breakroom": """
Each job card is a <div> with class 'job-card'. 
Extract job_title, company_name, location, salary for each.
Return JSON array.
"""
}

def get_prompt(site_name: str) -> str:
    return SITE_PROMPTS.get(site_name, "Extract job_title, company_name, location, salary for each job card on this page and return as JSON array.")

# ----------------------------
# Scrape function
# ----------------------------
def scrape_jobs(url: str, site_name: str) -> list[dict]:
    if not API_KEY:
        raise RuntimeError("FIRECRAWL_API_KEY is not set in Streamlit Secrets")

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "url": url,
        "formats": ["json"],
        "extract": {"prompt": get_prompt(site_name)}
    }

    for attempt in range(3):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            results = data.get("data", {}).get("extract", [])
            if not isinstance(results, list):
                results = []
            return results[:10]
        except requests.exceptions.ReadTimeout:
            time.sleep(2)
            if attempt == 2:
                raise RuntimeError(f"ReadTimeout for {site_name} ({url})")
        except Exception as e:
            if attempt == 2:
                raise RuntimeError(f"Failed to scrape {site_name}: {e}")

# ----------------------------
# Run all sites
# ----------------------------
@st.cache_data(show_spinner=False, ttl=600)
def run_all(job_title: str, location: str) -> dict:
    urls = build_urls(job_title, location)
    out = {}
    for site, url in urls.items():
        start_time = time.time()
        try:
            jobs = scrape_jobs(url, site)
            out[site] = {"url": url, "jobs": jobs}
        except Exception as e:
            out[site] = {"url": url, "jobs": [], "error": str(e)}
    return out

# ----------------------------
# UI
# ----------------------------
with st.form("search"):
    col1, col2 = st.columns(2)
    job_title = col1.text_input("Job title", "Data Analyst")
    location = col2.text_input("Location", "London")
    submitted = st.form_submit_button("Search")

if submitted:
    with st.spinner("Fetching jobs... 🔍"):
        data = run_all(job_title, location)

    all_jobs = [j for p in data.values() for j in p.get("jobs", [])]
    st.metric("Total Jobs Found", len(all_jobs))

    tabs = st.tabs(list(data.keys()))
    SITE_COLORS = {
        "Adzuna": "#279B37", "CWJobs": "#D17119", "TotalJobs": "#005F75",
        "Hays": "#0F42BE", "Indeed": "#003A9B", "Reed": "#FF00CD",
        "CVLibrary": "#014694", "Breakroom": "#F1666A"
    }

    for tab, (site, payload) in zip(tabs, data.items()):
        with tab:
            err = payload.get("error")
            if err:
                st.warning(f"⚠️ {err}")
                continue

            jobs = payload.get("jobs", [])
            if not jobs:
                st.info("😕 No job results found for this site.")
                continue

            col1, col2 = st.columns(2)
            accent = SITE_COLORS.get(site, "#1f2937")

            for i, j in enumerate(jobs):
                title = j.get("job_title") or "Unknown title"
                company = j.get("company_name") or "Unknown company"
                location = j.get("location") or "Unknown location"
                salary = j.get("salary") or "N/A"

                card_html = f"""
                <div style="
                    padding:20px; margin:12px 0; border-radius:15px;
                    border:1px solid {accent}; background: #f7f9fc;
                    box-shadow:0 4px 12px rgba(0,0,0,0.08); transition: transform 0.2s;"
                    onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                    <h4 style="margin:0; color:{accent}; font-weight:700;">{i+1}. {title}</h4>
                    <p style="margin:2px 0;">🏢 Company: {company}</p>
                    <p style="margin:2px 0;">📍 Location: {location}</p>
                    <p style="margin:2px 0;">💰 Salary: {salary}</p>
                </div>
                """
                if i % 2 == 0:
                    col1.markdown(card_html, unsafe_allow_html=True)
                else:
                    col2.markdown(card_html, unsafe_allow_html=True)
