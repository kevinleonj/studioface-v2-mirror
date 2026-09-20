"""Add a Secret Manager version from a hidden prompt. Usage: python scripts/set_secret.py <name>"""

import getpass
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

name = sys.argv[1]
value = getpass.getpass(f"{name}: ")
subprocess.run(
    ["gcloud", "secrets", "versions", "add", name, "--data-file=-"],
    input=value,
    text=True,
    check=True,
)
print(f"{name}: version added")
