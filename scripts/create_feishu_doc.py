#!/usr/bin/env python3
"""Create the fixed Feishu Docx document that the daily brief will update."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def feishu_post(base_url: str, path: str, token: str | None, payload: dict, timeout: int = 20) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Feishu HTTP {exc.code} at {path}: {body}") from exc
    result = json.loads(body)
    if result.get("code") not in (0, None):
        raise RuntimeError(f"Feishu API error at {path}: {result}")
    return result


def extract_folder_token(value: str) -> str:
    text = value.strip()
    match = re.search(r"/drive/folder/([A-Za-z0-9_-]+)", text)
    if match:
        return match.group(1)
    if text.startswith("http"):
        raise RuntimeError("FEISHU_FOLDER_TOKEN must be a /drive/folder/ URL or a folder token.")
    return text


def main() -> int:
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    folder_value = os.environ.get("FEISHU_FOLDER_TOKEN")
    title = os.environ.get("FEISHU_DOC_TITLE", "AIHR 嘉尔日报")
    base_url = os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn")
    if not app_id or not app_secret or not folder_value:
        raise RuntimeError("Missing FEISHU_APP_ID, FEISHU_APP_SECRET, or FEISHU_FOLDER_TOKEN.")

    token_result = feishu_post(
        base_url,
        "/open-apis/auth/v3/tenant_access_token/internal",
        None,
        {"app_id": app_id, "app_secret": app_secret},
    )
    tenant_token = token_result.get("tenant_access_token")
    if not tenant_token:
        raise RuntimeError(f"Feishu token response did not contain tenant_access_token: {token_result}")

    folder_token = extract_folder_token(folder_value)
    create_result = feishu_post(
        base_url,
        "/open-apis/docx/v1/documents",
        tenant_token,
        {"folder_token": folder_token, "title": title},
    )
    document = create_result.get("data", {}).get("document", {}) or create_result.get("data", {})
    document_id = document.get("document_id") or document.get("id")
    if not document_id:
        raise RuntimeError(f"Create document response missing document_id: {create_result}")

    print(f"FEISHU_DOCUMENT_ID={document_id}")
    print(f"FEISHU_DOCUMENT_URL={base_url.rstrip('/')}/docx/{document_id}")
    print("Save FEISHU_DOCUMENT_ID as a GitHub Actions secret, then run Daily AI HR Brief.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
