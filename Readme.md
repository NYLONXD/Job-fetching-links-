# 🚀 Job Aggregator

A robust Python-based job aggregation tool that fetches jobs from multiple platforms (LinkedIn, Naukri, Indeed, Internshala) and provides **direct application URLs** for easy manual application.

## ✨ Features

- 🔍 **Multi-Platform Search** - Aggregates jobs from LinkedIn, Naukri, Indeed, Internshala, and more
- 🎯 **Direct URLs** - Provides actual job posting links, not redirects
- ⏰ **Fresh Jobs Only** - Filters jobs posted within the last 72 hours
- 🧹 **Smart Deduplication** - Removes duplicate listings automatically
- 📁 **Clean Output** - Organized text files with all job details
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

Results are saved in the `job_results/` directory with timestamped filenames:

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

1. **Searches Multiple Sources**
   - Queries Adzuna API (aggregates 100+ job boards)
   - Directly scrapes LinkedIn and Naukri (as backup)

2. **Resolves Direct URLs**
   - Follows redirects to get actual job posting links
   - Identifies source platform (LinkedIn, Naukri, etc.)

3. **Filters & Deduplicates**
   - Filters jobs posted in last 72 hours
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
- The script uses ~1 API call per search

## 🐛 Troubleshooting

### "No jobs found"
- **Solution 1**: Set up Adzuna API credentials in `.env`
- **Solution 2**: Try broader search terms ("Developer" instead of "Senior Backend Developer")
- **Solution 3**: Use "India" as location instead of specific cities

### "403 Forbidden" errors
- This is normal for direct scrapers (LinkedIn/Naukri)
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