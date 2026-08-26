from dataclasses import dataclass
from fnmatch import fnmatchcase
from html.parser import HTMLParser
from pathlib import PurePosixPath
from urllib.parse import urljoin
from urllib.request import Request, urlopen
import gzip
import xml.etree.ElementTree as ET


@dataclass
class RepoEntry:
    name: str
    version: str
    release: str
    arch: str
    repo: str
    url: str
    summary: str = ""

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


def fetch_text(url):
    request = Request(url, headers={"User-Agent": "search-rpm/0.1"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def list_directory(url):
    parser = _IndexParser()
    parser.feed(fetch_text(url).decode("utf-8", "replace"))
    return [(href.rstrip("/"), urljoin(url, href)) for href in parser.links]


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _primary_from_repomd(base_url):
    repomd_url = urljoin(base_url.rstrip("/") + "/", "repodata/repomd.xml")
    root = ET.fromstring(fetch_text(repomd_url))
    primary_href = None
    for data in root:
        if data.attrib.get("type") == "primary":
            for child in data:
                if _local(child.tag) == "location":
                    primary_href = child.attrib.get("href")
                    break
    if not primary_href:
        raise ValueError("repomd.xml 中没有 primary 元数据")
    raw = fetch_text(urljoin(base_url.rstrip("/") + "/", primary_href))
    if primary_href.endswith(".gz"):
        raw = gzip.decompress(raw)
    return ET.fromstring(raw)


def load_packages(base_url, repo_name):
    root = _primary_from_repomd(base_url)
    packages = []
    for package in root.iter():
        if _local(package.tag) != "package":
            continue
        values = {}
        location = ""
        for child in package:
            key = _local(child.tag)
            if key in ("name", "arch", "summary"):
                values[key] = (child.text or "").strip()
            elif key == "version":
                values.update(child.attrib)
            elif key == "location":
                location = child.attrib.get("href", "")
        if values.get("name") and location:
            packages.append(RepoEntry(values["name"], values.get("ver", ""), values.get("rel", ""), values.get("arch", ""), repo_name, urljoin(base_url.rstrip("/") + "/", location), values.get("summary", "")))
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


def search_packages(packages, name_query="", version_query="", repo_query=""):
    def matches(value, query):
        query = query.strip().lower()
        if not query or query == "*":
            return True
        return fnmatchcase(value.lower(), query) if any(c in query for c in "*?") else query in value.lower()
    return [p for p in packages if matches(p.name, name_query) and matches(f"{p.version}-{p.release}", version_query) and matches(p.repo, repo_query)]
