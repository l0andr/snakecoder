import argparse
from pyexpat import features

import requests
import json
import subprocess
import re
import tqdm
import shutil
import concurrent.futures

TIMEOUT_SECONDS = 10  # Default max time allowed for each clone
MAX_WORKERS = 8     # Number of parallel clones
# Paths we want to keep in the repo (relative to repo root).
# Adjust as necessary. For example, "Snakemake" or "snakemake",
# "workflow/*", "workflow/rules/*", "config/*", "README.md", etc.
SPARSE_PATHS = [
    "\snakefile",
    "\Snakefile",
    "workflow/Snakefile",
    "workflow/rules",
    "config",
    "\Readme.md",
    "\README.md",       # in case it's uppercase
]

from git import Repo
import os
from urllib.parse import urlparse, urljoin

def is_github_repo_link(href: str) -> bool:
    return (href.startswith("https://github.com/") or href.startswith("http://github.com/")
            and "/blob/" not in href and "/topics/" not in href)

def is_subpage_link(href: str, root_domain: str) -> bool:
    # e.g., check if the link is on the same domain
    return root_domain in href  # This is simplistic. Might need a more robust check.

def normalize_url(base, link):
    """Convert relative link to absolute."""
    return urljoin(base, link)

def read_data_file(data_file_path: str,standart_only=False, stargazers_min =3) -> list:
    """
    Reads data.js, strips off the 'var data = ' prefix (if present),
    and parses the remainder as JSON. Returns a list of dicts.
    """
    with open(data_file_path, 'r', encoding='utf-8') as f:
        content = f.read().strip()

    # Remove a leading "var data = " (or variations with spaces) using regex
    # Example line: var data = [...]
    content = re.sub(r'^var\s+data\s*=\s*', '', content)

    # If there's a trailing semicolon, remove it.
    # e.g. "[...];"
    content = content.rstrip(';').strip()

    # Now parse as JSON
    data_list = json.loads(content)
    #for el in data_list:
    #    print(el)
    #    print("----")
    if standart_only:
        data_list = [x for x in data_list if x['standardized'] == True]

    if stargazers_min > 0:
        data_list = [x for x in data_list if x['stargazers_count'] >= stargazers_min]
    return data_list

def convert_to_github_url(full_name: str) -> str:
    """
    Given a string like 'UserName/RepoName', return
    'https://github.com/UserName/RepoName'.
    """
    return f"https://github.com/{full_name}"

def verify_github_link(url: str) -> bool:
    """
    Perform a HEAD request to check if the GitHub link is valid (status_code == 200).
    Returns True if valid, False otherwise.
    """
    try:
        resp = requests.head(url, timeout=10)
        # GitHub often redirects HEAD requests, so 200 or 302 might both be "live" repos.
        return resp.status_code in (200, 302)
    except requests.RequestException as e:
        print(f"Error verifying {url}: {e}")
        return False

def clone_repo_partial(github_url: str,
                       base_dir: str,
                       sparse_paths: list,
                       timeout_sec: int = 10,verbose=1):
    """
    Clone a GitHub repo **partially** (sparse checkout only the specified subdirectories/files).

    Steps:
    1. Create local directory name from "owner_repo".
    2. Run "git clone --depth 1 --filter=blob:none --sparse URL local_path".
    3. cd into local_path, run "git sparse-checkout set <paths>".
    4. If any step exceeds `timeout_sec`, remove the directory and return.
    """
    # Derive local directory name from the GitHub URL
    if not verify_github_link(github_url):
        if verbose >= 1:
            print(f"[Info] Invalid GitHub repo URL (do not have access): {github_url}")
        return
    parsed = urlparse(github_url)
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) < 2:
        print(f"[ERROR] Invalid GitHub repo URL: {github_url}")
        return

    owner, repo = path_parts[0], path_parts[1].replace('.git', '')
    local_repo_name = f"{owner}_{repo}"
    clone_path = os.path.join(base_dir, local_repo_name)

    # Skip if already cloned
    if os.path.exists(clone_path):
        if verbose >= 1:
            print(f"[INFO] Skipping clone (already exists): {clone_path}")
        return

    # Ensure base directory
    os.makedirs(base_dir, exist_ok=True)
    if verbose > 1:
        print(f"[INFO] Cloning (sparse) {github_url} -> {clone_path}")

    # 1) git clone --depth=1 --filter=blob:none --sparse ...
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse",
             github_url, clone_path],
            check=True,
            timeout=timeout_sec
        )
    except subprocess.TimeoutExpired:
        if verbose >= 1:
            print(f"[TIMEOUT] Cloning took too long. Removing {clone_path}.")
        shutil.rmtree(clone_path, ignore_errors=True)
        return
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 'git clone' failed for {github_url}. Error: {e}")
        shutil.rmtree(clone_path, ignore_errors=True)
        return

    # 2) git sparse-checkout set ...
    #    Need to run this command from within the clone_path
    #    We'll handle additional time-limited calls similarly.
    try:
        # Step 1) init --no-cone
        subprocess.run(
            ["git", "-C", clone_path, "sparse-checkout", "init", "--no-cone"],
            check=True,
            timeout=timeout_sec
        )

        # Step 2) set directories/files
        cmd = ["git", "-C", clone_path, "sparse-checkout", "set"] + sparse_paths
        subprocess.run(cmd, check=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        if verbose >= 1:
            print(f"[TIMEOUT] Sparse checkout took too long. Removing {clone_path}.")
        shutil.rmtree(clone_path, ignore_errors=True)
        return
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] 'git sparse-checkout set' failed in {clone_path}. Error: {e}")
        shutil.rmtree(clone_path, ignore_errors=True)
        return

    print(f"[INFO] Successfully cloned partial repo to {clone_path}")


def clone_repo(github_url: str, base_dir: str = "crawler_results",verbose=1):
    # Extract repo name from the URL
    if not verify_github_link(github_url):
        if verbose >= 1:
            print(f"[Info] Invalid GitHub repo URL (do not have access): {github_url}")
        return
    path = urlparse(github_url).path  # e.g., "/username/repo"
    repo_name = path.strip("/").split("/")[-1]  # "repo"

    # Create local directory path
    local_path = os.path.join(base_dir, repo_name)

    # Ensure the base directory exists
    os.makedirs(base_dir, exist_ok=True)

    # If we want to skip if it already exists
    if os.path.exists(local_path):
        if verbose >= 1:
            print(f"Repository {repo_name} already cloned at {local_path}. Skipping.")
        return

    # Perform a git clone using subprocess
    if verbose > 1:
        print(f"Cloning {github_url} into {local_path}")
    subprocess.run(["git", "clone", github_url, local_path], check=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Download snakemake pipelines for training")
    parser.add_argument("-data_file", help="Path to data file", type=str, default="data.js")
    parser.add_argument("-output_dir", help="Output directory", type=str, required=True)
    parser.add_argument("--standart", help="Standardized only", default=False,action='store_true')
    parser.add_argument("--stars_min", help="Minimal number of stars", type=int, default=3)
    parser.add_argument("--partial", help="If set only snakemake files and readme will be copied", default=False, action='store_true')
    parser.add_argument("-verbose", help="Log level: 0 - error, 1 - info, 2 - debug  ", type=int, default=1)
    args = parser.parse_args()
    verbose = args.verbose
    outdir = args.output_dir

    data_file = args.data_file
    data_list = read_data_file(data_file,standart_only= args.standart, stargazers_min=args.stars_min)
    items_to_clone = []
    if verbose >= 1:

        print(f"[INFO] Found {len(data_list)} repos in data file.")
        print(f"[INFO] Number of workers: {MAX_WORKERS}")
    def check_accessibility(item):
        full_name = item.get("full_name")
        if not full_name:
            return None
        github_url = convert_to_github_url(full_name)
        return github_url
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for item in tqdm.tqdm(data_list, desc="Processing repos.Check accesibility", disable=verbose != 1):
            features = executor.submit(check_accessibility,item)
            items_to_clone.append(features.result())
    if verbose >= 1:
        print(f"[INFO] Found {len(items_to_clone)} valid repos to clone.")
    # For CPU-bound tasks, prefer processes.
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_url = {}
        for url in tqdm.tqdm(items_to_clone, desc="Cloning repos", disable=verbose != 1):
            if args.partial:
                future = executor.submit(
                    clone_repo_partial,
                    github_url=url,
                    base_dir=outdir,
                    sparse_paths=SPARSE_PATHS,
                    timeout_sec=TIMEOUT_SECONDS,
                    verbose = verbose
                )
            else:
                future = executor.submit(clone_repo, url, outdir,verbose=verbose)
            future_to_url[future] = url

        # Optionally, wait for all tasks to complete or handle as they finish
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                future.result()  # If an exception was raised inside clone_repo_partial, re-raise it here
            except Exception as e:
                print(f"[ERROR] Exception cloning {url}: {e}")


