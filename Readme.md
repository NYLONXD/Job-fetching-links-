# 🚀 Job Aggregator

A robust Python-based job aggregation tool that fetches jobs and internships from multiple platforms (LinkedIn, Internshala, and 100+ boards via Adzuna) and provides **direct application URLs** for easy manual application.

## ✨ Features

- 🔍 **Multi-Platform Search** - Aggregates jobs from LinkedIn, Internshala (internships + fresher jobs) and Adzuna, queried in parallel
- 🎓 **Entry-Level Filter** - Drops Senior/Lead/Manager titles and postings asking for 2+ years of experience
- 🧭 **Backend Focus** - Searches several backend roles by default and drops off-role titles (frontend, UI/UX, Android, sales, ...)
- 🎯 **Direct URLs** - Provides actual job posting links, not redirects
- ⏰ **Fresh Jobs Only** - Filters jobs posted within the last 7 days (configurable with `--days`)
- 🧹 **Smart Deduplication** - Removes duplicate listings automatically
- 📁 **Clean Output** - Organized text file plus a CSV tracking sheet with a `Status` column
- 🔧 **Easy Configuration** - Simple .env file setup
- 🆓 **Free to Use** - Uses free Adzuna API tier

## 📋 Requirements

- Python 3.7+
- Free Adzuna API account (takes 2 minutes to set up)

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd job-aggregator
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up Adzuna API credentials**
   
   - Go to https://developer.adzuna.com/overview
   - Sign up for a free account
   - Get your **APP_ID** and **APP_KEY** from the dashboard
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Edit `.env` and add your credentials:
     ```
     ADZUNA_APP_ID=your_app_id_here
     ADZUNA_APP_KEY=your_app_key_here
     ```

## 🚀 Usage

### Backend Jobs + Internships (default)
```bash
python job_aggregator.py
```
Searches "Backend Developer", "Backend Engineer" and "Backend Intern" across India, entry level only, last 7 days.

### Options
| Flag | Default | What it does |
|------|---------|--------------|
| `roles ...` | backend roles | One or more roles to search, e.g. `"Django Developer" "Node.js Developer"` |
| `--location` | `India` | City or country |
| `--days` | `7` | Only jobs posted in the last N days |
| `--level` | `entry` | `entry` = internships + fresher/junior roles; `any` = no seniority filter |
| `--exclude` | off-role list for backend searches | Comma-separated title keywords to drop (`--exclude ""` turns it off) |
| `--paid-only` | off | Skip unpaid internships |
| `--skills` | `MY_SKILLS` in `.env` | Comma-separated skills (`\|` for aliases, e.g. `Node.js\|NodeJS`); results matching more of them come first, titles built on stacks you don't list (Java, .NET, PHP, ...) go last |
| `--output` | timestamped file | Custom output filename (a `.csv` is written alongside) |

### Basic Search
```bash
python job_aggregator.py "Python Developer"
```

### Search with Location
```bash
python job_aggregator.py "Backend Developer" --location "Delhi"
```

### Custom Output File
```bash
python job_aggregator.py "Full Stack Developer" --output my_jobs.txt
```

### Examples
```bash
# Search for React Intern in Bangalore
python job_aggregator.py "React Intern" --location "Bangalore"

# Search for Data Scientist across India
python job_aggregator.py "Data Scientist" --location "India"

# Search for DevOps Engineer with custom output
python job_aggregator.py "DevOps Engineer" --location "Mumbai" --output devops_jobs.txt
```

## 📂 Output

Results are saved in the `job_results/` directory with timestamped filenames. Each run writes a `.txt` report and a `.csv` tracking sheet (open in Excel/Sheets and fill the `Status` column as you apply):

```
job_results/
├── 20241220_220648_Backend_Developer_jobs.txt
├── 20241220_223015_Python_Developer_jobs.txt
└── ...
```

### Output Format

```
================================================================================
JOB SEARCH RESULTS - DIRECT APPLICATION LINKS
Generated: 2024-12-20 22:06:48
Total Jobs Found: 15
================================================================================

────────────────────────────────────────────────────────────────────────────────
SOURCE: LinkedIn (8 jobs)
────────────────────────────────────────────────────────────────────────────────

1. Senior Backend Developer
   Company: Tech Corp India
   Location: Delhi, India
   Posted: 0 days ago
   DIRECT URL: https://in.linkedin.com/jobs/view/12345678

2. Python Backend Engineer
   Company: StartupXYZ
   Location: Bangalore, Karnataka
   Posted: 1 days ago
   DIRECT URL: https://in.linkedin.com/jobs/view/87654321
```

## 🎯 How It Works

1. **Searches Multiple Sources (in parallel)**
   - Queries Adzuna API (aggregates 100+ job boards, IT category, senior titles excluded)
   - Scrapes LinkedIn public job search
   - Scrapes Internshala internships and jobs by keyword

2. **Builds Direct URLs**
   - LinkedIn and Internshala links point straight at the posting
   - Adzuna links point at the Adzuna details page, which links out to the employer

3. **Filters & Deduplicates**
   - Filters jobs posted in the last `--days` days
   - Entry level: drops senior titles and postings needing 2+ years of experience
   - Drops off-role titles and (optionally) unpaid internships
   - Removes duplicates based on URL and title+company

4. **Outputs Clean Results**
   - Organizes by source platform
   - Provides direct, clickable URLs
   - Includes job details (title, company, location, date)

## 🔧 Configuration

Edit `job_aggregator.py` to customize:

```python
class Config:
    REQUEST_TIMEOUT = 15      # Request timeout in seconds
    REQUEST_DELAY = 2         # Delay between requests
    MAX_RESULTS = 50          # Maximum results per source
    LOCATION = "India"        # Default location
    OUTPUT_DIR = "job_results" # Output directory
    DEFAULT_ROLES = ["Backend Developer", "Backend Engineer", "Backend Intern"]
    DEFAULT_DAYS = 7          # Posting age window
    MAX_EXPERIENCE_YEARS = 1  # Entry level: skip postings asking for more
    BACKEND_EXCLUDE_KEYWORDS = [...]  # Off-role titles dropped for backend searches
```

## 🗂️ Project Structure

```
job-aggregator/
├── job_aggregator.py      # Main script
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── .env                  # Your API credentials (gitignored)
├── .gitignore           # Git ignore file
├── README.md            # This file
└── job_results/         # Output directory (created automatically)
```

## 📝 API Rate Limits

**Adzuna Free Tier:**
- 250 calls per month
- ~8 searches per day
- Perfect for personal use

**Tips:**
- Use broader location terms ("India" vs specific cities)
- Run searches once per day for best results
- The script uses 1 API call per role (the default backend search uses 3)

## 🐛 Troubleshooting

### "No jobs found"
- **Solution 1**: Set up Adzuna API credentials in `.env`
- **Solution 2**: Try broader search terms ("Developer" instead of "Senior Backend Developer")
- **Solution 3**: Use "India" as location instead of specific cities

### "403 Forbidden" / "429 Too Many Requests" errors
- This can happen for direct scrapers (LinkedIn/Internshala) if you run many searches back to back
- Naukri was removed: its pages are now JavaScript-rendered and its API requires a reCAPTCHA
- The script will still work with Adzuna API
- These sites block automated access

### "Module not found" error
- Run: `pip install -r requirements.txt`

## 🤝 Contributing

Feel free to:
- Add new job board scrapers
- Improve date parsing
- Add export formats (CSV, JSON)
- Enhance deduplication logic

## 📄 License

MIT License - Free for personal and commercial use

## ⚠️ Disclaimer

This tool is for **personal job searching only**. Please:
- Respect website Terms of Service
- Don't abuse rate limits
- Use responsibly and ethically
- Apply to jobs manually (no auto-application)

## 🙏 Credits

- Uses [Adzuna API](https://developer.adzuna.com/) for job aggregation
- Built with Python, Requests, and BeautifulSoup

## 📞 Support

For issues or questions:
1. Check the Troubleshooting section above
2. Ensure your Adzuna API credentials are correct
3. Try with simpler search terms first

---

**Happy Job Hunting! 🎉**