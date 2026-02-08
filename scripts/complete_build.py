#!/usr/bin/env python
"""
Legacy complete build script with all dependencies for PrintQue.
For current builds use: python scripts/build.py

Run from repository root. Uses ROOT_DIR for build/dist; runs PyInstaller from api/.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

# Repo root (script lives in scripts/)
ROOT_DIR = Path(__file__).resolve().parent.parent
API_DIR = ROOT_DIR / "api"


def create_spec_file():
    """Create a comprehensive spec file with all dependencies"""
    spec_content = '''# -*- mode: python ; coding: utf-8 -*-
import sys
import os
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None

# Collect all dependencies
datas = []
binaries = []
hiddenimports = []

# Flask and all extensions
for package in ['flask', 'flask_socketio', 'jinja2', 'click', 'itsdangerous', 'werkzeug', 'markupsafe']:
    tmp_ret = collect_all(package)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

# Socket.IO and Engine.IO
for package in ['socketio', 'engineio', 'python_socketio', 'python_engineio']:
    try:
        hiddenimports += collect_submodules(package)
    except:
        pass

# Other critical packages
packages_to_collect = [
    'eventlet',
    'eventlet.green',
    'eventlet.green.subprocess',
    'eventlet.green.ssl',
    'eventlet.green.threading',
    'eventlet.hubs',
    'dns',
    'dns.resolver',
    'cryptography',
    'cryptography.fernet',
    'aiohttp',
    'aiofiles',
    'requests',
    'urllib3',
    'certifi',
    'psutil',
    'simple_websocket',
    'bidict',
    'greenlet'
]

for package in packages_to_collect:
    try:
        hiddenimports.append(package)
    except:
        pass

# Add specific imports that are often missed
hiddenimports += [
    'engineio.async_drivers.threading',
    'engineio.async_drivers.eventlet',
    'flask.json.provider',
    'flask.json.tag',
    'flask.logging',
    'flask.templating',
    'flask.signals',
    'flask_socketio',
    'eventlet.wsgi',
    'eventlet.websocket',
    'werkzeug.routing',
    'werkzeug.serving',
    'jinja2.ext',
    'dns.rdataclass',
    'dns.rdatatype',
    'dns.exception',
    'six',
    'six.moves',
    'six.moves.urllib',
    'six.moves.urllib.parse',
    'pkg_resources',
    'pkg_resources.extern',
    'bambu_handler',
    'paho',
    'paho.mqtt',
    'paho.mqtt.client',
]

# Add your project files and folders (paths relative to api_dir / cwd)
datas += [
    ('templates', 'templates'),
    ('static', 'static') if os.path.exists('static') else ('templates', '.'),
    ('requirements.txt', '.'),
]

# Add all your Python modules
your_modules = [
    'routes',
    'state',
    'printer_manager',
    'config',
    'printer_routes',
    'order_routes',
    'misc_routes',
    'retry_utils',
    'default_settings',
    'utils',
    'bambu_handler',
]

for module in your_modules:
    if os.path.exists(f'{module}.py'):
        hiddenimports.append(module)

a = Analysis(
    ['run_app.py'],
    pathex=[os.path.abspath('.')],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'numpy', 'pandas', 'scipy', 'PIL', 'tkinter'],
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
    icon='printque.ico' if os.path.exists('printque.ico') else None
)
'''
    
    spec_file = API_DIR / 'PrintQue_Complete.spec'
    spec_file.write_text(spec_content)
    print("Created PrintQue_Complete.spec")


def build_exe():
    """Build the executable"""
    print("\nBuilding PrintQue.exe with all dependencies...")
    
    packages = [
        'flask', 'flask-socketio', 'eventlet', 'python-socketio',
        'python-engineio', 'werkzeug', 'jinja2', 'cryptography',
        'aiohttp', 'requests', 'psutil',
        'simple-websocket', 'dnspython', 'paho-mqtt'
    ]
    for package in packages:
        result = subprocess.run([sys.executable, '-m', 'pip', 'show', package],
                                capture_output=True, text=True, cwd=str(ROOT_DIR))
        if result.returncode != 0:
            print(f"Installing missing package: {package}")
            subprocess.run([sys.executable, '-m', 'pip', 'install', package], cwd=str(ROOT_DIR))
    
    create_spec_file()
    
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        str(API_DIR / 'PrintQue_Complete.spec'),
        '--clean', '-y',
        '--distpath', str(ROOT_DIR / 'dist'),
        '--workpath', str(ROOT_DIR / 'build'),
    ]
    try:
        print("\nRunning PyInstaller...")
        result = subprocess.run(cmd, cwd=str(API_DIR), check=False)
        if result.returncode == 0:
            print("\nBuild completed successfully!")
            exe_path = ROOT_DIR / 'dist' / 'PrintQue.exe'
            if exe_path.exists():
                batch_content = """@echo off
title PrintQue Server
echo Starting PrintQue Server...
echo.
echo The application will open in your default browser at http://localhost:5000
echo If it doesn't open automatically, please navigate to http://localhost:5000
echo.
echo To stop the server, press Ctrl+C in this window.
echo.
cd /d "%~dp0"
PrintQue.exe
pause
"""
                (ROOT_DIR / 'dist' / 'Start_PrintQue.bat').write_text(batch_content)
                if (API_DIR / 'templates').exists():
                    dest = ROOT_DIR / 'dist' / 'templates'
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(API_DIR / 'templates', dest)
                    print("Copied templates folder")
                print("\n" + "="*60)
                print("BUILD SUCCESSFUL!")
                print("="*60)
                print(f"\nOutput: {ROOT_DIR / 'dist'}")
            else:
                print("\nError: PrintQue.exe was not created!")
        else:
            print(f"\nBuild failed with return code: {result.returncode}")
    except Exception as e:
        print(f"\nBuild error: {str(e)}")


def main():
    print("="*60)
    print("PrintQue Complete Build Script (legacy)")
    print("Prefer: python scripts/build.py")
    print("="*60)
    
    print("\nCleaning old builds...")
    for folder in [ROOT_DIR / 'build', ROOT_DIR / 'dist']:
        if folder.exists():
            shutil.rmtree(folder)
            print(f"Removed {folder}")
    
    build_exe()


if __name__ == "__main__":
    main()
