import gzip
import hashlib
import json
import shutil
import time
from contextlib import contextmanager
from pathlib import Path

APP_CACHE_DIR = Path.home() / ".cache" / "kylin-server-rpm-search"
CACHE_SCHEMA_VERSION = 3


def _cache_path(namespace, key):
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return APP_CACHE_DIR / namespace / f"v{CACHE_SCHEMA_VERSION}-{digest}.jsonl.gz"


def cache_is_valid(namespace, key, max_age_seconds):
    path = _cache_path(namespace, key)
    return (
        max_age_seconds > 0
        and path.exists()
        and time.time() - path.stat().st_mtime <= max_age_seconds
    )


def iter_cache_items(namespace, key, max_age_seconds):
    path = _cache_path(namespace, key)
    if not cache_is_valid(namespace, key, max_age_seconds):
        return
    try:
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line in stream:
                if line.strip():
                    yield json.loads(line)
    except (OSError, ValueError, TypeError):
        path.unlink(missing_ok=True)
        return


@contextmanager
def cache_writer(namespace, key, enabled=True):
    if not enabled:
        yield None
        return
    path = _cache_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    stream = None
    try:
        stream = gzip.open(temporary, "wt", encoding="utf-8")
        yield stream
        stream.close()
        stream = None
        temporary.replace(path)
    except Exception:
        if stream is not None:
            stream.close()
        temporary.unlink(missing_ok=True)
        raise


def write_cache_item(stream, value):
    if stream is not None:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")


def clear_cache():
    if APP_CACHE_DIR.exists():
        shutil.rmtree(APP_CACHE_DIR)
