import bz2
import ctypes
import ctypes.util
import gzip
import io
import lzma
import posixpath
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import Request, urlopen

from .cache import (
    cache_is_valid, cache_writer, iter_cache_items, write_cache_item,
)

USER_AGENT = "kylin-server-rpm-search/1.6.3"
MAX_REPOMD_BYTES = 4 * 1024 * 1024
MAX_COMPRESSED_METADATA_BYTES = 256 * 1024 * 1024
MAX_DECOMPRESSED_METADATA_BYTES = 512 * 1024 * 1024


@dataclass
class RepoEntry:
    name: str
    version: str
    release: str
    arch: str
    repo: str
    url: str
    summary: str = ""
    checksum_type: str = ""
    checksum: str = ""
    size: int = 0
    epoch: str = "0"

    @property
    def nevra(self):
        return f"{self.name}-{self.version}-{self.release}.{self.arch}"


class _DirectoryParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href and href not in ("../", "./"):
                self.links.append(href)


def fetch_bytes(url, timeout=30, max_bytes=MAX_COMPRESSED_METADATA_BYTES):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("仓库地址必须是有效 HTTPS URL")
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        content_length = int(response.headers.get("Content-Length", 0))
        if content_length > max_bytes:
            raise ValueError("仓库元数据超过允许大小")
        chunks = []
        received = 0
        while True:
            chunk = response.read(min(1024 * 1024, max_bytes - received + 1))
            if not chunk:
                break
            received += len(chunk)
            if received > max_bytes:
                raise ValueError("仓库元数据超过允许大小")
            chunks.append(chunk)
        return b"".join(chunks)


def _safe_repository_url(base_url, href):
    base = urlsplit(base_url.rstrip("/") + "/")
    target = urlsplit(urljoin(base.geturl(), href))
    normalized_path = posixpath.normpath(unquote(target.path))
    base_path = posixpath.normpath(unquote(base.path))
    if target.scheme != "https" or target.netloc != base.netloc:
        raise ValueError("仓库元数据地址越界")
    if normalized_path != base_path and not normalized_path.startswith(base_path.rstrip("/") + "/"):
        raise ValueError("仓库元数据路径越界")
    return target.geturl()


def list_directory(url, cache_seconds=86400):
    cache_key = f"directory|{url}"
    if cache_is_valid("directories", cache_key, cache_seconds):
        return [item["name"] for item in iter_cache_items("directories", cache_key, cache_seconds)]
    parser = _DirectoryParser()
    parser.feed(fetch_bytes(url, max_bytes=4 * 1024 * 1024).decode("utf-8", "replace"))
    names = []
    seen = set()
    with cache_writer("directories", cache_key, cache_seconds > 0) as stream:
        for href in parser.links:
            if not href.endswith("/"):
                continue
            try:
                safe_url = _safe_repository_url(url, href)
            except ValueError:
                continue
            if safe_url.rstrip("/") == url.rstrip("/"):
                continue
            name = PurePosixPath(urlsplit(safe_url).path.rstrip("/")).name
            if name and name not in seen:
                seen.add(name)
                names.append(name)
                write_cache_item(stream, {"name": name})
    return names


def has_repomd(url):
    try:
        fetch_bytes(
            _safe_repository_url(url, "repodata/repomd.xml"),
            timeout=15,
            max_bytes=MAX_REPOMD_BYTES,
        )
        return True
    except Exception:
        return False


def discover_repositories(root_url, max_depth=5, cache_seconds=86400):
    root = root_url.rstrip("/") + "/"
    discovered = []
    visited = set()

    def visit(url, depth, parts):
        if url in visited or depth > max_depth:
            return
        visited.add(url)
        if has_repomd(url):
            discovered.append((tuple(parts), url))
            return
        if depth == max_depth:
            return
        try:
            names = list_directory(url, cache_seconds)
        except Exception:
            return
        for name in names:
            try:
                child_url = _safe_repository_url(url, name + "/")
            except ValueError:
                continue
            visit(child_url, depth + 1, parts + [name])

    visit(root, 0, [])
    return discovered


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _zstd_decompress(raw):
    library_name = ctypes.util.find_library("zstd")
    if not library_name:
        raise RuntimeError("解析 V11 仓库需要系统 libzstd")
    library = ctypes.CDLL(library_name)
    library.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    library.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
    library.ZSTD_decompressBound.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    library.ZSTD_decompressBound.restype = ctypes.c_ulonglong
    library.ZSTD_decompress.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t]
    library.ZSTD_decompress.restype = ctypes.c_size_t
    library.ZSTD_isError.argtypes = [ctypes.c_size_t]
    library.ZSTD_isError.restype = ctypes.c_uint
    source = ctypes.create_string_buffer(raw)
    size = library.ZSTD_getFrameContentSize(source, len(raw))
    if size == 2**64 - 1:
        size = library.ZSTD_decompressBound(source, len(raw))
    if size in (0, 2**64 - 1, 2**64 - 2) or size > MAX_DECOMPRESSED_METADATA_BYTES:
        raise ValueError("Zstandard 元数据缺少安全的解压长度")
    destination = ctypes.create_string_buffer(size)
    result = library.ZSTD_decompress(destination, size, source, len(raw))
    if library.ZSTD_isError(result):
        raise ValueError("Zstandard 元数据解压失败")
    return destination.raw[:result]


def _bounded_stream_decompress(raw, opener):
    output = bytearray()
    with opener(io.BytesIO(raw)) as stream:
        while True:
            chunk = stream.read(min(1024 * 1024, MAX_DECOMPRESSED_METADATA_BYTES - len(output) + 1))
            if not chunk:
                return bytes(output)
            output.extend(chunk)
            if len(output) > MAX_DECOMPRESSED_METADATA_BYTES:
                raise ValueError("仓库元数据解压后超过允许大小")


def _decompress(raw):
    if raw.startswith(b"\x1f\x8b"):
        return _bounded_stream_decompress(
            raw, lambda stream: gzip.GzipFile(fileobj=stream, mode="rb")
        )
    if raw.startswith(b"BZh"):
        return _bounded_stream_decompress(
            raw, lambda stream: bz2.BZ2File(stream, mode="rb")
        )
    if raw.startswith(b"\xfd7zXZ\x00"):
        return _bounded_stream_decompress(
            raw, lambda stream: lzma.LZMAFile(stream, mode="rb")
        )
    if raw.startswith(b"\x28\xb5\x2f\xfd"):
        return _zstd_decompress(raw)
    if len(raw) > MAX_DECOMPRESSED_METADATA_BYTES:
        raise ValueError("仓库元数据超过允许大小")
    return raw


def _primary_bytes_from_repomd(base_url):
    repomd_url = _safe_repository_url(base_url, "repodata/repomd.xml")
    root = ET.fromstring(fetch_bytes(repomd_url, max_bytes=MAX_REPOMD_BYTES))
    primary_href = None
    for data in root:
        if data.attrib.get("type") == "primary":
            for child in data:
                if _local(child.tag) == "location":
                    primary_href = child.attrib.get("href")
                    break
    if not primary_href:
        raise ValueError("repomd.xml 中没有 primary 元数据")
    primary_url = _safe_repository_url(base_url, primary_href)
    raw = fetch_bytes(primary_url, max_bytes=MAX_COMPRESSED_METADATA_BYTES)
    return _decompress(raw)


def _entry_from_package(package, base_url, repo_name):
    values = {}
    location = ""
    checksum_type = ""
    checksum = ""
    size = 0
    for child in package:
        key = _local(child.tag)
        if key in ("name", "arch", "summary"):
            values[key] = (child.text or "").strip()
        elif key == "version":
            values.update(child.attrib)
        elif key == "location":
            location = child.attrib.get("href", "")
        elif key == "checksum" and child.attrib.get("pkgid") == "YES":
            checksum_type = child.attrib.get("type", "")
            checksum = (child.text or "").strip()
        elif key == "size":
            try:
                size = int(child.attrib.get("package", 0))
            except (TypeError, ValueError):
                size = 0
    if not values.get("name") or not location or not checksum_type or not checksum:
        return None
    return RepoEntry(
        values["name"], values.get("ver", ""), values.get("rel", ""),
        values.get("arch", ""), repo_name, _safe_repository_url(base_url, location),
        values.get("summary", ""), checksum_type, checksum, size,
        values.get("epoch", "0"),
    )


def iter_packages(base_url, repo_name, cache_seconds=86400):
    cache_key = f"{repo_name}|{base_url}"
    if cache_is_valid("packages", cache_key, cache_seconds):
        for item in iter_cache_items("packages", cache_key, cache_seconds):
            entry = RepoEntry(**item)
            if not entry.checksum_type or not entry.checksum:
                continue
            _safe_repository_url(base_url, entry.url)
            yield entry
        return

    primary_bytes = _primary_bytes_from_repomd(base_url)
    with cache_writer("packages", cache_key, cache_seconds > 0) as stream:
        for _, package in ET.iterparse(io.BytesIO(primary_bytes), events=("end",)):
            if _local(package.tag) != "package":
                continue
            entry = _entry_from_package(package, base_url, repo_name)
            package.clear()
            if entry is not None:
                write_cache_item(stream, asdict(entry))
                yield entry


def load_packages(base_url, repo_name, cache_seconds=86400):
    return list(iter_packages(base_url, repo_name, cache_seconds))


def parse_rpm_filename(url, repo_name):
    filename = PurePosixPath(url.split("?")[0]).name
    if not filename.endswith(".rpm"):
        return None
    stem = filename[:-4]
    try:
        left, arch = stem.rsplit(".", 1)
        name, version, release = left.rsplit("-", 2)
    except ValueError:
        return None
    return RepoEntry(name, version, release, arch, repo_name, url)


def _matches(value, query):
    query = query.strip().lower()
    if not query or query == "*":
        return True
    if any(character in query for character in "*?"):
        return fnmatchcase(value.lower(), query)
    return query in value.lower()


def rpm_version_key(value):
    parts = re.findall(r"[0-9]+|[A-Za-z]+", value)
    return tuple((0, int(part)) if part.isdigit() else (1, part.lower()) for part in parts)


def parse_package_names(text):
    names = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.extend(token for token in re.split(r"[\s,;，；]+", line) if token)
    return list(dict.fromkeys(names))


def package_matches(package, name_query="", version_query="", imported_names=None):
    queries = [query.strip() for query in (imported_names or []) if query.strip()]
    if name_query.strip():
        queries.append(name_query.strip())

    def query_matches(query):
        normalized = query.strip().lower()
        rpm_filename = PurePosixPath(package.url.split("?", 1)[0]).name.lower()
        nevra = package.nevra.lower()
        exact_names = {
            nevra, rpm_filename,
            rpm_filename[:-4] if rpm_filename.endswith(".rpm") else rpm_filename,
        }
        if normalized in exact_names:
            return True
        if any(character in normalized for character in "*?"):
            return any(fnmatchcase(candidate, normalized) for candidate in (package.name.lower(), nevra, rpm_filename))
        if re.search(r"\.(?:noarch|src|aarch64|x86_64|loongarch64|sw_64|ppc64le)$", normalized):
            return False
        return normalized in package.name.lower()

    return (
        (not queries or any(query_matches(query) for query in queries))
        and _matches(f"{package.version}-{package.release}", version_query)
    )


def search_packages(packages, name_query="", version_query="", imported_names=None):
    results = [
        package for package in packages
        if package_matches(package, name_query, version_query, imported_names)
    ]
    return sorted(
        results,
        key=lambda package: (
            package.repo.lower(),
            rpm_version_key(f"{package.epoch}:{package.version}-{package.release}"),
            package.name.lower(),
        ),
    )
