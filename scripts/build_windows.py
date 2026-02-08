#!/usr/bin/env python
"""
Legacy Windows-specific build script for PrintQue.
For current builds use: python scripts/build.py

This script expects to be run from the repository root. It uses ROOT_DIR
so that build/ and dist/ are at repo root when run from scripts/.
"""
import os
import sys
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

# Repo root (script lives in scripts/)
ROOT_DIR = Path(__file__).resolve().parent.parent


def clean_build():
    """Clean previous build artifacts"""
    print("Cleaning previous builds...")
    dirs_to_remove = [ROOT_DIR / 'build', ROOT_DIR / 'dist', ROOT_DIR / 'api' / '__pycache__']
    for d in dirs_to_remove:
        if d.exists():
            shutil.rmtree(d)
            print(f"Removed {d}")


def check_files():
    """Verify all required files exist (under api/)"""
    print("\nChecking required files...")
    api = ROOT_DIR / 'api'
    required = [
        api / 'app.py',
        api / 'state.py',
        api / 'printer_manager.py',
        api / 'config.py',
        api / 'requirements.txt',
    ]
    required_dirs = [api / 'routes']
    missing = []
    for f in required:
        if f.exists():
            print(f"[OK] {f.relative_to(ROOT_DIR)}")
        else:
            print(f"[MISSING] {f.relative_to(ROOT_DIR)}")
            missing.append(f)
    for d in required_dirs:
        if d.is_dir():
            print(f"[OK] {d.relative_to(ROOT_DIR)}/")
        else:
            print(f"[MISSING] {d.relative_to(ROOT_DIR)}/")
            missing.append(d)
    if missing:
        print("\nError: Missing required files!")
        return False
    template_dir = api / 'templates'
    if template_dir.exists():
        print(f"Found {len(list(template_dir.iterdir()))} templates")
    else:
        print("[MISSING] api/templates directory!")
        return False
    return True


def build_exe():
    """Build the executable using PyInstaller"""
    print("\nBuilding PrintQue.exe...")
    
    # Create a spec file first
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-
import os

# Add all your Python modules
your_modules = [
    'routes',
    'state',
    'printer_manager',
    'config',
    'printer_routes',
    'bambu_handler',
    'retry_utils',
    'logger',
    'order_routes',
    'filament_routes',
]

a = Analysis(
    ['run_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static') if os.path.exists('static') else ('templates', 'templates'),
    ],
    hiddenimports=[
        'engineio.async_drivers.threading',
        'flask_socketio',
        'eventlet',
        'eventlet.hubs.epolls',
        'eventlet.hubs.kqueue',
        'eventlet.hubs.selects',
        'dns',
        'dns.resolver',
        'dns.asyncresolver',
        'dns.asyncbackend',
        'dns.rdataclass',
        'dns.rdatatype',
        'cryptography',
        'cryptography.fernet',
        'aiohttp',
        'aiohttp.connector',
        'requests',
        'psutil',
        'werkzeug',
        'werkzeug.serving',
        'jinja2',
        'click',
        'itsdangerous',
        'markupsafe',
        'paho',
        'paho.mqtt',
        'paho.mqtt.client',
        'threading',
        're',
        'asyncio',
        'copy',
        'uuid',
        'tempfile',
        'datetime',
    ] + your_modules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PrintQue',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
'''
    
    spec_file = ROOT_DIR / 'PrintQue.spec'
    spec_file.write_text(spec_content)
    
    # Build using the spec file (run from root so dist/build at root)
    cmd = [sys.executable, '-m', 'PyInstaller', str(spec_file), '--clean', '-y']
    try:
        result = subprocess.run(cmd, cwd=str(ROOT_DIR), check=True, capture_output=True, text=True)
        print("Build completed successfully!")
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Build failed with error code {e.returncode}")
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False
    except FileNotFoundError:
        print("\nError: PyInstaller not found!")
        print("Please install it with: pip install pyinstaller")
        return False


def create_distribution():
    """Create a distribution package"""
    print("\nCreating distribution package...")
    
    dist_name = f"PrintQue_Windows_{datetime.now().strftime('%Y%m%d')}"
    dist_dir = ROOT_DIR / 'dist' / dist_name
    
    dist_dir.mkdir(parents=True, exist_ok=True)
    
    src_exe = ROOT_DIR / 'dist' / 'PrintQue.exe'
    if src_exe.exists():
        shutil.copy(src_exe, dist_dir)
        print(f"Copied PrintQue.exe to {dist_dir}")
    else:
        print("Error: PrintQue.exe not found!")
        return False
    
    for dir_name in ['data', 'uploads', 'certs']:
        (dist_dir / dir_name).mkdir(exist_ok=True)
        print(f"Created directory: {dir_name}")
    
    batch_content = """@echo off
title PrintQue Server
echo ================================================
echo           PrintQue - Print Farm Manager
echo ================================================
echo.
echo Starting PrintQue server...
echo.
echo The web interface will be available at:
echo   http://localhost:5000
echo.
echo Press Ctrl+C to stop the server.
echo ================================================
echo.
PrintQue.exe
pause
"""
    (dist_dir / 'Start_PrintQue.bat').write_text(batch_content)
    print("Created Start_PrintQue.bat")
    
    readme_content = """PrintQue - Open Source Print Farm Manager
==========================================

Quick Start:
1. Double-click 'Start_PrintQue.bat' to launch the server
2. Open your web browser and go to: http://localhost:5000
3. Add your printers and start managing your print farm!

Open Source Edition:
- All features enabled, no printer limits
- License: GPL v3
- GitHub: https://github.com/PrintQue/PrintQue

Data Storage:
- All data is stored in ~/PrintQueData/
- Security keys are auto-generated on first run
- No manual configuration is needed

Troubleshooting:
- If port 5000 is in use, the server will automatically try the next available port
- Check console window for error messages
- Report issues: https://github.com/PrintQue/PrintQue/issues
- Ensure firewall allows the application
- First run may be slow due to Windows Defender scan

Support:
- GitHub: [Your GitHub URL]
- Email: [Your Support Email]

Version: 1.0
"""
    (dist_dir / 'README.txt').write_text(readme_content)
    print("Created README.txt")
    
    zip_path = ROOT_DIR / 'dist' / f'{dist_name}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, dist_dir.parent)
                zipf.write(file_path, arcname)
    print(f"Distribution package created: {zip_path}")
    return True


def main():
    print("=" * 60)
    print("   PrintQue Windows Executable Builder (legacy)")
    print("   Prefer: python scripts/build.py")
    print("=" * 60)
    
    if sys.version_info < (3, 8):
        print("Error: Python 3.8 or higher is required")
        return 1
    
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("\nError: PyInstaller is not installed!")
        print("Install it with: pip install pyinstaller")
        return 1
    
    clean_build()
    if not check_files():
        print("\nBuild cannot continue - missing required files!")
        return 1
    if not build_exe():
        print("\nBuild failed! Check the error messages above.")
        return 1
    if not create_distribution():
        print("\nDistribution creation failed!")
        return 1
    
    print("\n" + "=" * 60)
    print("   Build Completed Successfully!")
    print("=" * 60)
    print(f"\nOutput: {ROOT_DIR / 'dist'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
