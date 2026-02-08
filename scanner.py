#!/usr/bin/env python3
import asyncio
import aiohttp
import subprocess
import argparse
from datetime import datetime

parser = argparse.ArgumentParser()
parser.add_argument("--shard", type=int, default=0)
parser.add_argument("--total-shards", type=int, default=1)
args = parser.parse_args()

URL_LIST = "https://crawler.ninja/files/https-sites.txt"
OUTPUT_FILE = "nextjs_sites.txt"
CONCURRENCY = 100
TIMEOUT = 5
DEBUG = True  # True for debug output

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
    """Download site list and parse domains"""
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(URL_LIST) as resp:
            text = await resp.text()
            lines = text.splitlines()
            return parse_sites(lines)

def parse_sites(lines):
    """Extract domain from lines like '3 microsoft.com'"""
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
    """Check X-Powered-By and Server headers"""
    powered = headers.get("X-Powered-By", "")
    server = headers.get("Server", "")
    if DEBUG:
        print(f"DEBUG Headers: X-Powered-By={powered} | Server={server}")
    return "next.js" in powered.lower() or "vercel" in server.lower()

async def check_site(session, sem, url):
    """Check a single site for Next.js"""
    async with sem:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        try:
            # HEAD /
            try:
                async with session.head(url, timeout=timeout, allow_redirects=True) as resp:
                    if DEBUG:
                        print(f"[HEAD /] {url} -> {resp.status}")
                    if is_next_header(resp.headers):
                        print(f"[+] {url} -> Next.js found via HEAD header")
                        return url
            except Exception as e:
                if DEBUG:
                    print(f"[HEAD ERROR] {url} -> {e}")

            # GET / fallback
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

            # GET /_next/static/
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

async def main():
    sites_list = await fetch_sites()
    print(f"Loaded {len(sites_list)} sites")

    # Sharding
    sites_list = sites_list[args.shard::args.total_shards]
    print(f"Shard {args.shard}/{args.total_shards} processing {len(sites_list)} sites")

    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ssl=False)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)

    found = []

    async with aiohttp.ClientSession(
        headers=HEADERS,
        timeout=timeout,
        connector=connector
    ) as session:

        tasks = []
        for site in sites_list:
            task = asyncio.create_task(check_site(session, sem, site))
            tasks.append(task)

            # Limit number of scheduled tasks in memory
            if len(tasks) >= CONCURRENCY * 5:
                for completed in asyncio.as_completed(tasks):
                    result = await completed
                    if result:
                        found.append(result)
                tasks = []

        # Finish remaining tasks
        for completed in asyncio.as_completed(tasks):
            result = await completed
            if result:
                found.append(result)

    # Unique output per shard (recommended)
    output_file = f"nextjs_sites_{args.shard}.txt"
    with open(output_file, "w") as f:
        for site in found:
            f.write(site + "\n")

    print(f"[✓] Finished shard {args.shard}. Found: {len(found)}")

if __name__ == "__main__":
    asyncio.run(main())
