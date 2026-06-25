

#gcloud run services update olaiprojectv4 --region=europe-north1 --add-volume=name=storage-vol,type=cloud-storage,bucket=olaiproject_price_data --add-volume-mount=volume=storage-vol,mount-path=/mnt/storage


import os

# --- ENVIRONMENT DETECTION ---
IS_CLOUD = "K_SERVICE" in os.environ

BASE_STORAGE = "/mnt/storage" if IS_CLOUD else "/app"
WATCHLIST_PATH = os.path.join(BASE_STORAGE, "WATCHLIST.xlsx")
TECHNICAL_FILE = os.path.join(BASE_STORAGE, "TECHNICAL.xlsx")
DASHBOARD_FILE = os.path.join(BASE_STORAGE, "matrix_dashboard.html")
NEWSWEB_DIR = os.path.join(BASE_STORAGE, "newsweb")
OSLOBORS_DIR = os.path.join(BASE_STORAGE, "oslobors")
GRAPHS_DIR = os.path.join(BASE_STORAGE, "visuals", "graphs")
SPARKLINES_DIR = os.path.join(BASE_STORAGE, "visuals", "newssparklines")


def ensure_local_directories():
        if not IS_CLOUD:
            for directory in (NEWSWEB_DIR, OSLOBORS_DIR, GRAPHS_DIR, SPARKLINES_DIR):
                os.makedirs(directory, exist_ok=True)
