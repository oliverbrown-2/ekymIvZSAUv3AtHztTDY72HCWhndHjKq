#!/usr/bin/env python3
import asyncio
import aiohttp
import subprocess
import random
import time
import re
import os
import sys
from datetime import datetime

PROXY_URL = "https://raw.githubusercontent.com/Skillter/ProxyGather/refs/heads/master/proxies/working-proxies-all.txt"

DORKS = [
    'inurl:_next',
    'inurl:_next/static',
    'inurl:_next/data',
    'intext:"__NEXT_DATA__"',
    'intitle:"Next.js"',
    'inurl:_next "webpack"',
    'inurl:_next "getServerSideProps"',
    '"_next/webpack-hmr"',
    'inurl:_next/static/chunks',
    'inurl:_next "Server Actions"',
]

# SETTINGS
MAX_RESULTS = 100
RELOAD_PROXIES_AFTER_N_FAILS = 50
SAVE_EVERY_N_REQUESTS = 10
RESULTS_BRANCH = "scan-results"

# Path to pagodo script
PAGODO_PATH = os.path.join(os.path.dirname(__file__), 'pagodo', 'pagodo.py')

class InfiniteScanner:
    def __init__(self):
        self.proxies = []
        self.dead_proxies = set()
        self.all_domains = set()
        self.session_count = 0
        self.total_requests = 0
        self.start_time = datetime.now()
        self.last_save_time = datetime.now()
        self.commit_count = 0
    
    async def download_proxies(self):
        """Download fresh proxies from GitHub"""
        print(f"\n[*] Downloading fresh proxies (session {self.session_count})...")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(PROXY_URL, timeout=30) as resp:
                    text = await resp.text()
                    
                    new_proxies = []
                    for line in text.splitlines():
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if not line.startswith('http'):
                                line = f'http://{line}'
                            
                            if line not in self.dead_proxies:
                                new_proxies.append(line)
                    
                    self.proxies = new_proxies
                    print(f"[+] Loaded {len(self.proxies)} new proxies")
                    print(f"[+] Dead proxies blacklist: {len(self.dead_proxies)}")
                    
                    return len(new_proxies) > 0
        except Exception as e:
            print(f"[-] Error downloading proxies: {e}")
            return False
    
    def git_commit_and_push(self):
        """Commit and push results to separate branch"""
        try:
            # Configure git (for GitHub Actions)
            subprocess.run(['git', 'config', 'user.name', 'Scanner Bot'], check=False)
            subprocess.run(['git', 'config', 'user.email', 'scanner@bot.com'], check=False)
            
            # Switch to results branch (create if doesn't exist)
            result = subprocess.run(['git', 'checkout', RESULTS_BRANCH], 
                                  capture_output=True, text=True)
            
            if result.returncode != 0:
                # Branch doesn't exist, create it
                subprocess.run(['git', 'checkout', '-b', RESULTS_BRANCH], check=True)
                print(f"[+] Created new branch: {RESULTS_BRANCH}")
            
            # Add the results file
            subprocess.run(['git', 'add', 'infinite_domains.txt'], check=True)
            subprocess.run(['git', 'add', 'scan_stats.txt'], check=True)
            
            # Commit with timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            commit_msg = f"Auto-save: {len(self.all_domains)} domains | {timestamp}"
            
            result = subprocess.run(['git', 'commit', '-m', commit_msg], 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                # Push to remote
                subprocess.run(['git', 'push', '-u', 'origin', RESULTS_BRANCH], check=True)
                
                self.commit_count += 1
                print(f"[✓] Git commit #{self.commit_count}: {commit_msg}")
                print(f"[✓] Pushed to branch: {RESULTS_BRANCH}")
            else:
                if "nothing to commit" in result.stdout:
                    print("[*] No changes to commit")
                else:
                    print(f"[-] Commit failed: {result.stdout}")
            
            # Switch back to main branch
            subprocess.run(['git', 'checkout', 'main'], check=False)
            
        except subprocess.CalledProcessError as e:
            print(f"[-] Git error: {e}")
        except Exception as e:
            print(f"[-] Unexpected git error: {e}")
    
    def save_domains_to_file(self):
        """Save all domains to file and stats"""
        try:
            # Save domains
            with open('infinite_domains.txt', 'w') as f:
                for domain in sorted(self.all_domains):
                    f.write(domain + '\n')
            
            # Save statistics
            elapsed = (datetime.now() - self.start_time).total_seconds()
            rate = len(self.all_domains) / (elapsed / 3600) if elapsed > 0 else 0
            
            with open('scan_stats.txt', 'w') as f:
                f.write(f"Scanner Statistics\n")
                f.write(f"==================\n\n")
                f.write(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                f.write(f"Total requests:      {self.total_requests}\n")
                f.write(f"Total domains:       {len(self.all_domains)}\n")
                f.write(f"Dead proxies:        {len(self.dead_proxies)}\n")
                f.write(f"Sessions:            {self.session_count}\n")
                f.write(f"Running time:        {elapsed/60:.1f} minutes\n")
                f.write(f"Domains/hour:        {rate:.1f}\n")
                f.write(f"Git commits:         {self.commit_count}\n")
            
            print(f"[💾] Saved {len(self.all_domains)} domains to file")
            self.last_save_time = datetime.now()
            
            return True
            
        except Exception as e:
            print(f"[-] Error saving domains: {e}")
            return False
    
    def run_single_dork(self, dork_idx, dork, proxy):
        """Execute a single dork query with one proxy"""
        
        dork_file = f'infinite_dork_{dork_idx}.txt'
        results_file = f'infinite_results_{self.session_count}_{dork_idx}_{int(time.time())}.txt'
        
        with open(dork_file, 'w') as f:
            f.write(dork)
        
        # Build command to run pagodo.py directly with Python
        cmd = [
            sys.executable,  # Use same Python interpreter
            PAGODO_PATH,
            '-g', dork_file,
            '-s', results_file,
            '-p', proxy,
            '-i', 10,
            '-x', 30,
            '-m', MAX_RESULTS
        ]
        
        try:
            self.total_requests += 1
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                try:
                    with open(results_file, 'r', errors='ignore') as f:
                        lines = [l.strip() for l in f if l.strip()]
                        
                        for line in lines:
                            domains = re.findall(r'https?://([^/\s<>"]+)', line)
                            for domain in domains:
                                if 'google' not in domain.lower():
                                    self.all_domains.add(domain)
                        
                        return {'status': 'success', 'results': len(lines), 'proxy': proxy}
                except Exception as e:
                    print(f"[-] Error reading results: {e}")
                    pass
                
                return {'status': 'success', 'results': 0, 'proxy': proxy}
            else:
                # Print stderr for debugging
                if result.stderr:
                    print(f"[-] Pagodo error: {result.stderr[:200]}")
                return {'status': 'failed', 'proxy': proxy}
        
        except subprocess.TimeoutExpired:
            return {'status': 'timeout', 'proxy': proxy}
        except Exception as e:
            print(f"[-] Unexpected error: {e}")
            return {'status': 'error', 'proxy': proxy}
    
    async def infinite_scan(self):
        """Run infinite scanning until proxies are exhausted"""
        
        print(f"""
    ╔════════════════════════════════════════════╗
    ║      INFINITE Next.js Scanner              ║
    ║      (runs until proxies exhausted)        ║
    ║      💾 Auto-saves & commits every {SAVE_EVERY_N_REQUESTS:2}      ║
    ╚════════════════════════════════════════════╝
    
    [*] Pagodo path: {PAGODO_PATH}
    [*] Python: {sys.executable}
        """)
        
        # Check if pagodo exists
        if not os.path.exists(PAGODO_PATH):
            print(f"[!] ERROR: Pagodo not found at {PAGODO_PATH}")
            print(f"[!] Please run setup first (see README)")
            return
        
        consecutive_fails = 0
        
        # Initial save and commit
        self.save_domains_to_file()
        self.git_commit_and_push()
        
        try:
            while True:
                # Reload proxies if needed
                if not self.proxies or consecutive_fails >= RELOAD_PROXIES_AFTER_N_FAILS:
                    if not await self.download_proxies():
                        print("\n[!] No more proxies available. Stopping.")
                        break
                    
                    self.session_count += 1
                    consecutive_fails = 0
                
                if not self.proxies:
                    print("\n[!] All proxies exhausted. Stopping.")
                    break
                
                # Select random proxy and dork
                proxy = random.choice(self.proxies)
                dork_idx = random.randint(0, len(DORKS) - 1)
                dork = DORKS[dork_idx]
                
                # Execute the scan
                result = self.run_single_dork(dork_idx, dork, proxy)
                
                # Process result
                if result['status'] == 'success':
                    consecutive_fails = 0
                    print(f"[✓] {result['results']:3} results | {len(self.all_domains):6} total | Proxy OK")
                
                elif result['status'] in ['failed', 'timeout', 'error']:
                    consecutive_fails += 1
                    
                    self.dead_proxies.add(proxy)
                    if proxy in self.proxies:
                        self.proxies.remove(proxy)
                    
                    print(f"[✗] Proxy DEAD ({result['status']}) | Remaining: {len(self.proxies)} | Fails: {consecutive_fails}")
                
                # Save to disk and commit every N requests
                if self.total_requests % SAVE_EVERY_N_REQUESTS == 0:
                    if self.save_domains_to_file():
                        self.git_commit_and_push()
                
                # Print statistics every 10 requests
                if self.total_requests % 10 == 0:
                    elapsed = (datetime.now() - self.start_time).total_seconds()
                    rate = len(self.all_domains) / (elapsed / 3600) if elapsed > 0 else 0
                    
                    print(f"\n{'='*50}")
                    print(f"[Stats] Requests: {self.total_requests} | Domains: {len(self.all_domains)}")
                    print(f"[Stats] Rate: {rate:.1f} domains/hour | Alive proxies: {len(self.proxies)}")
                    print(f"[Stats] Running: {elapsed/60:.1f} minutes")
                    print(f"[Stats] Commits: {self.commit_count}")
                    print(f"{'='*50}\n")
                
                await asyncio.sleep(random.randint(1, 3))
        
        except KeyboardInterrupt:
            print("\n\n[!] Interrupted by user (Ctrl+C)")
            print("[*] Saving data before exit...")
            self.save_domains_to_file()
            self.git_commit_and_push()
        
        # Final save and commit
        self.print_final_stats()
        self.save_domains_to_file()
        self.git_commit_and_push()
    
    def print_final_stats(self):
        """Print final scan statistics"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        
        print(f"""
    ╔════════════════════════════════════════════╗
    ║         Infinite Scan Complete             ║
    ╠════════════════════════════════════════════╣
    ║ Total requests:       {self.total_requests:20} ║
    ║ Total domains found:  {len(self.all_domains):20} ║
    ║ Dead proxies:         {len(self.dead_proxies):20} ║
    ║ Sessions:             {self.session_count:20} ║
    ║ Git commits:          {self.commit_count:20} ║
    ╠════════════════════════════════════════════╣
    ║ Running time:         {elapsed/60:17.1f} min ║
    ║ Domains/hour:         {len(self.all_domains)/(elapsed/3600) if elapsed > 0 else 0:17.1f} ║
    ╚════════════════════════════════════════════╝
        """)

async def main():
    scanner = InfiniteScanner()
    await scanner.infinite_scan()

if __name__ == '__main__':
    asyncio.run(main())
