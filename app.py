import os
import re
import json
import requests
import streamlit as st
from urllib.parse import quote_plus

API_KEY = st.secrets.get("FIRECRAWL_API_KEY")

API_URL = "https://api.firecrawl.dev/v1/scrape"

st.set_page_config(page_title="Multi Job Board Scraper", layout="wide")
st.title("Multi Job Board Scraper")

st.caption("Enter a job title and a location, the app builds 7 job board URLs, calls Firecrawl on each, and shows the top 10 results per site.")

def hyphenate(s: str) -> str:
    return re.sub(r"\s+", "-", s.strip())

def build_urls(job_title: str, location: str) -> dict:
    # Query parameter safe values
    q_job = quote_plus(job_title.strip())
    q_loc = quote_plus(location.strip())

    # Path segment values that need hyphens
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

# Keep your prompt focused on title and company, as requested
BASE_PROMPT = """
Extract job titles and company names from job listings on this Indeed search results page.
Job titles are typically in elements with class 'jobtitle' or within <h2> tags with class 'title' or <a> tags with 'data-tn-element=jobTitle'.
Company names are typically in elements with class 'company' or 'companyName'.
Focus on job cards (e.g., elements with class 'job_seen_beacon' or 'result').
Ignore ads, footers, navigation, or unrelated content.
Return a JSON array of objects with fields: job_title, company_name.
"""

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
    # Firecrawl usually nests extract under data
    results = data.get("data", {}).get("extract", [])
    # Protect against other shapes
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

with st.form("search"):
    col1, col2 = st.columns(2)
    job_title = col1.text_input("Job title", "Data Analyst")
    location = col2.text_input("Location", "London")
    submitted = st.form_submit_button("Search")

if submitted:
    with st.spinner("Scraping job boards with Firecrawl, this usually takes a few seconds"):
        data = run_all(job_title, location)

    for site, payload in data.items():
        st.subheader(site)
        st.write(f"[Search link]({payload['url']})")
        err = payload.get("error")
        if err:
            st.warning(f"Failed to scrape, {err}")
            continue

        jobs = payload.get("jobs", [])
        if not jobs:
            st.write("No jobs found.")
            continue

        for j in jobs:
            title = j.get("job_title") or "Unknown title"
            company = j.get("company_name") or "Unknown company"
            st.write(f"- **{title}**, {company}")

    st.divider()
    st.caption("Tip, if some sites are sparse, we can add site specific prompts later.")
