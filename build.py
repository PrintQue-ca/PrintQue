#!/usr/bin/env python3
"""
Cross-platform build script for PrintQue
Creates portable executables for Windows, macOS, and Linux

Usage:
    python build.py              # Build for current platform
    python build.py --clean      # Clean build artifacts first
    python build.py --skip-frontend  # Skip frontend build (use existing)
    python build.py --version 1.2.3  # Override version (for CI)
"""

import os
import sys
import shutil
import subprocess
import platform
import argparse
import re
from pathlib import Path
from datetime import datetime

# Build configuration
APP_NAME = "PrintQue"


def get_version_from_file() -> str:
    """Read version from api/__version__.py"""
    version_file = Path(__file__).parent / "api" / "__version__.py"
    if version_file.exists():
        content = version_file.read_text()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
    return "0.0.0"  # Fallback


# Default version from source file (can be overridden via --version flag)
VERSION = get_version_from_file()

# Directories
ROOT_DIR = Path(__file__).parent.absolute()
API_DIR = ROOT_DIR / "api"
APP_DIR = ROOT_DIR / "app"
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"

# Platform detection
PLATFORM = platform.system().lower()  # 'windows', 'darwin', 'linux'
IS_WINDOWS = PLATFORM == "windows"
IS_MAC = PLATFORM == "darwin"
IS_LINUX = PLATFORM == "linux"


def print_header(message: str):
    """Print a formatted header"""
    print("\n" + "=" * 60)
    print(f"  {message}")
    print("=" * 60 + "\n")


def print_step(message: str):
    """Print a step message"""
    print(f"[*] {message}")


def print_success(message: str):
    """Print a success message"""
    print(f"[+] {message}")


def print_error(message: str):
    """Print an error message"""
    print(f"[!] ERROR: {message}", file=sys.stderr)


def run_command(cmd: list, cwd: Path = None, check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result"""
    print(f"    Running: {' '.join(str(c) for c in cmd)}")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            capture_output=True,
            text=True
        )
        if result.stdout:
            for line in result.stdout.strip().split('\n')[:10]:  # Show first 10 lines
                print(f"    {line}")
        return result
    except subprocess.CalledProcessError as e:
        print_error(f"Command failed with code {e.returncode}")
        if e.stdout:
            print(f"    STDOUT: {e.stdout[:500]}")
        if e.stderr:
            print(f"    STDERR: {e.stderr[:500]}")
        raise


def clean_build():
    """Clean previous build artifacts"""
    print_step("Cleaning previous builds...")
    
    dirs_to_clean = [BUILD_DIR, DIST_DIR]
    files_to_clean = [f for f in ROOT_DIR.glob("*.spec") if f.is_file() and f.suffix == ".spec"]
    
    for d in dirs_to_clean:
        if d.exists():
            try:
                shutil.rmtree(d)
                print(f"    Removed {d}")
            except Exception as e:
                print(f"    Warning: Could not remove {d}: {e}")
    
    for f in files_to_clean:
        try:
            f.unlink()
            print(f"    Removed {f}")
        except Exception as e:
            print(f"    Warning: Could not remove {f}: {e}")
    
    # Clean frontend build
    frontend_dist = APP_DIR / "dist"
    if frontend_dist.exists():
        try:
            shutil.rmtree(frontend_dist)
            print(f"    Removed {frontend_dist}")
        except Exception as e:
            print(f"    Warning: Could not remove {frontend_dist}: {e}")
    
    print_success("Clean complete")


def check_dependencies():
    """Check that required dependencies are installed"""
    print_step("Checking dependencies...")
    
    # Check Python version
    if sys.version_info < (3, 9):
        print_error(f"Python 3.9+ required, found {sys.version}")
        return False
    print(f"    Python {sys.version.split()[0]} - OK")
    
    # Check PyInstaller
    try:
        import PyInstaller
        print(f"    PyInstaller {PyInstaller.__version__} - OK")
    except ImportError:
        print_error("PyInstaller not installed. Run: pip install pyinstaller")
        return False
    
    # Check Node.js
    try:
        result = run_command(["node", "--version"], check=False)
        if result.returncode == 0:
            print(f"    Node.js {result.stdout.strip()} - OK")
        else:
            print_error("Node.js not found. Please install Node.js 18+")
            return False
    except FileNotFoundError:
        print_error("Node.js not found. Please install Node.js 18+")
        return False
    
    # Check npm
    npm_cmd = "npm.cmd" if IS_WINDOWS else "npm"
    try:
        result = run_command([npm_cmd, "--version"], check=False)
        if result.returncode == 0:
            print(f"    npm {result.stdout.strip()} - OK")
        else:
            print_error("npm not found")
            return False
    except FileNotFoundError:
        print_error("npm not found")
        return False
    
    print_success("All dependencies OK")
    return True


def install_python_deps():
    """Install Python dependencies"""
    print_step("Installing Python dependencies...")
    
    requirements_file = API_DIR / "requirements.txt"
    if not requirements_file.exists():
        print_error(f"requirements.txt not found at {requirements_file}")
        return False
    
    run_command([sys.executable, "-m", "pip", "install", "-r", str(requirements_file)])
    
    # Also install PyInstaller if not present
    run_command([sys.executable, "-m", "pip", "install", "pyinstaller"], check=False)
    
    print_success("Python dependencies installed")
    return True


def build_frontend():
    """Build the React frontend"""
    print_step("Building React frontend...")
    
    if not APP_DIR.exists():
        print_error(f"Frontend directory not found: {APP_DIR}")
        return False
    
    # Install npm dependencies
    print("    Installing npm dependencies...")
    npm_cmd = "npm.cmd" if IS_WINDOWS else "npm"
    run_command([npm_cmd, "install"], cwd=APP_DIR)
    
    # Build the frontend
    print("    Building production bundle...")
    run_command([npm_cmd, "run", "build"], cwd=APP_DIR)
    
    # Check for build output
    frontend_dist = APP_DIR / "dist"
    if not frontend_dist.exists():
        # TanStack Start might output to .output/public
        alt_dist = APP_DIR / ".output" / "public"
        if alt_dist.exists():
            frontend_dist = alt_dist
        else:
            print_error("Frontend build output not found")
            return False
    
    print_success(f"Frontend built to {frontend_dist}")
    return True


def copy_frontend_to_api():
    """Copy built frontend files to API static folder"""
    print_step("Copying frontend to API static folder...")
    
    # Find frontend build output
    frontend_dist = APP_DIR / "dist"
    if not frontend_dist.exists():
        frontend_dist = APP_DIR / ".output" / "public"
    
    if not frontend_dist.exists():
        print_error("Frontend build output not found")
        return False
    
    # Target directory for frontend in API
    target_dir = API_DIR / "frontend_dist"
    
    # Remove existing
    if target_dir.exists():
        shutil.rmtree(target_dir)
    
    # Copy frontend build
    shutil.copytree(frontend_dist, target_dir)
    print_success(f"Frontend copied to {target_dir}")
    return True


def create_pyinstaller_spec():
    """Create PyInstaller spec file for the current platform"""
    print_step("Creating PyInstaller spec file...")
    
    # Platform-specific settings
    if IS_WINDOWS:
        exe_name = APP_NAME
        icon_file = "printque.ico"
        console = False  # No console window - standalone app opens browser only
    elif IS_MAC:
        exe_name = APP_NAME
        icon_file = "printque.icns"
        console = False
    else:  # Linux
        exe_name = APP_NAME.lower()
        icon_file = None
        console = True
    
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-
# Auto-generated PyInstaller spec for {APP_NAME}
# Platform: {PLATFORM}
# Generated: {datetime.now().isoformat()}

import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

# Paths
api_dir = r'{API_DIR}'
root_dir = r'{ROOT_DIR}'

# Change to API directory for imports
sys.path.insert(0, api_dir)
os.chdir(api_dir)

# Collect all dependencies
datas = []
binaries = []
hiddenimports = []

# Flask and extensions
for package in ['flask', 'flask_socketio', 'flask_cors', 'jinja2', 'click', 'werkzeug', 'markupsafe']:
    try:
        tmp_ret = collect_all(package)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

# Socket.IO packages
for package in ['socketio', 'engineio', 'python_socketio', 'python_engineio']:
    try:
        hiddenimports += collect_submodules(package)
    except Exception:
        pass

# Other critical packages
packages_to_collect = [
    'eventlet', 'eventlet.green', 'eventlet.hubs',
    'dns', 'dns.resolver', 'cryptography',
    'aiohttp', 'aiofiles', 'requests', 'urllib3', 'certifi',
    'psutil', 'dotenv', 'simple_websocket', 'bidict', 'greenlet',
    'paho', 'paho.mqtt', 'paho.mqtt.client',
]

for package in packages_to_collect:
    try:
        hiddenimports.append(package)
        hiddenimports += collect_submodules(package)
    except Exception:
        pass

# Add specific imports that are often missed
hiddenimports += [
    'engineio.async_drivers.threading',
    'engineio.async_drivers.eventlet',
    'flask.json.provider',
    'werkzeug.routing',
    'werkzeug.serving',
    'jinja2.ext',
    'dns.rdataclass',
    'dns.rdatatype',
    'dns.exception',
    'pkg_resources',
]

# Add application data files
datas += [
    (os.path.join(api_dir, 'static'), 'static'),
    (os.path.join(api_dir, 'routes'), 'routes'),
    (os.path.join(api_dir, 'services'), 'services'),
    (os.path.join(api_dir, 'utils'), 'utils'),
    (os.path.join(api_dir, 'default_settings.json'), '.'),
]

# Add frontend build if it exists
frontend_dist = os.path.join(api_dir, 'frontend_dist')
if os.path.exists(frontend_dist):
    datas += [(frontend_dist, 'frontend_dist')]

a = Analysis(
    [os.path.join(api_dir, 'app.py')],
    pathex=[api_dir],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'tkinter', 'PyQt5', 'PyQt6'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{exe_name}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console={console},
    disable_windowed_traceback=False,
    argv_emulation={'True' if IS_MAC else 'False'},
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='{icon_file}' if os.path.exists(os.path.join(root_dir, '{icon_file or ""}')) else None,
)

# macOS: Create .app bundle
'''
    
    if IS_MAC:
        spec_content += f'''
app = BUNDLE(
    exe,
    name='{APP_NAME}.app',
    icon='{icon_file}' if os.path.exists(os.path.join(root_dir, '{icon_file or ""}')) else None,
    bundle_identifier='com.printque.app',
    info_plist={{
        'CFBundleName': '{APP_NAME}',
        'CFBundleDisplayName': '{APP_NAME}',
        'CFBundleVersion': '{VERSION}',
        'CFBundleShortVersionString': '{VERSION}',
        'NSHighResolutionCapable': True,
    }},
)
'''
    
    spec_file = ROOT_DIR / f"{APP_NAME}.spec"
    spec_file.write_text(spec_content)
    print_success(f"Spec file created: {spec_file}")
    return True


def build_executable():
    """Build the executable using PyInstaller"""
    print_step("Building executable with PyInstaller...")
    
    spec_file = ROOT_DIR / f"{APP_NAME}.spec"
    if not spec_file.exists():
        print_error("Spec file not found. Run create_pyinstaller_spec first.")
        return False
    
    # Run PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(spec_file),
        "--clean",
        "-y",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR),
    ]
    
    run_command(cmd, cwd=ROOT_DIR)
    
    # Verify output
    if IS_WINDOWS:
        exe_path = DIST_DIR / f"{APP_NAME}.exe"
    elif IS_MAC:
        exe_path = DIST_DIR / f"{APP_NAME}.app"
    else:
        exe_path = DIST_DIR / APP_NAME.lower()
    
    if exe_path.exists():
        print_success(f"Executable created: {exe_path}")
        return True
    else:
        print_error(f"Executable not found at {exe_path}")
        return False


def create_distribution():
    """Create a distribution package with all necessary files"""
    print_step("Creating distribution package...")
    
    # Create platform-specific distribution name with version
    platform_name = {"windows": "Windows", "darwin": "macOS", "linux": "Linux"}[PLATFORM]
    dist_name = f"{APP_NAME}-{VERSION}-{platform_name}"
    dist_folder = DIST_DIR / dist_name
    
    # Create distribution folder
    dist_folder.mkdir(parents=True, exist_ok=True)
    
    # Copy executable (single-file release; app uses %USERPROFILE%\PrintQueData for data/logs/uploads)
    if IS_WINDOWS:
        src_exe = DIST_DIR / f"{APP_NAME}.exe"
        if src_exe.exists():
            shutil.copy(src_exe, dist_folder)
    elif IS_MAC:
        src_app = DIST_DIR / f"{APP_NAME}.app"
        if src_app.exists():
            shutil.copytree(src_app, dist_folder / f"{APP_NAME}.app")
    else:
        src_exe = DIST_DIR / APP_NAME.lower()
        if src_exe.exists():
            shutil.copy(src_exe, dist_folder)
    
    # No data/logs/uploads folders in release - app uses user app data folder
    # No .bat/.sh launcher - run the exe (or .app) directly
    
    # Create README
    readme = dist_folder / "README.txt"
    readme.write_text(f'''{APP_NAME} - Open Source Print Farm Manager
{'=' * 40}

Quick Start:
1. {'Double-click ' + APP_NAME + '.exe (browser opens automatically).' if IS_WINDOWS else 'Run ./' + APP_NAME.lower() if IS_LINUX else 'Open ' + APP_NAME + '.app'}
2. Open http://localhost:5000 if it doesn't open automatically.
3. Add your printers and start managing!

Data Storage (user app data folder, not next to the exe):
- Windows: %USERPROFILE%\\PrintQueData\\
- macOS/Linux: ~/PrintQueData/
- Config, uploads, and logs are stored there automatically.

Code signing:
- The executable is not currently signed. On Windows you may see SmartScreen
  or your antivirus flagging it; you can choose "Run anyway" or add an
  exception. We plan to sign releases in the future.

Open Source:
- All features enabled, no printer limits
- License: GPL v3
- GitHub: https://github.com/PrintQue/PrintQue

Support:
- Logs: PrintQueData\\app.log (or printque.log in PrintQueData\\logs)
- GitHub Issues: https://github.com/PrintQue/PrintQue/issues

Version: {VERSION}
Platform: {platform_name}
''')
    
    # Create zip archive
    zip_path = DIST_DIR / f"{dist_name}.zip"
    print(f"    Creating archive: {zip_path}")
    shutil.make_archive(str(DIST_DIR / dist_name), 'zip', DIST_DIR, dist_name)
    
    print_success(f"Distribution created: {dist_folder}")
    print_success(f"Archive created: {zip_path}")
    return True


def main():
    global VERSION
    
    parser = argparse.ArgumentParser(description=f"Build {APP_NAME} for {PLATFORM}")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts first")
    parser.add_argument("--skip-frontend", action="store_true", help="Skip frontend build")
    parser.add_argument("--skip-deps", action="store_true", help="Skip dependency installation")
    parser.add_argument("--version", type=str, help="Override version (for CI builds)")
    args = parser.parse_args()
    
    # Override version if provided via command line
    if args.version:
        VERSION = args.version
        print(f"Using version override: {VERSION}")
    
    print_header(f"{APP_NAME} Build Script")
    print(f"Version: {VERSION}")
    print(f"Platform: {PLATFORM}")
    print(f"Python: {sys.version.split()[0]}")
    print(f"Working directory: {ROOT_DIR}")
    
    try:
        # Clean if requested
        if args.clean:
            clean_build()
        
        # Check dependencies
        if not check_dependencies():
            return 1
        
        # Install Python dependencies
        if not args.skip_deps:
            if not install_python_deps():
                return 1
        
        # Build frontend
        if not args.skip_frontend:
            if not build_frontend():
                print_error("Frontend build failed")
                return 1
            
            if not copy_frontend_to_api():
                return 1
        
        # Create spec file and build
        if not create_pyinstaller_spec():
            return 1
        
        if not build_executable():
            return 1
        
        # Create distribution
        if not create_distribution():
            return 1
        
        print_header("Build Complete!")
        print(f"Output: {DIST_DIR}")
        print(f"Version: {VERSION}")
        print("\nTo test the build:")
        platform_name = {"windows": "Windows", "darwin": "macOS", "linux": "Linux"}[PLATFORM]
        dist_name = f"{APP_NAME}-{VERSION}-{platform_name}"
        if IS_WINDOWS:
            print(f"  cd dist\\{dist_name}")
            print(f"  {APP_NAME}.exe")
        elif IS_MAC:
            print(f"  open dist/{dist_name}/{APP_NAME}.app")
        else:
            print(f"  cd dist/{dist_name}")
            print(f"  ./{APP_NAME.lower()}")
        
        return 0
        
    except Exception as e:
        print_error(f"Build failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
