import os

DB_FOLDER = 'db'
os.makedirs('db', exist_ok=True)

CONSOLE_LOG = True
SCAN_INTERVAL = 60

# OAuth login
CLIENT_ID = os.getenv('CLIENT_ID')
REDIRECT_URL = 'http://127.0.0.1:8080'
SCOPES = 'project.read asset.create offline asset.read team.read account.read asset.delete'

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
