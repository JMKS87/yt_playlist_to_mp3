import os
import tempfile

_project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# W kontenerze ścieżki przychodzą z env (/data/output, /data/config/app.db);
# domyślne wartości wskazują na ./data w katalogu projektu, żeby lokalny dev działał bez konfiguracji.
OUTPUT_ROOT = os.path.abspath(os.environ.get("OUTPUT_ROOT", os.path.join(_project_dir, "data", "output")))
DB_PATH = os.path.abspath(os.environ.get("DB_PATH", os.path.join(_project_dir, "data", "config", "app.db")))
# Tu yt-dlp pobiera i konwertuje; do OUTPUT_ROOT trafia dopiero gotowy plik. Czyszczony przy starcie workera.
TEMP_DIR = os.path.abspath(os.environ.get("TEMP_DIR", os.path.join(tempfile.gettempdir(), "yt2mp3")))

QUALITIES = (64, 96, 128, 192, 256, 320)
DEFAULT_QUALITY = int(os.environ.get("DEFAULT_QUALITY", "64"))
DEFAULT_OUT_DIR = os.environ.get("DEFAULT_OUT_DIR", "default")

# Co ile sekund worker sprawdza kolejkę, jeśli nikt go nie obudził.
WORKER_POLL_SECONDS = 5
