import hashlib
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

USER_AGENT = "kylin-server-rpm-search/1.5.0"


def download_package(entry, destination, progress=None, resume_event=None):
    target_dir = Path(destination).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    parsed_url = urlsplit(entry.url)
    if parsed_url.scheme != "https" or not parsed_url.hostname:
        raise ValueError("RPM 下载地址必须是有效 HTTPS URL")
    filename = Path(parsed_url.path).name
    if not filename:
        raise ValueError("下载地址中没有有效文件名")
    if not entry.checksum_type or not entry.checksum:
        raise ValueError("仓库未提供 RPM 摘要，拒绝不安全下载")
    target = target_dir / filename
    temporary = target.with_suffix(target.suffix + ".part")
    request = Request(entry.url, headers={"User-Agent": USER_AGENT})
    try:
        digest = hashlib.new(entry.checksum_type)
    except ValueError as exc:
        raise ValueError("仓库使用了不支持的 RPM 摘要算法") from exc

    try:
        with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            expected = entry.size or int(response.headers.get("Content-Length", 0))
            received = 0
            while True:
                if resume_event is not None:
                    resume_event.wait()
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output.write(chunk)
                if digest:
                    digest.update(chunk)
                received += len(chunk)
                if progress:
                    progress(received, expected)
        if expected and received != expected:
            raise IOError(f"文件长度校验失败：应为 {expected} 字节，实际 {received} 字节")
        if digest and entry.checksum and digest.hexdigest().lower() != entry.checksum.lower():
            raise IOError("文件摘要校验失败")
        temporary.replace(target)
        return str(target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
