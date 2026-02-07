#!/usr/bin/env python3
import asyncio
import aiohttp
from datetime import datetime
import subprocess

URL_LIST = "https://crawler.ninja/files/https-sites.txt"
OUTPUT_FILE = "nextjs_sites.txt"
CONCURRENCY = 200
TIMEOUT = 5
DEBUG = True  # True for debug output, False for quiet mode

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

async def fetch_sites():
    """Download site list and parse valid domains"""
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(URL_LIST) as resp:
            text = await resp.text()
            lines = text.splitlines()
            return parse_sites(lines)

def parse_sites(lines):
    """Extract domain from lines formatted as 'number domain'"""
    sites = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 2:
            continue
        domain = parts[1].replace(",", "")
        if domain:
            sites.append("https://" + domain)
    return sites

async def check_site(session, sem, url):
    """Check a single site for Next.js via /_next/static/"""
    async with sem:
        next_url = url.rstrip("/") + "/_next/static/"
        try:
            async with session.get(next_url, timeout=TIMEOUT, allow_redirects=True) as resp:
                if DEBUG:
                    print(f"[GET] {next_url} -> {resp.status}")
                if resp.status in (200, 301, 302, 403):
                    with open(OUTPUT_FILE, "a") as f:
                        f.write(f"{url}\n")
                    print(f"[+] {url} -> Next.js suspected")
                    return url
        except Exception as e:
            if DEBUG:
                print(f"[ERROR] {next_url} -> {e}")
        return None

def save_and_push_final_file(file_path):
    """Create a git branch with date (YYYYMMDD), commit and push the final file"""
    branch_name = f"scan{datetime.now().strftime('%Y%m%d')}"
    try:
        # Create branch and switch
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)

        # Add file
        subprocess.run(["git", "add", file_path], check=True)

        # Commit
        commit_msg = f"Next.js scan result | {datetime.now().strftime('%Y-%m-%d')}"
        subprocess.run(["git", "commit", "-m", commit_msg], check=False)

        # Push branch
        subprocess.run(["git", "push", "-u", "origin", branch_name], check=False)

        print(f"[✓] Saved and pushed final file to branch {branch_name}")

        # Optionally return to main branch
        subprocess.run(["git", "checkout", "main"], check=False)

    except subprocess.CalledProcessError as e:
        print(f"[!] Git operation failed: {e}")

async def main():
    sites_list = await fetch_sites()
    print(f"Loaded {len(sites_list)} sites")

    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ssl=False)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)

    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout, connector=connector) as session:
        tasks = [check_site(session, sem, site) for site in sites_list]
        results = await asyncio.gather(*tasks)

    found_sites = [r for r in results if r]
    print(f"\n[✓] Finished. Total Next.js sites found: {len(found_sites)}")

    if found_sites:
        save_and_push_final_file(OUTPUT_FILE)

if __name__ == "__main__":
    asyncio.run(main())
