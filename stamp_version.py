"""Writes version.py with a build-timestamp version. Run before every build."""
import datetime as dt
import os

version = dt.datetime.now().strftime("%Y.%m.%d-%H%M")
path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "version.py")
with open(path, "w", encoding="utf-8") as f:
    f.write(f'VERSION = "{version}"\n')
print(f"Stamped version {version}")
