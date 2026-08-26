import gzip
import hashlib
import json
import shutil
import time
from pathlib import Path

APP_CACHE_DIR = Path.home() / ".cache" / "kylin-server-rpm-search"


def _cache_path(namespace, key):
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return APP_CACHE_DIR / namespace / f"{digest}.json.gz"


def load_cache(namespace, key, max_age_seconds):
    path = _cache_path(namespace, key)
    if max_age_seconds <= 0 or not path.exists():
        return None
    if time.time() - path.stat().st_mtime > max_age_seconds:
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError, TypeError):
        return None


def save_cache(namespace, key, value):
    path = _cache_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    with gzip.open(temporary, "wt", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
    temporary.replace(path)


def clear_cache():
    if APP_CACHE_DIR.exists():
        shutil.rmtree(APP_CACHE_DIR)
