import os
import re
import json
import requests
import streamlit as st
from urllib.parse import quote_plus
import time

# Firecrawl API key from Streamlit Secrets
API_KEY = st.secrets.get("FIRECRAWL_API_KEY")
API_URL = "https://api.firecrawl.dev/v1/scrape"

st.set_page_config(page_title="Job Board Aggregator", layout="wide")
st.title("🌐 Multi Job Board Aggregator")

st.caption("Enter a job title and a location. The app fetches top job listings from multiple job boards and displays them neatly for you.")


# ----------------------------
# URL Builders
# ----------------------------
def hyphenate(s: str) -> str:
    return re.sub(r"\s+", "-", s.strip().lower())

def build_urls(job_title: str, location: str) -> dict:
    q_job = quote_plus(job_title.strip().lower())
    q_loc = quote_plus(location.strip().lower())
    job_dash = hyphenate(job_title)
    loc_dash = hyphenate(location)

    return {
     #   "Adzuna":     f"https://www.adzuna.co.uk/jobs/search?q={q_job}&w={q_loc}",
     #   "CWJobs":     f"https://www.cwjobs.co.uk/jobs/{job_dash}/in-{loc_dash}?radius=10&searchOrigin=Resultlist_top-search",
     #   "TotalJobs":  f"https://www.totaljobs.com/jobs/{job_dash}/in-{loc_dash}?radius=10&searchOrigin=Resultlist_top-search",
        "Jooble":     f"https://uk.jooble.org/SearchResult?rgns={q_loc}&ukw={q_job}",
     #   "Indeed":     f"https://uk.indeed.com/jobs?q={q_job}&l={q_loc}",
     #   "Reed":       f"https://www.reed.co.uk/jobs/{job_dash}-jobs-in-{loc_dash}",
     #   "CVLibrary":  f"https://www.cv-library.co.uk/{job_dash}-jobs-in-{loc_dash}",
    }

# ----------------------------
# Site-specific prompts
# ----------------------------
SITE_PROMPTS = {
    "Reed": """
Extract job titles, company names, and job locations from this Reed search results page.

Each job listing is in an <article> element with class containing 'job-card_jobCard'.
Within the <header> section of each job card:
- Job title: <a> tag with data-element="job_title"
- Company: <a> tag with data-element="recruiter"
- Location: <li> element with data-qa="job-card-location"

Return JSON array of objects: job_title, company_name, location
Ignore any content outside <header> (including job descriptions or "Go to similar" links)
""",
    "Indeed": """
Extract job titles, company names, and job locations from this Indeed page.

- Job title: element with class 'jobtitle' or <h2 class="title"><a ...></a></h2>
- Company: class 'company' or 'companyName'
- Location: class 'location' or 'companyLocation'

Return JSON array of objects: job_title, company_name, location
Ignore ads, footers, or unrelated content
""",
    "Adzuna": """
Extract job titles, company names, and job locations from Adzuna job cards.

- Job title: element with class 'job_title' or similar
- Company: element with class 'company' or 'company_name'
- Location: element with class 'location'

Return JSON array of objects: job_title, company_name, location
Ignore unrelated content
""",
    "CWJobs": """
Extract job titles, company names, and job locations from CWJobs.

- Job title: <h2> or <a> inside job card
- Company: element with class 'job-company'
- Location: element with class 'job-location'

Return JSON array of objects: job_title, company_name, location
Ignore unrelated content
""",
    "TotalJobs": """
Extract job titles, company names, and job locations from TotalJobs.

- Job title: element with class 'job-title'
- Company: element with class 'job-company'
- Location: element with class 'job-location'

Return JSON array of objects: job_title, company_name, location
Ignore unrelated content
""",
    "Jooble": """
Extract job titles, company names, and job locations from this Jooble search results page.

Each job listing is contained within a job card container (e.g., a <div> with class containing 'job-listing' or similar).  
Within each job card:
- Extract the job title from the <a> tag with class 'job_card_link'. Keep the full text exactly as it appears.
- Extract the company name from the <p> tag with attribute data-test-name="_companyName".
- Extract the location from the element that contains the location text (class 'location' or similar within the job card).

Return a JSON array of objects, one per job card, with fields: job_title, company_name, location.
Ignore ads, similar jobs, badges, or any content outside the job card container.
""",
    "CVLibrary": """
Extract job titles, company names, and job locations from CVLibrary search results.

- Job title: <h2> or <a> inside job card
- Company: element with class 'job-company'
- Location: element with class 'job-location'

Return JSON array of objects: job_title, company_name, location
Ignore unrelated content
"""
}

def get_prompt(site_name: str) -> str:
    return SITE_PROMPTS.get(site_name)

# ----------------------------
# Firecrawl Scraping with retry
# ----------------------------
def scrape_jobs(url: str, site_name: str) -> list[dict]:
    if not API_KEY:
        raise RuntimeError("FIRECRAWL_API_KEY is not set in Streamlit Secrets")

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"url": url, "formats": ["extract"], "extract": {"prompt": get_prompt(site_name)}}

    for attempt in range(3):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            results = data.get("data", {}).get("extract", [])
            if isinstance(results, dict) and "extract" in results:
                results = results["extract"]
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

@st.cache_data(show_spinner=False, ttl=600)
def run_all(job_title: str, location: str) -> dict:
    urls = build_urls(job_title, location)
    out = {}
    for site, url in urls.items():
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
    with st.spinner("Fetching the hottest jobs for you... 🔍"):
        data = run_all(job_title, location)

    # Summary
    all_jobs = [j for p in data.values() for j in p.get("jobs", [])]
    st.metric("Total Jobs Found", len(all_jobs))

    # Tabs
    tabs = st.tabs(list(data.keys()))

    for tab, (site, payload) in zip(tabs, data.items()):
        with tab:
            st.write(f"[Search link]({payload['url']})")

            err = payload.get("error")
            if err:
                st.warning(f"⚠️ {err}")
                continue

            jobs = payload.get("jobs", [])
            if not jobs:
                st.info("No jobs found.")
                continue


            # Define site colors
            SITE_COLORS = {
                "Adzuna": "#FF6B6B",
                "CWJobs": "#4F46E5",
                "TotalJobs": "#10B981",
                "Jooble": "#F59E0B",
                "Indeed": "#2563EB",
                "Reed": "#8B5CF6",
                "CVLibrary": "#F43F5E"
            }

            # Job cards with site-based color accents
            for j in jobs:
                title = j.get("job_title") or "Unknown title"
                company = j.get("company_name") or "Unknown company"
                location = j.get("location") or "Unknown location"

                accent = SITE_COLORS.get(site, "#1f2937")  # default dark gray

                st.markdown(f"""
                <div style="
                    padding:20px; 
                    margin:12px 0; 
                    border-radius:15px; 
                    border:1px solid {accent}; 
                    background: linear-gradient(90deg, #fdfdfd, #f7f9fc);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
                    transition: transform 0.2s;
                " onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                    <h4 style="margin:0; color:{accent}; font-weight:700;">{title}</h4>
                    <p style="margin:4px 0 0; color:#4b5563;">
                        <span style="margin-right:6px;">🏢</span> Company: {company}
                    </p>
                    <p style="margin:2px 0 0; color:#6b7280;">
                        <span style="margin-right:6px;">📍</span> Location: {location}
                    </p>
                </div>
                """, unsafe_allow_html=True)



    st.divider()
    st.caption("✨ Demo dashboard built with Streamlit, aggregating top jobs for you")
