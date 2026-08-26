from pathlib import Path
from urllib.request import Request, urlopen


def download_package(entry, destination, progress=None):
    target_dir = Path(destination)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / entry.url.rstrip("/").split("/")[-1]
    request = Request(entry.url, headers={"User-Agent": "search-rpm/0.1"})
    with urlopen(request, timeout=60) as response, target.with_suffix(target.suffix + ".part").open("wb") as output:
        total = int(response.headers.get("Content-Length", 0))
        received = 0
        while True:
            chunk = response.read(1024 * 256)
            if not chunk:
                break
            output.write(chunk)
            received += len(chunk)
            if progress:
                progress(received, total)
    target.with_suffix(target.suffix + ".part").replace(target)
    return str(target)
