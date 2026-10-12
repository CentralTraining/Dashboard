"""Read complete dashboard files before preparing a GitHub update."""
import base64
import hashlib
import re

SCRIPT = '<script src="ollie-deadlines.js" defer></script>'


def read_dashboard(metadata, load_blob):
    value = metadata
    if value.get("encoding") != "base64" or not value.get("content"):
        value = load_blob(metadata["sha"])
    if value.get("encoding") != "base64" or not value.get("content"):
        raise ValueError("dashboard_html_unavailable")
    encoded = re.sub(r"\s+", "", value["content"])
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) != metadata["size"]:
        raise ValueError("dashboard_html_size_mismatch")
    identity = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if identity != metadata["sha"]:
        raise ValueError("dashboard_html_blob_mismatch")
    html = raw.decode("utf-8")
    validate_dashboard(html)
    return html


def validate_dashboard(html):
    if len(html.encode("utf-8")) < 10000 or not all(
        re.search(pattern, html, re.I) for pattern in
        [r"<!doctype\s+html", r"<body\b", r"</body\s*>", r"</html\s*>"]
    ):
        raise ValueError("dashboard_html_incomplete")


def add_deadline_script(html):
    validate_dashboard(html)
    if SCRIPT in html:
        return html
    position = list(re.finditer(r"</body\s*>", html, re.I))[-1].start()
    return html[:position] + SCRIPT + "\n" + html[position:]
