import os
import re
import json
import requests
import streamlit as st
from urllib.parse import quote_plus
import time
import concurrent.futures

# Firecrawl API key from Streamlit Secrets
API_KEY = st.secrets.get("FIRECRAWL_API_KEY")
API_URL = "https://api.firecrawl.dev/v1/scrape"

st.set_page_config(page_title="Job Board Aggregator", layout="wide")
st.title("🌐 Multi Job Board Aggregator")

st.caption("Enter a job title and a location. The app fetches top job listings from multiple job boards and displays them neatly for you.")


# ----------------------------
# URL Builders
# ----------------------------
# ----------------------------
# URL Builders (Hays + Breakroom included)
# ----------------------------
def hyphenate(s: str) -> str:
    return re.sub(r"\s+", "-", s.strip().lower())

def build_urls(job_title: str, location: str) -> dict:
    job_dash = hyphenate(job_title)
    loc_dash = hyphenate(location)

    return {
     "Adzuna":  f"https://www.adzuna.co.uk/jobs/search?q={job_title}&w={location}",
     "CWJobs":  f"https://www.cwjobs.co.uk/jobs/{job_dash}/in-{loc_dash}?radius=10&searchOrigin=Resultlist_top-search",
    # "TotalJobs": f"https://www.totaljobs.com/jobs/{job_dash}/in-{loc_dash}?radius=10&searchOrigin=Resultlist_top-search",
          "Indeed":  f"https://uk.indeed.com/jobs?q={job_title}&l={location}",
    # "Reed":  f"https://www.reed.co.uk/jobs/{job_dash}-jobs-in-{loc_dash}",
          "CVLibrary": f"https://www.cv-library.co.uk/{job_dash}-jobs-in-{loc_dash}",
    # "Hays":  f"https://www.hays.co.uk/job-search/{job_dash}-jobs-in-{loc_dash}-uk",
      #  "Breakroom": f"https://www.breakroom.cc/en-gb/{job_dash}-jobs-in-{loc_dash}"
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
    "Hays": """
Extract job titles, company names, and job locations from this Hays search results page.

Each job listing is contained in an element with class containing 'job-card' or similar.
Within each job card:
- Extract the job title from the <a> tag or heading element with class containing 'job-title'.
- Extract the company name from the element that contains the recruiter/employer name (often in a <span> or <p> tag inside the job card).
- Extract the location from the element containing the location info.

Return a JSON array of objects, one per job card, with fields: job_title, company_name, location.
Ignore ads, footers, similar jobs, or content outside the job cards.
""",

    "CVLibrary": """
Extract job titles, company names, and job locations from CVLibrary search results.

- Job title: <h2> or <a> inside job card
- Company: element with class 'job-company'
- Location: element with class 'job-location'

Return JSON array of objects: job_title, company_name, location
Ignore unrelated content
""",
    "Breakroom":"""
Extract job titles, company names, and job locations from this Breakroom search results page.

Each job listing is contained in a job card element (for example, class containing 'job-card' or similar).  
Within each job card:
- Extract the job title from the main title element (e.g., <h2> or <a> with class containing 'job-title'). Keep the full text exactly as it appears.  
- Extract the company name from the company element (e.g., <p>, <span>, or <div> with class containing 'company' or similar).  
- Extract the job location from the location element (e.g., class containing 'location' or similar).

Return a JSON array of objects, one per job card, with fields: job_title, company_name, location.  
Ignore ads, footers, similar jobs, or any content outside the job card container.

    """,
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
    
    # Create a wrapper function for the executor
    def scrape_single_site(site_name):
        url = urls[site_name]
        try:
            jobs = scrape_jobs(url, site_name)
            
            # Check for "no results" message
            r = requests.get(url)
            if "Sorry, no results were found" in r.text:
                jobs = []

            return site_name, {"url": url, "jobs": jobs}
        except Exception as e:
            return site_name, {"url": url, "jobs": [], "error": str(e)}

    # Get a list of sites to scrape
    sites_to_scrape = list(urls.keys())
    
    # Process sites in batches of 2
    for i in range(0, len(sites_to_scrape), 2):
        batch = sites_to_scrape[i:i+2]
        
        # Use a ThreadPoolExecutor with a max of 2 workers to respect the API limit
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            # Submit tasks for the current batch and collect results
            future_to_site = {executor.submit(scrape_single_site, site): site for site in batch}
            
            # Wait for all tasks in the batch to complete
            for future in concurrent.futures.as_completed(future_to_site):
                site_name, payload = future.result()
                out[site_name] = payload
            
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

    # Define site colors
    SITE_COLORS = {
        "Adzuna": "#FF6B6B",
        "CWJobs": "#4F46E5",
        "TotalJobs": "#10B981",
        "Hays": "#F59E0B",
        "Indeed": "#2563EB",
        "Reed": "#8B5CF6",
        "CVLibrary": "#F43F5E",
        "Breakroom": "#F53F5E"
    }

    for tab, (site, payload) in zip(tabs, data.items()):
        with tab:
            # Use the site's color for the CTA button
            accent = SITE_COLORS.get(site, "#1a73e8")
            
            # Make the link a prominent button-like CTA
            st.markdown(
                f"""
                <a href="{payload["url"]}" target="_blank" style="
                    display: inline-block;
                    padding: 10px 20px;
                    background-color: {accent};
                    color: white;
                    text-decoration: none;
                    font-weight: bold;
                    border-radius: 8px;
                    text-align: center;
                    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                    transition: all 0.2s ease-in-out;
                    margin-bottom: 20px;
                " onmouseover="this.style.backgroundColor='darken({accent}, 10%)'; this.style.boxShadow='0 6px 8px rgba(0,0,0,0.15)'" onmouseout="this.style.backgroundColor='{accent}'; this.style.boxShadow='0 4px 6px rgba(0,0,0,0.1)'">
                    🔗 View on {site}
                </a>
                """,
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

            # Create two columns for the job cards
            col1, col2 = st.columns(2)

            # Job cards with site-based color accents
            for i, j in enumerate(jobs):
                title = j.get("job_title") or "Unknown title"
                company = j.get("company_name") or "Unknown company"
                location = j.get("location") or "Unknown location"
                
                accent = SITE_COLORS.get(site, "#1f2937")  # default dark gray

                card_html = f"""
                <div style="
                    padding:20px; 
                    margin:12px 0; 
                    border-radius:15px; 
                    border:1px solid {accent}; 
                    background: linear-gradient(90deg, #fdfdfd, #f7f9fc);
                    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
                    transition: transform 0.2s;
                " onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
                    <h4 style="margin:0; color:{accent}; font-weight:700;">{i + 1}. {title}</h4>
                    <p style="margin:4px 0 0; color:#4b5563;">
                        <span style="margin-right:6px;">🏢</span> Company: {company}
                    </p>
                    <p style="margin:2px 0 0; color:#6b7280;">
                        <span style="margin-right:6px;">📍</span> Location: {location}
                    </p>
                </div>
                """
                
                # Alternate between columns
                if i % 2 == 0:
                    col1.markdown(card_html, unsafe_allow_html=True)
                else:
                    col2.markdown(card_html, unsafe_allow_html=True)


    st.divider()
    st.caption("✨ Demo dashboard built with Streamlit, aggregating top jobs for you")