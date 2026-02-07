import asyncio
import aiohttp
import subprocess
from datetime import datetime

URL_LIST = "https://crawler.ninja/files/https-sites.txt"
OUTPUT_FILE = "nextjs_sites.txt"
CONCURRENCY = 500
TIMEOUT = 5
SAVE_INTERVAL = 60  # секунд
GIT_BRANCH = "scan-results"

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
    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(URL_LIST) as resp:
            text = await resp.text()
            return [line.strip() for line in text.splitlines() if line.strip()]


def is_next_header(headers):
    powered = headers.get("X-Powered-By", "")
    server = headers.get("Server", "")
    return "next.js" in powered.lower() or "vercel" in server.lower()


async def check_site(session, sem, url):
    async with sem:
        try:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT)

            # HEAD
            try:
                async with session.head(url, timeout=timeout, allow_redirects=True) as resp:
                    if is_next_header(resp.headers):
                        return url
            except:
                pass

            # Fallback GET /
            try:
                async with session.get(url, timeout=timeout) as resp:
                    if is_next_header(resp.headers):
                        return url
            except:
                pass

            # Check /_next/static/
            next_url = url.rstrip("/") + "/_next/static/"
            try:
                async with session.get(next_url, timeout=timeout, allow_redirects=True) as resp:
                    if resp.status in (200, 301, 302):
                        return url
            except:
                pass

        except Exception:
            pass

        return None


def save_and_commit(sites):
    if not sites:
        return
    # Save to file
    with open(OUTPUT_FILE, "w") as f:
        for site in sites:
            f.write(site + "\n")
    print(f"[💾] Saved {len(sites)} sites to {OUTPUT_FILE}")

    # Git commit and push
    try:
        subprocess.run(["git", "checkout", GIT_BRANCH], check=False)
    except:
        subprocess.run(["git", "checkout", "-b", GIT_BRANCH], check=True)

    subprocess.run(["git", "add", OUTPUT_FILE], check=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"Auto-save: {len(sites)} sites | {timestamp}"
    subprocess.run(["git", "commit", "-m", commit_msg], check=False)
    subprocess.run(["git", "push", "-u", "origin", GIT_BRANCH], check=False)
    print(f"[✓] Git commit & push done: {commit_msg}")


async def periodic_save(sites):
    while True:
        await asyncio.sleep(SAVE_INTERVAL)
        save_and_commit(sites)


async def main():
    sites_list = await fetch_sites()
    print(f"Loaded {len(sites_list)} sites")

    sem = asyncio.Semaphore(CONCURRENCY)
    connector = aiohttp.TCPConnector(limit=CONCURRENCY, ssl=False)
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)

    found = []

    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout, connector=connector) as session:
        asyncio.create_task(periodic_save(found))

        for site in sites_list:
            result = await check_site(session, sem, site)
            if result:
                found.append(result)
                print(f"[+] {result} (Total found: {len(found)})")

        save_and_commit(found)

    print(f"\n[✓] Finished. Total Next.js sites found: {len(found)}")


if __name__ == "__main__":
    asyncio.run(main())
