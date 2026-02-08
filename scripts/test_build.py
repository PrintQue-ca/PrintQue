#!/usr/bin/env python3
"""
Quick test script to verify the PrintQue build works correctly.

Usage:
    python scripts/test_build.py           # Test the source directly
    python scripts/test_build.py --dist    # Test the built executable
"""

import os
import sys
import time
import subprocess
import argparse
import platform
import requests
from pathlib import Path

# Repo root (script lives in scripts/)
ROOT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT_DIR / "dist"
API_DIR = ROOT_DIR / "api"

def get_exe_path():
    """Get the path to the built executable"""
    system = platform.system().lower()
    if system == "windows":
        exe = DIST_DIR / "PrintQue.exe"
        if not exe.exists():
            # Check in dated folder
            for folder in DIST_DIR.glob("PrintQue_Windows_*"):
                exe = folder / "PrintQue.exe"
                if exe.exists():
                    return exe
        return exe
    elif system == "darwin":
        app = DIST_DIR / "PrintQue.app" / "Contents" / "MacOS" / "PrintQue"
        if not app.exists():
            for folder in DIST_DIR.glob("PrintQue_macOS_*"):
                app = folder / "PrintQue.app" / "Contents" / "MacOS" / "PrintQue"
                if app.exists():
                    return app
        return app
    else:
        exe = DIST_DIR / "printque"
        if not exe.exists():
            for folder in DIST_DIR.glob("PrintQue_Linux_*"):
                exe = folder / "printque"
                if exe.exists():
                    return exe
        return exe


def test_api_endpoints(base_url: str = "http://localhost:5000"):
    """Test that the API endpoints are responding"""
    endpoints = [
        ("/api/v1/system/stats", "System stats"),
        ("/api/v1/printers", "Printers list"),
        ("/api/v1/orders", "Orders list"),
        ("/api/v1/system/license", "License info"),
    ]
    
    print("\nTesting API endpoints...")
    all_passed = True
    
    for endpoint, name in endpoints:
        try:
            resp = requests.get(f"{base_url}{endpoint}", timeout=5)
            if resp.status_code == 200:
                print(f"  [PASS] {name}: {endpoint}")
            else:
                print(f"  [FAIL] {name}: {endpoint} - Status {resp.status_code}")
                all_passed = False
        except requests.exceptions.RequestException as e:
            print(f"  [FAIL] {name}: {endpoint} - {e}")
            all_passed = False
    
    return all_passed


def test_frontend(base_url: str = "http://localhost:5000"):
    """Test that the frontend is being served"""
    print("\nTesting frontend...")
    try:
        resp = requests.get(base_url, timeout=5)
        if resp.status_code == 200:
            if "<!DOCTYPE html>" in resp.text or "<html" in resp.text:
                print("  [PASS] Frontend HTML is being served")
                return True
            else:
                print("  [WARN] Response received but may not be HTML")
                return True
        else:
            print(f"  [FAIL] Frontend returned status {resp.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"  [FAIL] Could not reach frontend: {e}")
        return False


def run_source_test():
    """Run the API from source for testing"""
    print("Starting API from source...")
    print(f"Working directory: {API_DIR}")
    
    # Start the API
    process = subprocess.Popen(
        [sys.executable, "app.py"],
        cwd=API_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Wait for startup
    print("Waiting for server to start...")
    time.sleep(5)
    
    try:
        # Run tests
        api_ok = test_api_endpoints()
        frontend_ok = test_frontend()
        
        if api_ok and frontend_ok:
            print("\n[SUCCESS] All tests passed!")
            return 0
        else:
            print("\n[FAILED] Some tests failed")
            return 1
    finally:
        print("\nStopping server...")
        process.terminate()
        process.wait(timeout=5)


def run_dist_test():
    """Run the built executable for testing"""
    exe_path = get_exe_path()
    
    if not exe_path.exists():
        print(f"[ERROR] Executable not found at {exe_path}")
        print("Run 'python scripts/build.py' first to create the executable.")
        return 1
    
    print(f"Starting executable: {exe_path}")
    
    # Start the executable
    process = subprocess.Popen(
        [str(exe_path)],
        cwd=exe_path.parent,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Wait for startup (executables may take longer)
    print("Waiting for server to start...")
    time.sleep(10)
    
    try:
        # Run tests
        api_ok = test_api_endpoints()
        frontend_ok = test_frontend()
        
        if api_ok and frontend_ok:
            print("\n[SUCCESS] All tests passed!")
            return 0
        else:
            print("\n[FAILED] Some tests failed")
            return 1
    finally:
        print("\nStopping server...")
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


def main():
    parser = argparse.ArgumentParser(description="Test PrintQue build")
    parser.add_argument("--dist", action="store_true", help="Test built executable instead of source")
    args = parser.parse_args()
    
    print("=" * 50)
    print("  PrintQue Build Test")
    print("=" * 50)
    print(f"Platform: {platform.system()}")
    print(f"Python: {sys.version.split()[0]}")
    
    # Check for requests library
    try:
        import requests
    except ImportError:
        print("\n[ERROR] 'requests' library required for testing.")
        print("Install with: pip install requests")
        return 1
    
    if args.dist:
        return run_dist_test()
    else:
        return run_source_test()


if __name__ == "__main__":
    sys.exit(main())
