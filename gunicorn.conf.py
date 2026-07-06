import multiprocessing
import os


bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
worker_class = "gthread"

# Two processes isolate failures; threads keep uploads/OpenAI calls responsive.
# Override these values from Render without changing the repository.
workers = max(1, min(4, int(os.getenv("WEB_CONCURRENCY", "2"))))
threads = max(2, min(8, int(os.getenv("GUNICORN_THREADS", "4"))))

# Large scanned textbooks need extra time for upload, page inspection, and OCR fallback.
# A legacy Render value of 180 seconds is automatically raised to 240 seconds.
_requested_timeout = int(os.getenv("GUNICORN_TIMEOUT", "240"))
timeout = max(240, min(300, _requested_timeout))
graceful_timeout = 30
keepalive = 5

# Recycle workers gradually to release memory after repeated DOCX/PDF jobs.
max_requests = max(100, int(os.getenv("GUNICORN_MAX_REQUESTS", "250")))
max_requests_jitter = max(0, int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "40")))

# Faster temporary request bodies on Linux/Render.
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None

accesslog = "-"
errorlog = "-"
capture_output = True
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

# Do not preload: each worker should open its own SQLite/diskcache connection.
preload_app = False
