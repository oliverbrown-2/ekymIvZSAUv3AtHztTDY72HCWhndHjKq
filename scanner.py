#!/usr/bin/env python3
import subprocess
import threading
import time
import os
import sys
import urllib.request

PROXY_URL = "https://raw.githubusercontent.com/Skillter/ProxyGather/refs/heads/master/proxies/working-proxies-all.txt"

DORKS = [
    'inurl:_next',
    'inurl:_next/static',
    'inurl:_next/data',
    'intext:"__NEXT_DATA__"',
    'intitle:"Next.js"',
]

MAX_RESULTS = 100
COMMIT_INTERVAL = 300  # seconds
RESULTS_BRANCH = "scan-results"

PAGODO_PATH = os.path.join(os.path.dirname(__file__), 'pagodo', 'pagodo.py')
DORK_FILE = "dorks.txt"
RESULT_FILE = "results.txt"


class Scanner:

    def download_proxies(self):
        print("[*] Downloading proxies...")
        with urllib.request.urlopen(PROXY_URL, timeout=30) as r:
            lines = r.read().decode().splitlines()

        proxies = []
        for p in lines:
            p = p.strip()
            if not p:
                continue
            if not p.startswith("https"):
                p = "https://" + p
            proxies.append(p)

        proxy_string = ",".join(proxies)
        print(f"[+] Loaded {len(proxies)} proxies")
        return proxy_string

    def write_dorks(self):
        with open(DORK_FILE, "w") as f:
            f.write("\n".join(DORKS))

    def run_pagodo(self, proxy_string):
        cmd = [
            sys.executable,
            PAGODO_PATH,
            "-g", DORK_FILE,
            "-s", RESULT_FILE,
            "-p", proxy_string,
            "-i", "10",
            "-x", "30",
            "-m", str(MAX_RESULTS),
            "-v", "2"
        ]
        subprocess.run(cmd)

    def git_commit_loop(self):
        while True:
            time.sleep(COMMIT_INTERVAL)

            subprocess.run(["git", "checkout", RESULTS_BRANCH],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)

            subprocess.run(["git", "add", RESULT_FILE])
            subprocess.run(
                ["git", "commit", "-m", "Auto update results"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            subprocess.run(["git", "push"],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)

            print("[✓] Auto-committed results.txt")

    def run(self):
        if not os.path.exists(PAGODO_PATH):
            print("Pagodo not found.")
            return

        self.write_dorks()
        proxy_string = self.download_proxies()

        t = threading.Thread(target=self.git_commit_loop, daemon=True)
        t.start()

        try:
            while True:
                self.run_pagodo(proxy_string)
                time.sleep(5)

        except KeyboardInterrupt:
            print("\n[!] Stopping...")
            subprocess.run(["git", "add", RESULT_FILE])
            subprocess.run(["git", "commit", "-m", "Final update"])
            subprocess.run(["git", "push"])


if __name__ == "__main__":
    Scanner().run()
