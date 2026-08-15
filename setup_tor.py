import urllib.request
import tarfile
import os
import subprocess
import time

# Using a known stable version of Tor Expert Bundle from the archive
TOR_URL = "https://archive.torproject.org/tor-package-archive/torbrowser/13.5.2/tor-expert-bundle-windows-x86_64-13.5.2.tar.gz"
TOR_DIR = "tor_bundle"

def setup_and_run_tor():
    if not os.path.exists(TOR_DIR):
        print(f"Downloading Tor Expert Bundle from {TOR_URL}...")
        try:
            # Add a user-agent to avoid being blocked
            req = urllib.request.Request(TOR_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response, open("tor.tar.gz", 'wb') as out_file:
                out_file.write(response.read())
            print("Extracting...")
            with tarfile.open("tor.tar.gz", "r:gz") as tar:
                tar.extractall(path=TOR_DIR)
            os.remove("tor.tar.gz")
            print("Download and extraction complete.")
        except Exception as e:
            print(f"Failed to download/extract Tor: {e}")
            return
            
    tor_exe = os.path.join(TOR_DIR, "tor", "tor.exe")
    if not os.path.exists(tor_exe):
        print(f"Could not find {tor_exe}. Extraction may have failed.")
        return
        
    print(f"Starting Tor from {tor_exe}...")
    # Start Tor in the background
    # Using CREATE_NO_WINDOW (0x08000000) and DETACHED_PROCESS (0x00000008) 
    # so it runs silently and stays alive after this script exits
    subprocess.Popen([tor_exe], creationflags=0x08000008)
    print("Tor proxy started successfully!")
    print("It is now listening on 127.0.0.1:9050.")
    print("Please wait ~10 seconds for it to fully connect to the Tor network before running a search in Drak web.")

if __name__ == "__main__":
    setup_and_run_tor()
