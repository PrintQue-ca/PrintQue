import sys
from cx_Freeze import setup, Executable

build_exe_options = {
    "packages": ["os", "flask", "flask_socketio"],
    "excludes": [],
    "include_files": []
}

base = None
if sys.platform == "win32":
    base = "Win32GUI"

setup(
    name="PrintQue",
    version="1.0",
    description="PrintQue 3D Printer Management",
    options={"build_exe": build_exe_options},
    executables=[Executable("app.py", base=base)]
)