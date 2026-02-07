#!/usr/bin/env python3
import asyncio
import aiohttp
import subprocess
from datetime import datetime

URL_LIST = "https://crawler.ninja/files/https-sites.txt"
OUTPUT_FILE = "nextjs_sites.txt"
CONCURRENCY = 500
TIMEOUT = 5
SAVE_INTERVAL = 60  # seconds
GIT_BRANCH = "scan-results"
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


def is_next_header(headers):
    """Check X-Powered-By and Server headers for Next.js"""
    powered = headers.get("X-Powered-By", "")
    server = headers.get("Server", "")
    if DEBUG:
        print(f"DEBUG Headers: X-Powered-By={powered} | Server={server}")
    return "next.js" in powered.lower() or "vercel" in server.lower()


async def check_site(session, sem, url):
    """Check a single site for Next.js"""
    async with sem:
        try:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT)

            # HEAD request
            try:
                async with session.head(url, timeout=timeout, allow_redirects=True) as resp:
                    if DEBUG:
                        print(f"[HEAD] {url} -> {resp.status}")
                    if is_next_header(resp.headers):
                        print(f"[+] {url} -> Next.js found via HEAD header")
                        return url
            except Exception as e:
                if DEBUG:
                    print(f"[HEAD ERROR] {url} -> {e}")

            # Fallback GET /
            try:
                async with session.get(url, timeout=timeout) as resp:
                    if DEBUG:
                        print(f"[GET /] {url} -> {resp.status}")
                    if is_next_header(resp.headers):
                        print(f"[+] {url} -> Next.js found via GET / header")
                        return url
            except Exception as e:
                if DEBUG:
                    print(f"[GET ERROR] {url} -> {e}")

            # Check /_next/static/
            next_url = url.rstrip("/") + "/_next/static/"
            try:
                async with session.get(next_url, timeout=timeout, allow_redirects=True) as resp:
                    if DEBUG:
                        print(f"[GET _next/static/] {next_url} -> {resp.status}")
                    if resp.status in (200, 301, 302):
                        print(f"[+] {url} -> Next.js suspected via /_next/static/")
                        return url
            except Exception as e:
                if DEBUG:
                    print(f"[NEXT STATIC ERROR] {next_url} -> {e}")

        except Exception as e:
            if DEBUG:
                print(f"[ERROR] {url} -> {e}")

        return None


def save_and_commit(sites):
    """Save found sites and push to git"""
    if not sites:
        return
    with open(OUTPUT_FILE, "w") as f:
        for site in sites:
            f.write(site + "\n")
    print(f"[💾] Saved {len(sites)} sites to {OUTPUT_FILE}")

    try:
        subprocess.run(["git", "checkout", GIT_BRANCH], check=False)
    except:
        subprocess.run(["git", "checkout", "-b", GIT_BRANCH], check=True)

    subprocess.run(["git", "add", OUTPUT_FILE], check=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"Auto-save: {len(sites)} sites | {timestamp}"
    subprocess.run(["git", "commit", "-m", commit_msg], check=False)
    subprocess.run(["git", "push", "-u", "origin", GIT_BRANCH], check=False)
    print(f"[✓] Git commit
