#!/usr/bin/env python
"""
Fixed build script for PrintQue Windows executable
"""
import os
import sys
import shutil
import subprocess
import zipfile
from datetime import datetime

def clean_build():
    """Clean previous build artifacts"""
    print("Cleaning previous builds...")
    dirs_to_remove = ['build', 'dist', '__pycache__']
    for dir_name in dirs_to_remove:
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name)
            print(f"Removed {dir_name}")

def check_files():
    """Verify all required files exist"""
    print("\nChecking required files...")
    required_files = [
        'app.py',
        'run_app.py',
        'routes.py',
        'state.py',
        'printer_manager.py',
        'config.py',
        'requirements.txt'
    ]
    
    missing_files = []
    for file in required_files:
        if os.path.exists(file):
            print(f"[OK] {file}")
        else:
            print(f"[MISSING] {file}")
            missing_files.append(file)
    
    if missing_files:
        print("\nError: Missing required files!")
        return False
    
    # Check templates
    print("\nChecking templates...")
    template_dir = 'templates'
    if os.path.exists(template_dir):
        templates = os.listdir(template_dir)
        print(f"Found {len(templates)} templates")
    else:
        print("[MISSING] templates directory!")
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
        'dotenv',
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
    
    # Write spec file
    with open('PrintQue.spec', 'w') as f:
        f.write(spec_content)
    
    # Build using the spec file
    cmd = ['pyinstaller', 'PrintQue.spec', '--clean', '-y']
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
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
    dist_dir = os.path.join('dist', dist_name)
    
    # Create distribution directory
    os.makedirs(dist_dir, exist_ok=True)
    
    # Copy executable
    if os.path.exists('dist/PrintQue.exe'):
        shutil.copy('dist/PrintQue.exe', dist_dir)
        print(f"Copied PrintQue.exe to {dist_dir}")
    else:
        print("Error: PrintQue.exe not found!")
        return False
    
    # Create data directories
    data_dirs = ['data', 'uploads', 'certs']
    for dir_name in data_dirs:
        target_dir = os.path.join(dist_dir, dir_name)
        os.makedirs(target_dir, exist_ok=True)
        print(f"Created directory: {dir_name}")
    
    # Copy additional files
    files_to_copy = [
        'README.txt',
        'requirements.txt',
    ]
    
    for file in files_to_copy:
        if os.path.exists(file):
            shutil.copy(file, dist_dir)
            print(f"Copied {file}")
    
    
    # Create batch file launcher
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
    
    with open(os.path.join(dist_dir, 'Start_PrintQue.bat'), 'w') as f:
        f.write(batch_content)
    print("Created Start_PrintQue.bat")
    
    # Create configuration template
    config_content = """# PrintQue Open Source Edition - Configuration Template
# Copy this file to .env and modify as needed

# Server Configuration
PORT=5000
HOST=0.0.0.0

# Security Keys (CHANGE THESE for production!)
SECRET_KEY=change-this-secret-key-to-something-random
ENCRYPTION_KEY=change-this-encryption-key-to-something-random
ADMIN_KEY=change-this-admin-key-to-something-random

# Bambu Printer Settings
BAMBU_CA_CERT=certs/bambu_ca.pem
"""
    
    with open(os.path.join(dist_dir, 'config_template.env'), 'w') as f:
        f.write(config_content)
    print("Created config_template.env")
    
    # Create README
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

Configuration:
- Copy 'config_template.env' to '.env' and modify the settings
- Default port is 5000 (change in .env if needed)

Data Storage:
- Printer data: data/printers.json
- Orders: data/orders.json
- Uploaded files: uploads/
- Certificates: certs/

First Run:
- The application will create all necessary data files automatically
- A default encryption key will be generated (WARNING shown in console)
- For production use, set your own ENCRYPTION_KEY in .env file

Troubleshooting:
- If port 5000 is in use, change PORT in .env file
- Check console window for error messages
- Report issues: https://github.com/PrintQue/PrintQue/issues
- Ensure firewall allows the application
- First run may be slow due to Windows Defender scan

Support:
- GitHub: [Your GitHub URL]
- Email: [Your Support Email]

Version: 1.0
"""
    
    with open(os.path.join(dist_dir, 'README.txt'), 'w') as f:
        f.write(readme_content)
    print("Created README.txt")
    
    # Create a zip file
    print(f"\nCreating zip archive: {dist_name}.zip")
    zip_path = f'dist/{dist_name}.zip'
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dist_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, os.path.dirname(dist_dir))
                zipf.write(file_path, arcname)
    
    print(f"Distribution package created: {zip_path}")
    return True

def main():
    print("=" * 60)
    print("   PrintQue Windows Executable Builder")
    print("=" * 60)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("Error: Python 3.8 or higher is required")
        print(f"Current version: {sys.version}")
        return 1
    
    print(f"Python version: {sys.version.split()[0]}")
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
        print(f"PyInstaller version: {PyInstaller.__version__}")
    except ImportError:
        print("\nError: PyInstaller is not installed!")
        print("Install it with: pip install pyinstaller")
        return 1
    
    # Clean previous builds
    clean_build()
    
    # Check required files
    if not check_files():
        print("\nBuild cannot continue - missing required files!")
        return 1
    
    # Build executable
    print("\n" + "=" * 60)
    print("Building executable...")
    print("=" * 60)
    if not build_exe():
        print("\nBuild failed! Check the error messages above.")
        return 1
    
    # Create distribution
    print("\n" + "=" * 60)
    print("Creating distribution package...")
    print("=" * 60)
    if not create_distribution():
        print("\nDistribution creation failed!")
        return 1
    
    print("\n" + "=" * 60)
    print("   Build Completed Successfully!")
    print("=" * 60)
    print("\nOutput files:")
    print(f"  - Executable: dist/PrintQue.exe")
    print(f"  - Distribution folder: dist/PrintQue_Windows_{datetime.now().strftime('%Y%m%d')}/")
    print(f"  - Zip package: dist/PrintQue_Windows_{datetime.now().strftime('%Y%m%d')}.zip")
    print("\nTo test the executable:")
    print("  1. Navigate to: dist/PrintQue_Windows_{datetime.now().strftime('%Y%m%d')}/")
    print("  2. Double-click: Start_PrintQue.bat")
    print("  3. Open browser to: http://localhost:5000")
    print("\nNote: First run may be slow as Windows Defender scans the file.")
    print("=" * 60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())