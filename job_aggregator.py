#!/usr/bin/env python3
"""
Job Aggregation Script - Direct URL Version
Extracts real job URLs from multiple sources for direct application
"""

import requests
from bs4 import BeautifulSoup
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import csv
import re
import sys
import time
from typing import List, Optional, Set
import argparse
import random
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Emoji output crashes on cp1252 consoles and when output is redirected to a file
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Central configuration for the job aggregator."""

    # Adzuna API credentials (loaded from .env file)
    ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "YOUR_APP_ID_HERE")
    ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "YOUR_APP_KEY_HERE")

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    ]

    REQUEST_TIMEOUT = 15
    REQUEST_DELAY = 2
    MAX_RESULTS = 50
    LOCATION = os.getenv("DEFAULT_LOCATION", "India")
    OUTPUT_DIR = "job_results"

    # Roles searched when none are given on the command line (DEFAULT_ROLES in .env, comma-separated)
    DEFAULT_ROLES = [r.strip() for r in os.getenv("DEFAULT_ROLES", "").split(",") if r.strip()] \
        or ["Backend Developer", "Backend Engineer", "Backend Intern"]
    DEFAULT_DAYS = 7

    # Your skills, used to rank results (MY_SKILLS in .env, comma-separated;
    # aliases separated by "|", e.g. "Node.js|NodeJS")
    MY_SKILLS = [s.strip() for s in os.getenv("MY_SKILLS", "").split(",") if s.strip()]

    # Stacks that push a job to the bottom when its title names one you don't list
    OTHER_STACKS = [
        "java", "spring boot", ".net", "dot net", "c#", "php", "laravel", "golang",
        "ruby", "rails", "salesforce", "sap", "kotlin", "scala", "wordpress",
    ]

    # Entry-level filter (--level entry): drop senior titles and postings
    # that ask for more than MAX_EXPERIENCE_YEARS of experience
    SENIOR_TITLE_PATTERN = r"\b(senior|sr|lead|principal|staff|manager|architect|head|director|vp|iii|iv)\b"
    MAX_EXPERIENCE_YEARS = 1

    # Titles dropped when searching backend roles (override with --exclude)
    BACKEND_EXCLUDE_KEYWORDS = [
        "frontend", "front end", "front-end", "ui", "ux", "designer", "android", "ios",
        "flutter", "react native", "qa", "tester", "sales", "marketing", "seo",
        "content", "hr", "recruiter", "graphic",
        # Internshala's "backend executive" listings are back-office, not software
        "executive", "operations", "talent acquisition", "business development",
    ]


# ============================================================================
# DATA MODELS
# ============================================================================

class JobPosting:
    """Represents a single job posting."""

    # "Intern", "Internship", "Python_Intern" but not "International" / "Internal"
    INTERN_PATTERN = re.compile(r"(?<![a-z])intern(?:ship)?s?(?![a-z])", re.IGNORECASE)

    def __init__(self, title: str, company: str, url: str,
                 source: str, posted_date: str = None, location: str = None,
                 description: str = None, job_type: str = None,
                 pay: str = None, experience: str = None, skills: List[str] = None):
        self.title = title
        self.company = company
        self.url = url
        self.source = source
        self.posted_date = posted_date
        self.location = location
        self.description = description
        self.job_type = job_type or ("Internship" if self.INTERN_PATTERN.search(title) else "Job")
        self.pay = pay
        self.experience = experience
        self.skills = skills or []
        self.matched_skills: List[str] = []  # Filled in by SkillMatcher
        self.stack_mismatch: List[str] = []
        self.timestamp = datetime.now()

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        return isinstance(other, JobPosting) and self.url == other.url


# ============================================================================
# UTILITIES
# ============================================================================

class DateParser:
    """Parse and validate job posting dates."""

    UNIT_HOURS = [('minute', 0), ('hour', 1), ('day', 24), ('week', 24 * 7), ('month', 24 * 30)]

    @staticmethod
    def is_recent(date_str: str, hours: int = 72) -> bool:
        """Check if a relative date like '3 days ago' or '1 week ago' falls within `hours`."""
        if not date_str:
            return True

        date_str = date_str.lower().strip()

        recent_keywords = ['just posted', 'today', 'active', 'just now', 'new', 'few hours', 'early applicant']
        if any(kw in date_str for kw in recent_keywords):
            return True

        match = re.search(r'(\d+)', date_str)
        count = int(match.group(1)) if match else 1  # "a week ago"

        for unit, unit_hours in DateParser.UNIT_HOURS:
            if unit in date_str:
                return count * unit_hours <= hours

        return True


class ExperienceParser:
    """Extract the minimum years of experience a posting asks for."""

    # Matches "2 years", "3+ yrs", "2-3 years", "1 to 3 years", "1 year(s)"
    YEARS_PATTERN = re.compile(
        r"(\d+)\s*\+?\s*(?:(?:-|–|to)\s*\d+\s*\+?\s*)?(?:years?|yrs?)", re.IGNORECASE
    )
    # Matches "Experience: 5" where the unit is left out
    LABEL_PATTERN = re.compile(r"experience\s*(?:required)?\s*[:\-–]\s*(\d+)", re.IGNORECASE)

    @classmethod
    def min_years(cls, text: str, require_context: bool = True) -> Optional[int]:
        """
        Return the smallest experience requirement found in `text`.
        With require_context, a match only counts if "exp" appears nearby,
        so phrases like "founded 10 years ago" are ignored.
        """
        if not text:
            return None

        found = []
        for match in cls.YEARS_PATTERN.finditer(text):
            window = text[max(0, match.start() - 40):match.end() + 40].lower()
            if not require_context or 'exp' in window:
                found.append(int(match.group(1)))
        found.extend(int(match.group(1)) for match in cls.LABEL_PATTERN.finditer(text))

        return min(found) if found else None


class JobFilter:
    """Drop postings that don't fit the search: too senior, off-role, unpaid or too old."""

    def __init__(self, config: Config, days: int, entry_level: bool = True,
                 exclude_keywords: List[str] = None, paid_only: bool = False):
        self.config = config
        self.max_hours = days * 24
        self.entry_level = entry_level
        self.paid_only = paid_only
        self.senior_pattern = re.compile(config.SENIOR_TITLE_PATTERN, re.IGNORECASE)
        self.exclude_pattern = None
        if exclude_keywords:
            self.exclude_pattern = re.compile(
                r"\b(" + "|".join(re.escape(kw) for kw in exclude_keywords) + r")\b",
                re.IGNORECASE
            )

    def reason_to_skip(self, job: JobPosting) -> Optional[str]:
        """Return why a job should be skipped, or None to keep it."""
        if self.entry_level:
            if self.senior_pattern.search(job.title):
                return 'senior title'

            if job.experience:
                years = ExperienceParser.min_years(job.experience, require_context=False)
            else:
                years = ExperienceParser.min_years(job.description)
            if years is not None and years > self.config.MAX_EXPERIENCE_YEARS:
                return f'needs {self.config.MAX_EXPERIENCE_YEARS + 1}+ yrs'

        if self.exclude_pattern and self.exclude_pattern.search(job.title):
            return 'off-role title'

        if self.paid_only and job.pay and job.pay.lower().startswith('unpaid'):
            return 'unpaid'

        if not DateParser.is_recent(job.posted_date, hours=self.max_hours):
            return 'too old'

        return None


class SkillMatcher:
    """Rank postings by how many of your skills they mention."""

    def __init__(self, skills: List[str], other_stacks: List[str]):
        # Each skill entry may carry aliases: "Node.js|NodeJS" counts once as "Node.js"
        self.skills = []
        known = set()
        for entry in skills:
            aliases = [a.strip() for a in entry.split('|') if a.strip()]
            self.skills.append((aliases[0], self._pattern(aliases)))
            known.update(a.lower() for a in aliases)
        self.other_stacks = [(s, self._pattern([s])) for s in other_stacks if s not in known]

    @staticmethod
    def _pattern(terms: List[str]):
        # Lookarounds instead of \b so terms like "C++", ".NET" and "Node.js" match
        return re.compile(r"(?<!\w)(" + "|".join(re.escape(t) for t in terms) + r")(?!\w)", re.IGNORECASE)

    def score(self, job: JobPosting):
        """Fill in job.matched_skills and job.stack_mismatch."""
        text = " ".join(filter(None, [job.title, job.description, " ".join(job.skills)]))
        job.matched_skills = [name for name, pattern in self.skills if pattern.search(text)]

        # "Java Developer" is a mismatch; "Java/Python Developer" isn't, since it names one of yours
        if not any(pattern.search(job.title) for _, pattern in self.skills):
            job.stack_mismatch = [name for name, pattern in self.other_stacks if pattern.search(job.title)]

    @staticmethod
    def sort_key(job: JobPosting):
        """Best matches first, titles built on other stacks last."""
        return (bool(job.stack_mismatch), -len(job.matched_skills))


class Deduplicator:
    """Handle duplicate detection and removal."""

    def __init__(self):
        self.seen_urls: Set[str] = set()
        self.seen_titles: Set[str] = set()

    def is_duplicate(self, job: JobPosting) -> bool:
        """Check if a job is a duplicate."""
        # Normalize URL for comparison
        url_clean = job.url.split('?')[0].lower()

        if url_clean in self.seen_urls:
            return True

        signature = f"{job.title.lower()}|{job.company.lower()}"
        if signature in self.seen_titles:
            return True

        return False

    def add(self, job: JobPosting):
        """Mark a job as seen."""
        url_clean = job.url.split('?')[0].lower()
        self.seen_urls.add(url_clean)
        signature = f"{job.title.lower()}|{job.company.lower()}"
        self.seen_titles.add(signature)


# ============================================================================
# SCRAPERS WITH DIRECT URLS
# ============================================================================

class AdzunaAPIScraper:
    """Search jobs via the Adzuna API."""

    name = "Adzuna"

    def __init__(self, config: Config, entry_level: bool = True):
        self.config = config
        self.app_id = config.ADZUNA_APP_ID
        self.app_key = config.ADZUNA_APP_KEY
        self.entry_level = entry_level

    def scrape(self, role: str, location: str, days: int) -> List[JobPosting]:
        """Search jobs via Adzuna API."""

        if self.app_id == "YOUR_APP_ID_HERE" or self.app_key == "YOUR_APP_KEY_HERE":
            print(f"\n⚠️  Adzuna API not configured. Skipping...")
            print(f"   Get FREE API key at: https://developer.adzuna.com/overview")
            return []

        print(f"\n🔍 Searching Adzuna API for '{role}' in {location}...")

        base_url = "https://api.adzuna.com/v1/api/jobs/in/search/1"

        params = {
            'app_id': self.app_id,
            'app_key': self.app_key,
            'results_per_page': self.config.MAX_RESULTS,
            'what': role,
            'where': location,
            'category': 'it-jobs',
            'sort_by': 'date',
            'max_days_old': days
        }
        if self.entry_level:
            # Let Adzuna drop senior postings so the result page isn't spent on them
            params['what_exclude'] = 'senior lead principal manager architect'

        try:
            response = requests.get(base_url, params=params, timeout=self.config.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"   ❌ Error fetching Adzuna: {e}")
            return []

        jobs = []
        results = data.get('results', [])
        print(f"   Adzuna: found {len(results)} listings for '{role}'")

        for item in results:
            try:
                title = item.get('title', 'Unknown')
                company = item.get('company', {}).get('display_name', 'Unknown')
                job_location = item.get('location', {}).get('display_name', 'India')

                # The redirect_url always lands on this Adzuna details page, which
                # links out to the employer, so build it directly instead of following redirects
                job_url = f"https://www.adzuna.in/details/{item['id']}"

                created = item.get('created', '')
                if created:
                    posted_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
                    posted_str = f"{(datetime.now(posted_date.tzinfo) - posted_date).days} days ago"
                else:
                    posted_str = "Recently"

                pay = None
                if item.get('salary_min') and str(item.get('salary_is_predicted')) != '1':
                    pay = f"₹{int(item['salary_min']):,} - ₹{int(item.get('salary_max') or item['salary_min']):,} /year"

                jobs.append(JobPosting(
                    title=title,
                    company=company,
                    url=job_url,
                    source="Adzuna",
                    posted_date=posted_str,
                    location=job_location,
                    description=item.get('description', ''),
                    pay=pay
                ))

            except Exception:
                continue

        return jobs


class LinkedInDirectScraper:
    """Scrape LinkedIn directly for job URLs."""

    name = "LinkedIn"

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()

    def scrape(self, role: str, location: str, days: int) -> List[JobPosting]:
        """Search LinkedIn for jobs."""
        print(f"\n🔍 Searching LinkedIn for '{role}' in {location}...")

        headers = {
            'User-Agent': random.choice(self.config.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

        # LinkedIn ignores the experience-level filter (f_E) for logged-out
        # requests, so seniority is filtered locally by JobFilter instead
        base_url = "https://www.linkedin.com/jobs/search"
        params = {
            'keywords': role,
            'location': location,
            'f_TPR': f'r{days * 86400}',  # Posted within the last `days` days
        }

        try:
            response = self.session.get(base_url, params=params, headers=headers,
                                        timeout=self.config.REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            jobs = []

            # LinkedIn job cards
            job_cards = soup.find_all('div', class_='base-card')

            if not job_cards:
                job_cards = soup.find_all('div', attrs={'data-entity-urn': True})

            print(f"   LinkedIn: found {len(job_cards)} listings for '{role}'")

            for card in job_cards[:self.config.MAX_RESULTS]:
                try:
                    # Extract title and URL
                    title_elem = card.find('h3', class_='base-search-card__title')
                    if not title_elem:
                        title_elem = card.find('a', class_='base-card__full-link')

                    if not title_elem:
                        continue

                    link = card.find('a', href=True)
                    if not link:
                        continue

                    job_url = link['href']
                    if not job_url.startswith('http'):
                        job_url = 'https://www.linkedin.com' + job_url

                    # Clean URL (remove tracking params)
                    job_url = job_url.split('?')[0]

                    title = title_elem.get_text(strip=True)

                    # Extract company
                    company_elem = card.find('h4', class_='base-search-card__subtitle')
                    company = company_elem.get_text(strip=True) if company_elem else "Unknown"

                    # Extract location
                    loc_elem = card.find('span', class_='job-search-card__location')
                    job_location = loc_elem.get_text(strip=True) if loc_elem else location

                    # Extract date
                    date_elem = card.find('time')
                    posted_date = date_elem.get_text(strip=True) if date_elem else "Recently"

                    job = JobPosting(
                        title=title,
                        company=company,
                        url=job_url,
                        source="LinkedIn",
                        posted_date=posted_date,
                        location=job_location
                    )

                    jobs.append(job)

                except Exception:
                    continue

            return jobs

        except Exception as e:
            print(f"   ❌ Error fetching LinkedIn: {e}")
            return []


class InternshalaScraper:
    """Scrape Internshala for internships and fresher jobs (India)."""

    name = "Internshala"
    BASE_URL = "https://internshala.com"

    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()

    def scrape(self, role: str, location: str, days: int) -> List[JobPosting]:
        """Search Internshala internship and job listings by keyword."""
        print(f"\n🔍 Searching Internshala for '{role}' in {location}...")

        headers = {
            'User-Agent': random.choice(self.config.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        keyword_slug = re.sub(r'[^a-z0-9]+', '-', role.lower()).strip('-')
        # Internshala search isn't location-scoped by keyword URL, so filter by city locally
        city = None if location.lower() == 'india' else location.lower()

        jobs = []
        for kind in ('internships', 'jobs'):
            url = f"{self.BASE_URL}/{kind}/keywords-{keyword_slug}/"

            try:
                response = self.session.get(url, headers=headers, timeout=self.config.REQUEST_TIMEOUT)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"   ❌ Error fetching Internshala {kind}: {e}")
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.select('div.individual_internship[internshipid]')
            print(f"   Internshala: found {len(cards)} {kind} listings for '{role}'")

            for card in cards[:self.config.MAX_RESULTS]:
                try:
                    job = self._parse_card(card)
                except Exception:
                    continue

                if not job:
                    continue

                if city and city not in job.location.lower() and 'work from home' not in job.location.lower():
                    continue

                jobs.append(job)

            time.sleep(self.config.REQUEST_DELAY)

        return jobs

    def _parse_card(self, card) -> Optional[JobPosting]:
        """Turn one Internshala listing card into a JobPosting."""
        title_elem = card.select_one('a.job-title-href')
        if not title_elem:
            return None

        company_elem = card.select_one('p.company-name')
        locations = [a.get_text(strip=True) for a in card.select('.locations a')]

        # Internships show a stipend, jobs show a salary (desktop + mobile variants)
        pay_elem = card.select_one('.stipend') or card.select_one('.detail-row-1 .desktop')
        pay = pay_elem.get_text(' ', strip=True) if pay_elem else None

        duration_icon = card.select_one('.detail-row-1 .ic-16-calendar')
        if pay and duration_icon:
            pay = f"{pay} ({duration_icon.find_next('span').get_text(strip=True)})"

        experience_icon = card.select_one('.detail-row-1 .ic-16-briefcase')
        experience = experience_icon.find_next('span').get_text(strip=True) if experience_icon else None

        posted_elem = card.select_one('.color-labels span')
        about_elem = card.select_one('.about_job .text')
        skills = [s.get_text(strip=True) for s in card.select('.job_skill')]

        return JobPosting(
            title=title_elem.get_text(strip=True),
            company=company_elem.get_text(strip=True) if company_elem else "Unknown",
            url=self.BASE_URL + card.get('data-href', title_elem['href']),
            source="Internshala",
            posted_date=posted_elem.get_text(strip=True) if posted_elem else None,
            location=", ".join(locations) or None,
            description=about_elem.get_text(' ', strip=True) if about_elem else None,
            job_type="Internship" if card.get('employment_type') == 'internship' else "Job",
            pay=pay,
            experience=experience,
            skills=skills
        )


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

class OutputFormatter:
    """Handle output file generation."""

    CSV_COLUMNS = ['Title', 'Company', 'Type', 'Location', 'Pay', 'Experience',
                   'Posted', 'Source', 'Skills Match', 'URL', 'Status']

    @staticmethod
    def describe_match(job: JobPosting) -> str:
        """e.g. 'python, postgresql' or 'other stack: java'."""
        if job.stack_mismatch:
            return "other stack: " + ", ".join(job.stack_mismatch)
        return ", ".join(job.matched_skills)

    @staticmethod
    def write_to_file(jobs: List[JobPosting], filename: str):
        """Write jobs to a text file with DIRECT URLs."""
        # Only create parent directory when a directory component is present.
        dirpath = os.path.dirname(filename)
        if dirpath:
            os.makedirs(dirpath, exist_ok=True)

        with open(filename, 'w', encoding='utf-8') as f:
            f.write("=" * 80 + "\n")
            f.write(f"JOB SEARCH RESULTS - DIRECT APPLICATION LINKS\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total Jobs Found: {len(jobs)}\n")
            f.write("=" * 80 + "\n\n")

            jobs_by_source = {}
            for job in jobs:
                source = job.source
                if source not in jobs_by_source:
                    jobs_by_source[source] = []
                jobs_by_source[source].append(job)

            for source, source_jobs in sorted(jobs_by_source.items()):
                f.write(f"\n{'─' * 80}\n")
                f.write(f"SOURCE: {source} ({len(source_jobs)} jobs)\n")
                f.write(f"{'─' * 80}\n\n")

                for i, job in enumerate(source_jobs, 1):
                    f.write(f"{i}. {job.title}  [{job.job_type}]\n")
                    f.write(f"   Company: {job.company}\n")
                    if job.location:
                        f.write(f"   Location: {job.location}\n")
                    if job.pay:
                        f.write(f"   Pay: {job.pay}\n")
                    if job.experience:
                        f.write(f"   Experience: {job.experience}\n")
                    if job.posted_date:
                        f.write(f"   Posted: {job.posted_date}\n")
                    if job.matched_skills or job.stack_mismatch:
                        f.write(f"   Skills Match: {OutputFormatter.describe_match(job)}\n")
                    f.write(f"   DIRECT URL: {job.url}\n")
                    if job.description:
                        f.write(f"   Preview: {job.description[:200]}...\n")
                    f.write("\n")

            f.write("\n" + "=" * 80 + "\n")
            f.write(f"✅ All URLs are DIRECT links - click to apply!\n")
            f.write("=" * 80 + "\n")

        print(f"\n✅ Results saved to: {filename}")

    @staticmethod
    def write_csv(jobs: List[JobPosting], filename: str):
        """Write jobs to a CSV with a blank Status column for tracking applications."""
        # utf-8-sig so Excel shows ₹ and other non-ASCII text correctly
        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(OutputFormatter.CSV_COLUMNS)
            for job in jobs:
                writer.writerow([job.title, job.company, job.job_type, job.location or '',
                                 job.pay or '', job.experience or '', job.posted_date or '',
                                 job.source, OutputFormatter.describe_match(job), job.url, ''])

        print(f"✅ Tracking sheet saved to: {filename}")


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

class JobAggregator:
    """Main orchestrator for job aggregation."""

    def __init__(self, config: Config = None, days: int = None, entry_level: bool = True,
                 exclude_keywords: List[str] = None, paid_only: bool = False,
                 skills: List[str] = None):
        self.config = config or Config()
        self.days = days or self.config.DEFAULT_DAYS
        self.entry_level = entry_level
        self.scrapers = [
            AdzunaAPIScraper(self.config, entry_level),
            LinkedInDirectScraper(self.config),
            InternshalaScraper(self.config)
        ]
        self.deduplicator = Deduplicator()
        self.job_filter = JobFilter(self.config, self.days, entry_level, exclude_keywords, paid_only)
        self.skill_matcher = SkillMatcher(skills, self.config.OTHER_STACKS) if skills else None

    def _run_scraper(self, scraper, roles: List[str], location: str) -> List[JobPosting]:
        """Run one source over every role, pausing between requests to the same site."""
        jobs = []
        for i, role in enumerate(roles):
            if i:
                time.sleep(self.config.REQUEST_DELAY)
            try:
                jobs.extend(scraper.scrape(role, location, self.days))
            except Exception as e:
                print(f"   ❌ Error with {scraper.name} for '{role}': {e}")
        return jobs

    def aggregate(self, roles: List[str], location: str = None) -> List[JobPosting]:
        """Aggregate jobs with DIRECT URLs from all sources."""
        location = location or self.config.LOCATION
        all_jobs = []
        skipped = Counter()

        print(f"\n{'=' * 80}")
        print(f"🚀 Starting Job Aggregation - Getting DIRECT URLs")
        print(f"{'=' * 80}")
        print(f"Roles: {', '.join(roles)}")
        print(f"Location: {location}")
        print(f"Time Filter: Last {self.days} days")
        print(f"Level: {'Entry level / internships' if self.entry_level else 'Any'}")

        # Sources are different sites, so query them in parallel; each source
        # still walks its roles one at a time with a delay
        with ThreadPoolExecutor(max_workers=len(self.scrapers)) as executor:
            futures = [executor.submit(self._run_scraper, scraper, roles, location)
                       for scraper in self.scrapers]
            results = [future.result() for future in futures]

        print(f"\n{'─' * 80}")
        for scraper, jobs in zip(self.scrapers, results):
            kept = 0
            for job in jobs:
                if self.deduplicator.is_duplicate(job):
                    skipped['duplicate'] += 1
                    continue
                self.deduplicator.add(job)

                reason = self.job_filter.reason_to_skip(job)
                if reason:
                    skipped[reason] += 1
                    continue

                all_jobs.append(job)
                kept += 1

            print(f"   ✓ {scraper.name}: kept {kept} of {len(jobs)} listings")

        if self.skill_matcher:
            for job in all_jobs:
                self.skill_matcher.score(job)
            all_jobs.sort(key=SkillMatcher.sort_key)

        print(f"\n📊 Summary: Found {len(all_jobs)} unique jobs with DIRECT URLs")
        if self.skill_matcher:
            strong = sum(1 for job in all_jobs if len(job.matched_skills) >= 2 and not job.stack_mismatch)
            print(f"   {strong} match 2+ of your skills (listed first in the output)")
        if skipped:
            print(f"   Skipped: " + ", ".join(f"{count} {reason}" for reason, count in skipped.most_common()))
        print(f"{'─' * 80}")

        return all_jobs

    def run(self, roles: List[str], location: str = None, output_file: str = None):
        """Run the complete aggregation pipeline."""
        jobs = self.aggregate(roles, location)

        if not jobs:
            print("\n⚠️  No jobs found. Try:")
            print("   • Set up Adzuna API: https://developer.adzuna.com/overview")
            print("   • Use broader search terms or a longer --days window")
            print("   • Try 'India' as location instead of specific city")
            return

        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_role = re.sub(r'[^\w\s-]', '', roles[0]).strip().replace(' ', '_')
            if len(roles) > 1:
                safe_role += f"_and_{len(roles) - 1}_more"
            filename = f"{self.config.OUTPUT_DIR}/{timestamp}_{safe_role}_jobs.txt"
        else:
            filename = output_file

        OutputFormatter.write_to_file(jobs, filename)
        OutputFormatter.write_csv(jobs, os.path.splitext(filename)[0] + '.csv')

        print(f"\n{'=' * 80}")
        print(f"✨ Job Aggregation Complete - All Direct URLs!")
        print(f"{'=' * 80}")


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """Command-line interface for the job aggregator."""
    parser = argparse.ArgumentParser(
        description='Aggregate job postings with DIRECT application URLs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python job_aggregator.py                      # Backend jobs + internships, entry level
  python job_aggregator.py "Backend Developer" "Django Developer"
  python job_aggregator.py "Python Developer" --location "Delhi" --paid-only
  python job_aggregator.py "Backend Developer" --level any --days 3
  python job_aggregator.py "Full Stack" --output my_jobs.txt

Setup Adzuna API (recommended):
  1. Sign up at: https://developer.adzuna.com/overview
  2. Get your APP_ID and APP_KEY from dashboard
  3. Add ADZUNA_APP_ID and ADZUNA_APP_KEY to the .env file
        """
    )

    parser.add_argument(
        'roles',
        type=str,
        nargs='*',
        help=f'Job roles to search for (default: {", ".join(Config.DEFAULT_ROLES)})'
    )

    parser.add_argument(
        '--location',
        type=str,
        default=None,
        help='Location to search in (default: India)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=None,
        help='Custom output filename (a .csv is written alongside it)'
    )

    parser.add_argument(
        '--days',
        type=int,
        default=Config.DEFAULT_DAYS,
        help=f'Only include jobs posted in the last N days (default: {Config.DEFAULT_DAYS})'
    )

    parser.add_argument(
        '--level',
        choices=['entry', 'any'],
        default='entry',
        help='entry: internships and fresher/junior roles only (default); any: no seniority filter'
    )

    parser.add_argument(
        '--exclude',
        type=str,
        default=None,
        help='Comma-separated title keywords to drop (default for backend roles: frontend, ui, android, ...)'
    )

    parser.add_argument(
        '--paid-only',
        action='store_true',
        help='Skip unpaid internships'
    )

    parser.add_argument(
        '--skills',
        type=str,
        default=None,
        help='Comma-separated skills to rank results by (default: MY_SKILLS from .env)'
    )

    args = parser.parse_args()

    roles = args.roles or Config.DEFAULT_ROLES

    if args.exclude is not None:
        exclude_keywords = [kw.strip() for kw in args.exclude.split(',') if kw.strip()]
    elif any(re.search(r'back[\s-]?end', role, re.IGNORECASE) for role in roles):
        exclude_keywords = Config.BACKEND_EXCLUDE_KEYWORDS
    else:
        exclude_keywords = []

    if args.skills is not None:
        skills = [s.strip() for s in args.skills.split(',') if s.strip()]
    else:
        skills = Config.MY_SKILLS

    aggregator = JobAggregator(
        days=args.days,
        entry_level=args.level == 'entry',
        exclude_keywords=exclude_keywords,
        paid_only=args.paid_only,
        skills=skills
    )
    aggregator.run(
        roles=roles,
        location=args.location,
        output_file=args.output
    )


if __name__ == '__main__':
    main()
