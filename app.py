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
st.markdown("""
<style>
a[href^="#"] { display: none !important; }
h1 a, h2 a, h3 a, h4 a, h5 a, h6 a { display: none !important; }
</style>
""", unsafe_allow_html=True)
st.title("🌐 Multi Job Board Aggregator")
st.caption("Enter a job title and a location. The app fetches top job listings from multiple job boards and displays them neatly for you.")

# ----------------------------
# URL Builders
# ----------------------------
def hyphenate(s: str) -> str:
    return re.sub(r"\s+", "-", s.strip().lower())

def build_urls(job_title: str, location: str) -> dict:
    job_dash = hyphenate(job_title)
    loc_dash = hyphenate(location)
    return {
        "Adzuna": f"https://www.adzuna.co.uk/jobs/search?q={job_title}&w={location}",
        "CWJobs": f"https://www.cwjobs.co.uk/jobs/{job_dash}/in-{loc_dash}?radius=10&searchOrigin=Resultlist_top-search",
        "TotalJobs": f"https://www.totaljobs.com/jobs/{job_dash}/in-{loc_dash}?radius=10&searchOrigin=Resultlist_top-search",
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
    "Adzuna": "Extract job titles, company names, locations, and salaries from Adzuna job cards. Return JSON array of objects with keys: job_title, company_name, location, salary.",
    "CWJobs": "Extract job titles, company names, locations, and salaries from CWJobs search results. Return JSON array of objects with keys: job_title, company_name, location, salary.",
    "TotalJobs": "Extract job titles, company names, locations, and salaries from TotalJobs search results. Return JSON array of objects with keys: job_title, company_name, location, salary.",
    "Indeed": "Extract job titles, company names, locations, and salaries from Indeed search results. Return JSON array of objects with keys: job_title, company_name, location, salary.",
    "Reed": "Extract job titles, company names, locations, and salaries from Reed search results. Return JSON array of objects with keys: job_title, company_name, location, salary.",
    "CVLibrary": "Extract job titles, company names, locations, and salaries from CVLibrary search results. Return JSON array of objects with keys: job_title, company_name, location, salary.",
    "Hays": "Extract job titles, company names, locations, and salaries from Hays search results. Return JSON array of objects with keys: job_title, company_name, location, salary.",
    "Breakroom": "Extract job titles, company names, locations, and salaries from Breakroom search results. Return JSON array of objects with keys: job_title, company_name, location, salary."
}

def get_prompt(site_name: str) -> str:
    return SITE_PROMPTS.get(site_name, "")

# ----------------------------
# Firecrawl Scraping with retry
# ----------------------------
def scrape_jobs(url: str, site_name: str) -> list[dict]:
    if not API_KEY:
        raise RuntimeError("FIRECRAWL_API_KEY is not set in Streamlit Secrets")

    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {
        "urls": [url],
        "extractPrompt": get_prompt(site_name),
        "formats": ["json"]
    }

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

# ----------------------------
# Run all sites
# ----------------------------
@st.cache_data(show_spinner=False, ttl=600)
def run_all(job_title: str, location: str) -> dict:
    urls = build_urls(job_title, location)
    out = {}

    with st.status("Fetching job data...", expanded=True) as status_container:
        for site, url in urls.items():
            start_time = time.time()
            st.write(f"🌐 Starting scrape for **{site}**...")

            try:
                jobs = scrape_jobs(url, site)

                r = requests.get(url)
                if "Sorry, no results were found" in r.text:
                    jobs = []

                out[site] = {"url": url, "jobs": jobs}
                duration = time.time() - start_time
                st.write(f"✅ **{site}** completed in {duration:.2f} seconds.")

            except Exception as e:
                out[site] = {"url": url, "jobs": [], "error": str(e)}
                duration = time.time() - start_time
                st.error(f"❌ Failed to scrape **{site}** after {duration:.2f} seconds: {e}")

        status_container.update(label="All scraping tasks completed!", state="complete", expanded=False)

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
            accent = SITE_COLORS.get(site, "#1a73e8")
            st.markdown(
                f'<a href="{payload["url"]}" target="_blank" style="display:inline-block;padding:12px 24px;background-color:{accent};color:white;text-decoration:none;font-weight:bold;border-radius:8px;margin-bottom:20px;font-size:1.1em;">🔗 View on {site}</a>',
                unsafe_allow_html=True
            )
            err = payload.get("error")
            if err:
                st.warning(f"⚠️ {err}")
                continue

            jobs = payload.get("jobs", [])
            if not jobs:
                st.info("😕 No job results found for your search.")
                continue

            col1, col2 = st.columns(2)
            for i, j in enumerate(jobs):
                title = j.get("job_title") or "Unknown title"
                company = j.get("company_name") or "Unknown company"
                location = j.get("location") or "Unknown location"
                salary = j.get("salary") or "N/A"

                accent = SITE_COLORS.get(site, "#1f2937")
                card_html = f"""
                <div style="padding:20px;margin:12px 0;border-radius:15px;border:1px solid {accent};background: linear-gradient(90deg, #fdfdfd, #f7f9fc);box-shadow:0 4px 12px rgba(0,0,0,0.08);">
                    <h4 style="margin:0;color:{accent};font-weight:700;">{i + 1}. {title}</h4>
                    <p style="margin:4px 0 0;color:#4b5563;">🏢 Company: {company}</p>
                    <p style="margin:2px 0 0;color:#6b7280;">📍 Location: {location}</p>
                    <p style="margin:2px 0 0;color:#4b5563;">💰 Salary: {salary}</p>
                </div>
                """
                if i % 2 == 0:
                    col1.markdown(card_html, unsafe_allow_html=True)
                else:
                    col2.markdown(card_html, unsafe_allow_html=True)

    st.divider()
