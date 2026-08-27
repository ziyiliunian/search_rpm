import bz2
import gzip
import ctypes
import ctypes.util
import lzma
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .cache import load_cache, save_cache

USER_AGENT = "kylin-server-rpm-search/1.2.0"


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


class _IndexParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            if href and href not in ("../", "./"):
                self.links.append(href)


def fetch_bytes(url, timeout=30):
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def list_directory(url, cache_seconds=86400):
    cached = load_cache("directories", url, cache_seconds)
    if cached is not None:
        return [(item[0], item[1]) for item in cached]
    parser = _IndexParser()
    parser.feed(fetch_bytes(url).decode("utf-8", "replace"))
    entries = [(href.rstrip("/"), urljoin(url, href)) for href in parser.links]
    if cache_seconds > 0:
        save_cache("directories", url, entries)
    return entries


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
    if size in (0, 2**64 - 1, 2**64 - 2) or size > 1024 * 1024 * 1024:
        raise ValueError("Zstandard 元数据缺少安全的解压长度")
    destination = ctypes.create_string_buffer(size)
    result = library.ZSTD_decompress(destination, size, source, len(raw))
    if library.ZSTD_isError(result):
        raise ValueError("Zstandard 元数据解压失败")
    return destination.raw[:result]


def _decompress(raw):
    if raw.startswith(b"\x1f\x8b"):
        return gzip.decompress(raw)
    if raw.startswith(b"BZh"):
        return bz2.decompress(raw)
    if raw.startswith(b"\xfd7zXZ\x00"):
        return lzma.decompress(raw)
    if raw.startswith(b"\x28\xb5\x2f\xfd"):
        return _zstd_decompress(raw)
    return raw


def _primary_from_repomd(base_url):
    repomd_url = urljoin(base_url.rstrip("/") + "/", "repodata/repomd.xml")
    root = ET.fromstring(fetch_bytes(repomd_url))
    primary_href = None
    for data in root:
        if data.attrib.get("type") == "primary":
            for child in data:
                if _local(child.tag) == "location":
                    primary_href = child.attrib.get("href")
                    break
    if not primary_href:
        raise ValueError("repomd.xml 中没有 primary 元数据")
    raw = fetch_bytes(urljoin(base_url.rstrip("/") + "/", primary_href))
    return ET.fromstring(_decompress(raw))


def load_packages(base_url, repo_name, cache_seconds=86400):
    cache_key = f"{repo_name}|{base_url}"
    cached = load_cache("packages", cache_key, cache_seconds)
    if cached is not None:
        return [RepoEntry(**item) for item in cached]

    root = _primary_from_repomd(base_url)
    packages = []
    for package in root.iter():
        if _local(package.tag) != "package":
            continue
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
        if values.get("name") and location:
            packages.append(RepoEntry(
                values["name"], values.get("ver", ""), values.get("rel", ""),
                values.get("arch", ""), repo_name,
                urljoin(base_url.rstrip("/") + "/", location),
                values.get("summary", ""), checksum_type, checksum, size,
            ))
    if cache_seconds > 0:
        save_cache("packages", cache_key, [asdict(package) for package in packages])
    return packages


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


def search_packages(packages, name_query="", version_query="", imported_names=None):
    queries = [query.strip() for query in (imported_names or []) if query.strip()]
    if name_query.strip():
        queries.append(name_query.strip())

    def name_matches(package_name):
        return not queries or any(_matches(package_name, query) for query in queries)

    results = [
        package for package in packages
        if name_matches(package.name)
        and _matches(f"{package.version}-{package.release}", version_query)
    ]
    return sorted(
        results,
        key=lambda package: (
            package.repo.lower(),
            rpm_version_key(f"{package.epoch}:{package.version}-{package.release}"),
            package.name.lower(),
        ),
    )
