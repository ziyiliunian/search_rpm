import json
import re
from html.parser import HTMLParser
from urllib.request import Request, urlopen

CVE_API_URL = "https://support.kylinos.cn/protalweb/security/cve/info"
CVE_PAGE_URL = "https://support.kylinos.cn/#/security/cveDetail?allTitle={}"
USER_AGENT = "search_rpm/1.7.5"
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
STATUS_NAMES = {
    "0": "不影响", "1": "处理中", "2": "已修复", "3": "不计划修复",
    "4": "不影响", "5": "超出支持范围",
}
RISK_NAMES = {
    "critical": "严重", "high": "高", "medium": "中", "low": "低", "none": "无",
    "严重": "严重", "高": "高", "中": "中", "低": "低", "无": "无",
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


def _string(value):
    return "" if value is None else str(value)


def _dict_items(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


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
    for item in _dict_items(data.get("cvss_info_list")):
        scores.append({
            "provider": _string(item.get("provider")),
            "score": _string(item.get("score")),
            "vector": _string(item.get("value")),
        })
    products = []
    for item in _dict_items(data.get("product_relation_list")):
        state = _string(item.get("state"))
        products.append({
            "product_name": _string(item.get("product_name")),
            "state": STATUS_NAMES.get(state, state),
        })
    components = []
    for item in _dict_items(data.get("product_component_list")):
        product = item.get("product_info") if isinstance(item.get("product_info"), dict) else {}
        status = _string(item.get("status"))
        components.append({
            "product": _string(product.get("product_name") or product.get("product_nick_name")),
            "component": _string(item.get("component_name") or item.get("src_name")),
            "version": _string(item.get("version")),
            "architecture": _string(item.get("framework")),
            "status": STATUS_NAMES.get(status, status),
            "security_advisory": _string(item.get("sa_no") or item.get("announcement_no")),
            "release_date": _string(item.get("release_date") or item.get("update_date")),
            "source_package": _string(item.get("packageSourceName")),
        })
    return {
        "cve_id": str(data.get("all_title") or cve_id),
        "severity": RISK_NAMES.get(
            str(data.get("threat_severity") or "").strip().lower(),
            "未知",
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
