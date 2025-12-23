#!/usr/bin/env python3
"""
Job Aggregation Script - Direct URL Version
Extracts real job URLs from multiple sources for direct application
"""

import requests
from datetime import datetime, timedelta
import re
import time
from typing import List, Set
import argparse
import random
from urllib.parse import urlparse, parse_qs
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


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


# ============================================================================
# DATA MODELS
# ============================================================================

class JobPosting:
    """Represents a single job posting."""
    
    def __init__(self, title: str, company: str, url: str, 
                 source: str, posted_date: str = None, location: str = None,
                 description: str = None):
        self.title = title
        self.company = company
        self.url = url  # Keep original URL (will be real URL now)
        self.source = source
        self.posted_date = posted_date
        self.location = location
        self.description = description
        self.timestamp = datetime.now()
    
    def __hash__(self):
        return hash(self.url)
    
    def __eq__(self, other):
        return isinstance(other, JobPosting) and self.url == other.url


# ============================================================================
# UTILITIES
# ============================================================================

class URLResolver:
    """Resolve redirect URLs to get actual job posting URLs."""
    
    @staticmethod
    def resolve_adzuna_redirect(adzuna_url: str, timeout: int = 10) -> str:
        """
        Follow Adzuna redirect to get the actual job URL.
        Example: https://www.adzuna.in/land/ad/12345 -> https://linkedin.com/jobs/view/...
        """
        try:
            response = requests.get(
                adzuna_url, 
                timeout=timeout, 
                allow_redirects=True,
                headers={'User-Agent': Config.USER_AGENTS[0]}
            )
            # Get final URL after all redirects
            final_url = response.url
            
            # Clean up tracking parameters
            if 'linkedin.com' in final_url:
                # Keep only essential parts
                parsed = urlparse(final_url)
                clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                return clean_url
            
            return final_url
            
        except Exception as e:
            # If redirect fails, return original URL
            return adzuna_url
    
    @staticmethod
    def identify_source(url: str) -> str:
        """Identify job source from URL."""
        domain = urlparse(url).netloc.lower()
        
        if 'linkedin.com' in domain:
            return 'LinkedIn'
        elif 'naukri.com' in domain:
            return 'Naukri'
        elif 'indeed.com' in domain:
            return 'Indeed'
        elif 'internshala.com' in domain:
            return 'Internshala'
        elif 'instahyre.com' in domain:
            return 'Instahyre'
        elif 'shine.com' in domain:
            return 'Shine'
        elif 'timesjobs.com' in domain:
            return 'TimesJobs'
        elif 'foundit.in' in domain or 'monsterindia.com' in domain:
            return 'Foundit'
        else:
            return 'Other'


class DateParser:
    """Parse and validate job posting dates."""
    
    @staticmethod
    def is_recent(date_str: str, hours: int = 72) -> bool:
        """Check if recent (72 hours for better results)."""
        if not date_str:
            return True
        
        date_str = date_str.lower().strip()
        
        recent_keywords = ['just posted', 'today', 'active', 'just now', 'new', '1 day', '2 days']
        if any(kw in date_str for kw in recent_keywords):
            return True
        
        if 'hour' in date_str:
            match = re.search(r'(\d+)', date_str)
            if match:
                return int(match.group(1)) <= hours
            return True
        
        if 'minute' in date_str:
            return True
        
        if 'day' in date_str:
            match = re.search(r'(\d+)', date_str)
            if match:
                return int(match.group(1)) * 24 <= hours
            return True
        
        return True


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
    """Use Adzuna API and resolve to real URLs."""
    
    def __init__(self, config: Config):
        self.config = config
        self.app_id = config.ADZUNA_APP_ID
        self.app_key = config.ADZUNA_APP_KEY
    
    def scrape(self, role: str, location: str) -> List[JobPosting]:
        """Search jobs via Adzuna API and resolve to real URLs."""
        
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
            'sort_by': 'date',
            'max_days_old': 3
        }
        
        try:
            response = requests.get(base_url, params=params, timeout=self.config.REQUEST_TIMEOUT)
            response.raise_for_status()
            data = response.json()
            
            jobs = []
            results = data.get('results', [])
            
            print(f"   Found {len(results)} job listings")
            print(f"   Resolving to direct URLs (this may take a moment)...")
            
            for i, item in enumerate(results, 1):
                try:
                    title = item.get('title', 'Unknown')
                    company = item.get('company', {}).get('display_name', 'Unknown')
                    adzuna_url = item.get('redirect_url', '')
                    location_obj = item.get('location', {})
                    job_location = location_obj.get('display_name', 'India')
                    description = item.get('description', '')[:200]
                    
                    # Parse date
                    created = item.get('created', '')
                    if created:
                        posted_date = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        posted_str = f"{(datetime.now(posted_date.tzinfo) - posted_date).days} days ago"
                    else:
                        posted_str = "Recently"
                    
                    # KEY CHANGE: Resolve Adzuna redirect to get real URL
                    print(f"   [{i}/{len(results)}] Resolving URL...", end='\r')
                    real_url = URLResolver.resolve_adzuna_redirect(adzuna_url)
                    
                    # Identify actual source from resolved URL
                    actual_source = URLResolver.identify_source(real_url)
                    
                    job = JobPosting(
                        title=title,
                        company=company,
                        url=real_url,  # Now using REAL URL!
                        source=actual_source,  # Now shows LinkedIn, Naukri, etc.
                        posted_date=posted_str,
                        location=job_location,
                        description=description
                    )
                    
                    jobs.append(job)
                    
                    # Small delay to avoid overwhelming servers
                    time.sleep(0.5)
                    
                except Exception as e:
                    continue
            
            print(f"\n   ✓ Resolved {len(jobs)} direct URLs")
            return jobs
            
        except requests.RequestException as e:
            print(f"   ❌ Error fetching Adzuna: {e}")
            return []


class LinkedInDirectScraper:
    """Scrape LinkedIn directly for job URLs."""
    
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
    
    def scrape(self, role: str, location: str) -> List[JobPosting]:
        """Search LinkedIn for jobs."""
        print(f"\n🔍 Searching LinkedIn for '{role}' in {location}...")
        
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': random.choice(self.config.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        # LinkedIn job search URL
        base_url = "https://www.linkedin.com/jobs/search"
        params = {
            'keywords': role,
            'location': location,
            'f_TPR': 'r86400',  # Last 24 hours
            'position': '1',
            'pageNum': '0'
        }
        
        try:
            # Build URL
            url = f"{base_url}?keywords={role.replace(' ', '%20')}&location={location.replace(' ', '%20')}&f_TPR=r86400"
            
            response = self.session.get(url, headers=headers, timeout=self.config.REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            jobs = []
            
            # LinkedIn job cards
            job_cards = soup.find_all('div', class_='base-card')
            
            if not job_cards:
                job_cards = soup.find_all('div', attrs={'data-entity-urn': True})
            
            print(f"   Found {len(job_cards)} job listings")
            
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
                    
                except Exception as e:
                    continue
            
            return jobs
            
        except Exception as e:
            print(f"   ❌ Error fetching LinkedIn: {e}")
            return []


class NaukriDirectScraper:
    """Scrape Naukri directly for job URLs."""
    
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
    
    def scrape(self, role: str, location: str) -> List[JobPosting]:
        """Search Naukri for jobs."""
        print(f"\n🔍 Searching Naukri for '{role}' in {location}...")
        
        from bs4 import BeautifulSoup
        
        headers = {
            'User-Agent': random.choice(self.config.USER_AGENTS),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        
        role_slug = role.lower().replace(' ', '-')
        location_slug = location.lower().replace(' ', '-').split()[0]  # First word
        
        url = f"https://www.naukri.com/{role_slug}-jobs-in-{location_slug}?sort=date"
        
        try:
            response = self.session.get(url, headers=headers, timeout=self.config.REQUEST_TIMEOUT)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            jobs = []
            job_cards = soup.find_all('article', class_='jobTuple')
            
            print(f"   Found {len(job_cards)} job listings")
            
            for card in job_cards[:self.config.MAX_RESULTS]:
                try:
                    title_elem = card.find('a', class_='title')
                    if not title_elem:
                        continue
                    
                    title = title_elem.get_text(strip=True)
                    job_url = title_elem['href']
                    
                    # Ensure full URL
                    if not job_url.startswith('http'):
                        job_url = 'https://www.naukri.com' + job_url
                    
                    company_elem = card.find('a', class_='subTitle')
                    company = company_elem.get_text(strip=True) if company_elem else "Unknown"
                    
                    loc_elem = card.find('li', class_='location')
                    job_location = loc_elem.get_text(strip=True) if loc_elem else location
                    
                    date_elem = card.find('span', class_='jobTupleFooter')
                    posted_date = date_elem.get_text(strip=True) if date_elem else None
                    
                    if posted_date and not DateParser.is_recent(posted_date):
                        continue
                    
                    job = JobPosting(
                        title=title,
                        company=company,
                        url=job_url,
                        source="Naukri",
                        posted_date=posted_date,
                        location=job_location
                    )
                    
                    jobs.append(job)
                    
                except Exception as e:
                    continue
            
            return jobs
            
        except Exception as e:
            print(f"   ❌ Error fetching Naukri: {e}")
            return []


# ============================================================================
# OUTPUT FORMATTING
# ============================================================================

class OutputFormatter:
    """Handle output file generation."""
    
    @staticmethod
    def write_to_file(jobs: List[JobPosting], filename: str):
        """Write jobs to a text file with DIRECT URLs."""
        import os
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
                    f.write(f"{i}. {job.title}\n")
                    f.write(f"   Company: {job.company}\n")
                    if job.location:
                        f.write(f"   Location: {job.location}\n")
                    if job.posted_date:
                        f.write(f"   Posted: {job.posted_date}\n")
                    f.write(f"   DIRECT URL: {job.url}\n")
                    if job.description:
                        f.write(f"   Preview: {job.description}...\n")
                    f.write("\n")
            
            f.write("\n" + "=" * 80 + "\n")
            f.write(f"✅ All URLs are DIRECT links - click to apply!\n")
            f.write("=" * 80 + "\n")
        
        print(f"\n✅ Results saved to: {filename}")


# ============================================================================
# MAIN ORCHESTRATION
# ============================================================================

class JobAggregator:
    """Main orchestrator for job aggregation."""
    
    def __init__(self, config: Config = None):
        self.config = config or Config()
        self.scrapers = [
            AdzunaAPIScraper(self.config),  # Resolves to real URLs
            LinkedInDirectScraper(self.config),  # Direct LinkedIn URLs
            NaukriDirectScraper(self.config)  # Direct Naukri URLs
        ]
        self.deduplicator = Deduplicator()
    
    def aggregate(self, role: str, location: str = None) -> List[JobPosting]:
        """Aggregate jobs with DIRECT URLs from all sources."""
        location = location or self.config.LOCATION
        all_jobs = []
        
        print(f"\n{'=' * 80}")
        print(f"🚀 Starting Job Aggregation - Getting DIRECT URLs")
        print(f"{'=' * 80}")
        print(f"Role: {role}")
        print(f"Location: {location}")
        print(f"Time Filter: Last 72 hours")
        
        for scraper in self.scrapers:
            try:
                jobs = scraper.scrape(role, location)
                
                unique_jobs = []
                for job in jobs:
                    if not self.deduplicator.is_duplicate(job):
                        unique_jobs.append(job)
                        self.deduplicator.add(job)
                
                all_jobs.extend(unique_jobs)
                print(f"   ✓ Added {len(unique_jobs)} unique jobs with direct URLs")
                
                time.sleep(self.config.REQUEST_DELAY)
                
            except Exception as e:
                print(f"   ❌ Error with {scraper.__class__.__name__}: {e}")
                continue
        
        print(f"\n{'─' * 80}")
        print(f"📊 Summary: Found {len(all_jobs)} unique jobs with DIRECT URLs")
        print(f"{'─' * 80}")
        
        return all_jobs
    
    def run(self, role: str, location: str = None, output_file: str = None):
        """Run the complete aggregation pipeline."""
        jobs = self.aggregate(role, location)
        
        if not jobs:
            print("\n⚠️  No jobs found. Try:")
            print("   • Set up Adzuna API: https://developer.adzuna.com/overview")
            print("   • Use broader search terms")
            print("   • Try 'India' as location instead of specific city")
            return
        
        if not output_file:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_role = re.sub(r'[^\w\s-]', '', role).strip().replace(' ', '_')
            filename = f"{self.config.OUTPUT_DIR}/{timestamp}_{safe_role}_jobs.txt"
        else:
            filename = output_file
        
        OutputFormatter.write_to_file(jobs, filename)
        
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
  python job_aggregator.py "Backend Developer"
  python job_aggregator.py "Python Developer" --location "Delhi"
  python job_aggregator.py "Full Stack" --output my_jobs.txt

Setup Adzuna API (recommended):
  1. Sign up at: https://developer.adzuna.com/overview
  2. Get your APP_ID and APP_KEY from dashboard
  3. Edit lines 35-36 in this script with your credentials
        """
    )
    
    parser.add_argument(
        'role',
        type=str,
        help='Job role to search for (e.g., "Backend Developer")'
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
        help='Custom output filename'
    )
    
    args = parser.parse_args()
    
    aggregator = JobAggregator()
    aggregator.run(
        role=args.role,
        location=args.location,
        output_file=args.output
    )


if __name__ == '__main__':
    main()