import os
import platform

DB_FOLDER = 'db'
os.makedirs('db', exist_ok=True)

CONSOLE_LOG = True
SCAN_INTERVAL = 60

# OAuth login
# Default CLIENT_ID configured by m@maxstr.se. 
# Supports redirect urls http://127.0.0.1:5111 and http://127.0.0.1:8080.
CLIENT_ID = os.getenv('CLIENT_ID', '24a75470-e2e5-45c7-80dc-ac306c1d7875')
REDIRECT_URL = 'http://127.0.0.1:5111'
SCOPES = 'project.read asset.create offline asset.read team.read account.read asset.delete'

TELEMETRY_HEADERS = {
    "x-vendor-name": os.getenv("VENDOR", "@strombergdev"),
    "x-client-name": os.getenv("CLIENT_NAME", "frameio-python-sync"),
    "x-client-version": os.getenv("VERSION", "1.0.4"),
    "x-platform": os.getenv("PLATFORM", platform.system())
}

# Cache variables used for storing active Frame.io client.
authenticated_client = None
client_expires = 0


class SyncSetting:
    ASSETS_FRAMEIO_TO_LOCAL = True
    ASSETS_LOCAL_TO_FRAME = True


SYSTEM_FOLDERS = [
    "#recycle",
    "@eaDir",
    "bin",
    "config",
    "dev",
    "etc",
    "etc.defaults",
    "initrd",
    "lib",
    "lost+found",
    "mnt",
    "proc",
    "root",
    "run",
    "sbin",
    "sys",
    "tmp",
    "usr",
    "var",
    "var.defaults",
    "cores",
    "sbin",
    "Library",
    "private",
    "opt",
    "System",
]
