from __future__ import annotations

from urllib.parse import quote, urljoin, urlparse

import httpx

from tps.research import _build_auth_headers, _TextExtractor


def _sharepoint_folder_url(base_url: str, path: str) -> str:
    """Build SharePoint REST API URL for folder contents."""
    # ponytail: REST API is site-scoped, must be {site_url}/_api/ not {root}/_api/
    parsed = urlparse(base_url)
    site_path = parsed.path.rstrip("/")
    if path:
        rel = f"{site_path}/{path}"
    else:
        rel = f"{site_path}/Shared Documents"
    encoded = quote(rel, safe="/")
    return (
        f"{parsed.scheme}://{parsed.netloc}{site_path}"
        f"/_api/web/GetFolderByServerRelativeUrl('{encoded}')"
    )


def browse_sharepoint(base_url: str, path: str = "",
                      auth_source: dict | None = None) -> dict:
    """List files and folders from a SharePoint document library."""
    folder_url = _sharepoint_folder_url(base_url, path)
    parsed = urlparse(base_url)
    site_path = parsed.path.rstrip("/")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    headers = {
        "Accept": "application/json;odata=nometadata",
        "User-Agent": "Mozilla/5.0 (compatible; OCPArchitect/1.0)",
        "Referer": base_url + "/",
        "Origin": origin,
    }
    headers.update(_build_auth_headers(auth_source))

    files = []
    folders = []
    errors = []

    # Fetch files
    try:
        r = httpx.get(
            f"{folder_url}/Files?$select=Name,ServerRelativeUrl,Length,TimeLastModified",
            headers=headers, follow_redirects=True, timeout=20,
        )
        r.raise_for_status()
        for f in r.json().get("value", []):
            parsed = urlparse(base_url)
            file_url = f"{parsed.scheme}://{parsed.netloc}{f['ServerRelativeUrl']}"
            files.append({
                "name": f["Name"],
                "url": file_url,
                "size": f.get("Length", 0),
                "modified": f.get("TimeLastModified", ""),
                "type": "file",
            })
    except Exception as e:
        errors.append(f"Files: {e}")

    # Fetch subfolders
    try:
        r = httpx.get(
            f"{folder_url}/Folders?$select=Name,ServerRelativeUrl,ItemCount",
            headers=headers, follow_redirects=True, timeout=20,
        )
        r.raise_for_status()
        for f in r.json().get("value", []):
            if f["Name"] in ("Forms",):
                continue
            # ponytail: strip site_path prefix so url works as sub_path for next browse
            rel = f["ServerRelativeUrl"]
            if rel.startswith(site_path):
                rel = rel[len(site_path):].lstrip("/")
            folders.append({
                "name": f["Name"],
                "url": rel,
                "items": f.get("ItemCount", 0),
                "type": "folder",
            })
    except Exception as e:
        errors.append(f"Folders: {e}")

    return {"files": files, "folders": folders, "errors": errors}


def browse_web(base_url: str, path: str = "",
               auth_source: dict | None = None) -> dict:
    """Scrape links from a web page as a file listing fallback."""
    url = f"{base_url.rstrip('/')}/{path}".rstrip("/")
    headers = {"User-Agent": "Mozilla/5.0 (compatible; OCPArchitect/1.0)"}
    headers.update(_build_auth_headers(auth_source))

    try:
        r = httpx.get(url, headers=headers, follow_redirects=True, timeout=20)
        r.raise_for_status()
    except Exception as e:
        return {"files": [], "folders": [], "errors": [str(e)]}

    # Extract links from HTML
    from html.parser import HTMLParser

    class _LinkExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.links: list[dict] = []

        def handle_starttag(self, tag, attrs):
            if tag != "a":
                return
            href = dict(attrs).get("href", "")
            if not href or href.startswith("#") or href.startswith("javascript:"):
                return
            full = urljoin(url, href)
            self.links.append({"name": "", "url": full, "type": "file"})

        def handle_data(self, data):
            if self.links and not self.links[-1]["name"]:
                self.links[-1]["name"] = data.strip()

    parser = _LinkExtractor()
    parser.feed(r.text)
    # Dedupe by URL, filter out navigation links
    seen = set()
    files = []
    for link in parser.links:
        if link["url"] in seen or not link["name"]:
            continue
        seen.add(link["url"])
        files.append(link)

    return {"files": files[:100], "folders": [], "errors": []}


def browse_doc_source(source_type: str, base_url: str, path: str = "",
                      auth_source: dict | None = None) -> dict:
    """Route to the appropriate browser based on source type."""
    if source_type == "sharepoint":
        return browse_sharepoint(base_url, path, auth_source)
    return browse_web(base_url, path, auth_source)
