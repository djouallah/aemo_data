import re
import requests
from urllib.request import urlopen
import io
import zipfile
import datetime
import tempfile
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Tuple
import obstore
from obstore.store import from_url
import threading

def is_github_tree_url(url: str) -> bool:
    """Check if URL is a GitHub (directory) URL."""
    clean_url = url.rstrip('/*')
    return clean_url.startswith("https://github.com/") and "/tree/" in clean_url


def is_glob_pattern(url: str) -> bool:
    """Check if URL ends with glob pattern /*."""
    return url.endswith('/*')


def github_tree_to_api_url(url: str) -> str:
    """Convert GitHub tree URL to GitHub API contents URL."""
    clean_url = url.rstrip('/*')
    parts = clean_url.replace("https://github.com/", "", 1).split("/", 3)
    if len(parts) < 4:
        raise ValueError("Invalid GitHub tree URL")
    user, repo, tree, branch_path = parts
    if tree != "tree":
        raise ValueError("Expected /tree/ in URL")
    branch_path_parts = branch_path.split("/", 1)
    branch = branch_path_parts[0]
    path = branch_path_parts[1] if len(branch_path_parts) > 1 else ""
    return f"https://api.github.com/repos/{user}/{repo}/contents/{path}?ref={branch}"


def recursively_find_zip_files(api_url: str, base_path: str = "") -> List[Tuple[str, str, str]]:
    """
    Recursively find all .zip files in a GitHub directory and subdirectories.
    
    Args:
        api_url: GitHub API URL for the directory
        base_path: Relative path prefix for nested directories
    
    Returns:
        List of tuples (filename, relative_path, download_url) for each zip file found
        - filename: just the base filename (e.g., "file.zip")
        - relative_path: full path including subdirs (e.g., "2025/file.zip")
        - download_url: the GitHub download URL
    """
    zip_files = []
    
    try:
        resp = requests.get(api_url, timeout=30)
        if not resp.ok:
            print(f"Warning: Failed to fetch {api_url}: HTTP {resp.status_code}")
            return zip_files
        
        items = resp.json()
        if not isinstance(items, list):
            return zip_files
        
        for item in items:
            item_name = item.get("name", "")
            item_type = item.get("type", "")
            
            if item_type == "file" and item_name.endswith(".zip"):
                # Found a zip file
                relative_path = f"{base_path}/{item_name}" if base_path else item_name
                zip_files.append((item_name, relative_path, item["download_url"]))
            
            elif item_type == "dir":
                # Recursively search subdirectory
                subdir_url = item.get("url")
                if subdir_url:
                    subdir_path = f"{base_path}/{item_name}" if base_path else item_name
                    zip_files.extend(recursively_find_zip_files(subdir_url, subdir_path))
    
    except Exception as e:
        print(f"Error scanning directory {api_url}: {e}")
    
    return zip_files


def scraping(urls: List[str], folders: List[str], totalfiles: int, ws: str, lh: str, max_workers: int) -> int:
    """
    Optimized download function using obstore for OneLake operations.
    Files are extracted directly without gzip compression and written to disk immediately.

    Supports:
      - Regular HTML directory listings (original behavior)
      - GitHub tree URLs (e.g., https://github.com/user/repo/tree/branch/path)
      - GitHub tree URLs with glob pattern (e.g., https://github.com/user/repo/tree/branch/path/*)

    Returns:
        int: 1 if files were successfully downloaded, 0 if error or no new files
    """
    store = from_url(f'abfss://{ws}@onelake.dfs.fabric.microsoft.com/{lh}.Lakehouse/Files')
    summary = []
    total_files_processed = 0
    
    # Thread lock for log operations
    log_lock = threading.Lock()

    def process_url(url_folder_pair: Tuple[str, str]) -> Tuple[str, int]:
        url, folder = url_folder_pair

        clean_folder = folder.strip("/")
        if clean_folder and not clean_folder.endswith("/"):
            clean_folder += "/"

        log_file_name = clean_folder + "download_log.csv"

        # Step 1: Read log fresh from OneLake (with lock to prevent race conditions)
        with log_lock:
            downloaded_files = set()  # Use set for O(1) lookups
            try:
                log_result = obstore.get(store, log_file_name)
                log_bytes = log_result.bytes()
                log_content = bytes(log_bytes).decode("utf-8").strip()
                
                if log_content:
                    lines = log_content.splitlines()
                    if len(lines) > 1:  # Skip header if exists
                        for line in lines[1:]:
                            if line.strip():
                                # Extract zip filename (first column)
                                parts = line.split(",", 1)
                                if parts:
                                    downloaded_files.add(parts[0].strip())
            except Exception as e:
                print(f"Could not read log file {log_file_name}: {e}")
                downloaded_files = set()

        def extract_week_partition(filename: str) -> str:
            match = re.search(r"(\d{4})(\d{2})(\d{2})", filename)
            if match:
                year, month, day = map(int, match.groups())
                dt = datetime.date(year, month, day)
                iso_year, iso_week, _ = dt.isocalendar()
                return f"week={iso_year}_{iso_week:02d}"
            return "week=unknown"

        # Step 2: Get list of .zip files based on URL type
        github_zip_url_map = {}
        try:
            if is_github_tree_url(url):
                # Use GitHub API to list directory contents
                api_url = github_tree_to_api_url(url)
                
                if is_glob_pattern(url):
                    # Recursive search for all zip files in subdirectories
                    zip_files_info = recursively_find_zip_files(api_url)
                    if not zip_files_info:
                        return f"{url} - No zip files found in directory tree", 0
                    # zip_files_info contains (filename, relative_path, download_url)
                    # Sort by filename
                    zip_files_info.sort(key=lambda x: x[0], reverse=True)
                    all_files = [filename for filename, relative_path, download_url in zip_files_info]
                    github_zip_url_map = {filename: download_url for filename, relative_path, download_url in zip_files_info}
                else:
                    # Single directory search (original behavior)
                    api_resp = requests.get(api_url, timeout=30)
                    if not api_resp.ok:
                        return f"{url} - GitHub API error: {api_resp.status_code}", 0
                    items = api_resp.json()
                    if not isinstance(items, list):
                        return f"{url} - Not a directory (GitHub API returned file or error)", 0

                    zip_files_info = []
                    for item in items:
                        if item.get("type") == "file" and item.get("name", "").endswith(".zip"):
                            zip_files_info.append((item["name"], item["download_url"]))
                    
                    zip_files_info.sort(key=lambda x: x[0], reverse=True)
                    all_files = [name for name, _ in zip_files_info]
                    github_zip_url_map = dict(zip_files_info)
            else:
                # Original: parse HTML directory listing
                html_content = urlopen(url).read().decode("utf-8")
                pattern = re.compile(r"[\w.-]+\.zip")
                all_files = sorted(dict.fromkeys(pattern.findall(html_content)), reverse=True)
        except Exception as e:
            return f"{url} - Failed to list files: {e}", 0

        # Filter out already downloaded files
        new_files = [f for f in all_files if f not in downloaded_files]
        new_files = sorted(new_files, reverse=True)[:totalfiles]

        if not new_files:
            return f"{url} - 0 files extracted (all {len(all_files)} files already downloaded)", 0

        uploaded_log_entries = []

        def process_file(filename: str):
            """Process a single zip file: download, extract to temp disk, upload each file immediately."""
            temp_zip_path = None
            try:
                # Determine download URL
                if is_github_tree_url(url):
                    download_url = github_zip_url_map[filename]
                else:
                    download_url = url + filename

                # Download to temporary file to avoid holding entire zip in memory
                with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
                    temp_zip_path = temp_zip.name
                    with requests.get(download_url, stream=True, timeout=30) as resp:
                        if not resp.ok:
                            print(f"Failed to download {filename}: HTTP {resp.status_code}")
                            return None
                        # Stream download in chunks
                        for chunk in resp.iter_content(chunk_size=8192):
                            if chunk:
                                temp_zip.write(chunk)

                # Extract and upload each file individually
                results = []
                partition_folder = clean_folder + extract_week_partition(filename) + "/"
                
                with zipfile.ZipFile(temp_zip_path, "r") as zf:
                    for zip_info in zf.infolist():
                        if zip_info.is_dir():
                            continue
                        
                        # Extract to temporary file
                        with tempfile.NamedTemporaryFile(delete=False) as temp_extracted:
                            temp_extracted_path = temp_extracted.name
                            try:
                                # Extract directly to temp file
                                with zf.open(zip_info) as source:
                                    chunk_size = 8192
                                    while True:
                                        chunk = source.read(chunk_size)
                                        if not chunk:
                                            break
                                        temp_extracted.write(chunk)
                                
                                # Upload directly from temp file
                                extracted_filename = partition_folder + zip_info.filename
                                with open(temp_extracted_path, 'rb') as upload_file:
                                    obstore.put(store, extracted_filename, upload_file.read())
                                
                                results.append((filename, extracted_filename))
                                
                            finally:
                                # Clean up temp extracted file immediately
                                try:
                                    os.unlink(temp_extracted_path)
                                except:
                                    pass
                
                return results
                
            except Exception as e:
                print(f"Error processing {filename}: {e}")
                return None
            finally:
                # Clean up temp zip file
                if temp_zip_path and os.path.exists(temp_zip_path):
                    try:
                        os.unlink(temp_zip_path)
                    except:
                        pass

        # Step 3: Process files with parallelism controlled by max_workers
        successful_uploads = []
        with ThreadPoolExecutor(max_workers=min(max_workers, len(new_files))) as pool:
            futures = [pool.submit(process_file, fn) for fn in new_files]
            for f in as_completed(futures):
                res = f.result()
                if res:
                    successful_uploads.extend(res)

        # Step 4: Update log with successful uploads
        if successful_uploads:
            with log_lock:
                try:
                    # Read current log state again (in case it was updated by another thread)
                    existing_lines = []
                    try:
                        existing_log_result = obstore.get(store, log_file_name)
                        existing_log_bytes = existing_log_result.bytes()
                        existing_log = bytes(existing_log_bytes).decode("utf-8").strip()
                        if existing_log:
                            lines = existing_log.splitlines()
                            if len(lines) > 1:  # Skip header
                                existing_lines = lines[1:]
                    except:
                        pass

                    # Add new entries
                    new_lines = [f"{zipf},{extracted_path}" for zipf, extracted_path in successful_uploads]
                    all_log_lines = existing_lines + new_lines
                    log_content = "zip_filename,extracted_filepath\n" + "\n".join(all_log_lines)
                    obstore.put(store, log_file_name, log_content.encode("utf-8"))
                    print(f"Updated log {log_file_name} with {len(successful_uploads)} new entries")

                except Exception as e:
                    print(f"Error updating log file {log_file_name}: {e}")

        return f"{url} - {len(successful_uploads)} files extracted and uploaded", len(successful_uploads)

    # Process URLs concurrently
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {
            executor.submit(process_url, (url, folder)): url
            for url, folder in zip(urls, folders)
        }
        for future in as_completed(future_to_url):
            try:
                result, files_count = future.result()
                summary.append(result)
                total_files_processed += files_count
            except Exception as e:
                url = future_to_url[future]
                summary.append(f"{url} - Error: {e}")
                # Don't add to total_files_processed for errors

    # Print summary for debugging
    print("\n".join(summary))
    
    # Return 1 if any files were processed, 0 otherwise
    return 1 if total_files_processed > 0 else 0
