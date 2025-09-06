import os
import re
import json
import requests
import streamlit as st
from urllib.parse import quote_plus

# Firecrawl API key (from Streamlit Secrets)
API_KEY = st.secrets.get("FIRECRAWL_API_KEY")
API_URL = "https://api.firecrawl.dev/v1/scrape"

st.set_page_config(page_title="Multi Job Board Scraper", layout="wide")
st.title("🌐 Multi Job Board Scraper")

st.caption("Enter a job title and a location. The app builds 7 job board URLs, calls Firecrawl, and shows the top 10 results per site.")

# ----------------------------
# URL Builders
# ----------------------------
def hyphenate(s: str) -> str:
    return re.sub(r"\s+", "-", s.strip())

def build_urls(job_title: str, location: str) -> dict:
    q_job = quote_plus(job_title.strip())
    q_loc = quote_plus(location.strip())

    job_dash = hyphenate(job_title)
    loc_dash = hyphenate(location)

    return {
        "Adzuna":     f"https://www.adzuna.co.uk/jobs/search?q={q_job}&w={q_loc}",
        "CWJobs":     f"https://www.cwjobs.co.uk/jobs/{job_dash}/in-{loc_dash}?radius=10&searchOrigin=Resultlist_top-search",
        "TotalJobs":  f"https://www.totaljobs.com/jobs/{job_dash}/in-{loc_dash}?radius=10&searchOrigin=Resultlist_top-search",
        "Jooble":     f"https://uk.jooble.org/SearchResult?rgns={q_loc}&ukw={q_job}",
        "Indeed":     f"https://uk.indeed.com/jobs?q={q_job}&l={q_loc}",
        "Reed":       f"https://www.reed.co.uk/jobs/{job_dash}-jobs-in-{loc_dash}",
        "CVLibrary":  f"https://www.cv-library.co.uk/{job_dash}-jobs-in-{loc_dash}",
    }

# ----------------------------
# Firecrawl Prompt
# ----------------------------
BASE_PROMPT = """
Extract job titles and company names from job listings on this search results page.
Job titles are typically in elements with class 'jobtitle' or within <h2> tags with class 'title' or <a> tags with 'data-tn-element=jobTitle'.
Company names are typically in elements with class 'company' or 'companyName'.
Focus on job cards (e.g., elements with class 'job_seen_beacon' or 'result').
Ignore ads, footers, navigation, or unrelated content.
Return a JSON array of objects with fields: job_title, company_name.
"""

# ----------------------------
# Firecrawl Call
# ----------------------------
def scrape_jobs(url: str) -> list[dict]:
    if not API_KEY:
        raise RuntimeError("FIRECRAWL_API_KEY is not set in Streamlit Secrets")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "url": url,
        "formats": ["extract"],
        "extract": {"prompt": BASE_PROMPT}
    }

    r = requests.post(API_URL, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}, {r.text}")

    data = r.json()
    results = data.get("data", {}).get("extract", [])
    if isinstance(results, dict) and "extract" in results:
        results = results["extract"]
    if not isinstance(results, list):
        results = []
    return results[:10]

@st.cache_data(show_spinner=False, ttl=600)
def run_all(job_title: str, location: str) -> dict:
    urls = build_urls(job_title, location)
    out = {}
    for site, url in urls.items():
        try:
            jobs = scrape_jobs(url)
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
    with st.spinner("Scraping job boards with Firecrawl..."):
        data = run_all(job_title, location)

    # Summary
    all_jobs = [j for p in data.values() for j in p.get("jobs", [])]
    st.metric("Total Jobs Found", len(all_jobs))

    # Tabs for each site
    tabs = st.tabs(list(data.keys()))

    for tab, (site, payload) in zip(tabs, data.items()):
        with tab:
            st.write(f"[Search link]({payload['url']})")

            err = payload.get("error")
            if err:
                st.warning(f"⚠️ Failed to scrape: {err}")
                continue

            jobs = payload.get("jobs", [])
            if not jobs:
                st.info("No jobs found.")
                continue

            # Job Cards
            for j in jobs:
                title = j.get("job_title") or "Unknown title"
                company = j.get("company_name") or "Unknown company"

                st.markdown(f"""
                <div style="padding:15px; margin:10px 0; border-radius:12px;
                            border:1px solid #ddd; background-color:#fdfdfd;
                            box-shadow: 0 2px 6px rgba(0,0,0,0.05);">
                    <h4 style="margin:0; color:#333;">{title}</h4>
                    <p style="margin:2px 0 0; color:#666;">{company}</p>
                </div>
                """, unsafe_allow_html=True)

    st.divider()
    st.caption("✨ Demo dashboard built with Streamlit and Firecrawl")
