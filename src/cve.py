import json
import re
from html.parser import HTMLParser
from urllib.request import Request, urlopen

CVE_API_URL = "https://support.kylinos.cn/protalweb/security/cve/info"
CVE_PAGE_URL = "https://support.kylinos.cn/#/security/cveDetail?allTitle={}"
USER_AGENT = "search_rpm/1.7.0"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
STATUS_NAMES = {
    "0": "不影响", "1": "处理中", "2": "已修复", "3": "不计划修复",
    "4": "不影响", "5": "超出支持范围",
}
RISK_NAMES = {
    "Critical": "严重 Critical", "High": "高 High", "Medium": "中 Medium",
    "Low": "低 Low", "None": "无 None",
}


class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"p", "div", "h1", "h2", "h3", "h4", "h5", "li", "br"}:
            self.parts.append("\n")

    def handle_data(self, data):
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self):
        value = "".join(self.parts)
        return re.sub(r"\n{3,}", "\n\n", value).strip()


def html_to_text(value):
    if not value:
        return ""
    parser = _TextParser()
    parser.feed(str(value))
    return parser.text()


def normalize_cve_id(value):
    cve_id = value.strip().upper()
    if not re.fullmatch(r"CVE-\d{4}-\d{4,}", cve_id):
        raise ValueError("请输入有效的 CVE 编号，例如 CVE-2026-16389")
    return cve_id


def _read_limited(response):
    length = int(response.headers.get("Content-Length", 0))
    if length > MAX_RESPONSE_BYTES:
        raise ValueError("CVE 响应数据超过允许大小")
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("CVE 响应数据超过允许大小")
    return data


def query_cve(value):
    cve_id = normalize_cve_id(value)
    body = json.dumps({"allTitle": cve_id}).encode("utf-8")
    request = Request(
        CVE_API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    with urlopen(request, timeout=45) as response:
        payload = json.loads(_read_limited(response).decode("utf-8"))
    if str(payload.get("resultCode")) != "0":
        raise RuntimeError(payload.get("message") or "麒麟 CVE 服务返回错误")
    data = payload.get("obj")
    if not isinstance(data, dict) or not data.get("all_title"):
        raise LookupError(f"未查询到 {cve_id} 的漏洞信息")
    scores = []
    for item in data.get("cvss_info_list") or []:
        scores.append({
            "provider": str(item.get("provider") or ""),
            "score": str(item.get("score") or ""),
            "vector": str(item.get("value") or ""),
        })
    products = []
    for item in data.get("product_relation_list") or []:
        products.append({
            "product_name": str(item.get("product_name") or ""),
            "state": STATUS_NAMES.get(str(item.get("state") or ""), str(item.get("state") or "")),
        })
    components = []
    for item in data.get("product_component_list") or []:
        product = item.get("product_info") or {}
        components.append({
            "product": str(product.get("product_name") or product.get("product_nick_name") or ""),
            "component": str(item.get("component_name") or item.get("src_name") or ""),
            "version": str(item.get("version") or ""),
            "architecture": str(item.get("framework") or ""),
            "status": STATUS_NAMES.get(str(item.get("status") or ""), str(item.get("status") or "")),
            "security_advisory": str(item.get("sa_no") or item.get("announcement_no") or ""),
            "release_date": str(item.get("release_date") or item.get("update_date") or ""),
            "source_package": str(item.get("packageSourceName") or ""),
        })
    return {
        "cve_id": str(data.get("all_title") or cve_id),
        "severity": RISK_NAMES.get(
            str(data.get("threat_severity") or ""),
            str(data.get("threat_severity") or ""),
        ),
        "published": str(data.get("cve_publicdate") or ""),
        "updated": str(data.get("cve_updatedate") or ""),
        "architectures": [str(item) for item in data.get("frameworks") or []],
        "security_advisories": [str(item) for item in data.get("sa_nos") or []],
        "description": html_to_text(data.get("cve_detail")),
        "solution": html_to_text(data.get("fix_solution")),
        "update_information": html_to_text(data.get("update_information")),
        "restart_required": str(data.get("restart_tag") or ""),
        "scores": scores,
        "products": products,
        "components": components,
        "source_url": CVE_PAGE_URL.format(cve_id),
    }
