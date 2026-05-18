#!/usr/bin/env python3
"""Prepare Feishu OAuth user authorization for writing personal documents."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_DOCX_SCOPES = "docx:document docx:document:write_only"


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


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing {name}.")
    return value


def app_access_token(base_url: str, app_id: str, app_secret: str) -> str:
    result = feishu_post(
        base_url,
        "/open-apis/auth/v3/app_access_token/internal",
        None,
        {"app_id": app_id, "app_secret": app_secret},
    )
    token = result.get("app_access_token")
    if not token:
        raise RuntimeError(f"Feishu response did not contain app_access_token: {result}")
    return str(token)


def extract_code(value: str) -> str:
    text = value.strip()
    parsed = urllib.parse.urlparse(text)
    if parsed.query:
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("code"):
            return query["code"][0]
    return text


def command_auth_url(args: argparse.Namespace) -> int:
    app_id = require_env("FEISHU_APP_ID")
    redirect_uri = require_env("FEISHU_REDIRECT_URI")
    state = args.state or secrets.token_urlsafe(16)
    params = {
        "app_id": app_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    scope = args.scope or DEFAULT_DOCX_SCOPES
    if scope:
        params["scope"] = scope
    print("Open this URL, approve the app, then copy the redirected URL:")
    print("https://open.feishu.cn/open-apis/authen/v1/index?" + urllib.parse.urlencode(params))
    print(f"State: {state}")
    return 0


def command_exchange_code(args: argparse.Namespace) -> int:
    app_id = require_env("FEISHU_APP_ID")
    app_secret = require_env("FEISHU_APP_SECRET")
    code_value = args.code or require_env("FEISHU_AUTH_CODE")
    base_url = os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn")
    app_token = app_access_token(base_url, app_id, app_secret)
    result = feishu_post(
        base_url,
        "/open-apis/authen/v1/access_token",
        app_token,
        {"grant_type": "authorization_code", "code": extract_code(code_value)},
    )
    data = result.get("data", result)
    refresh_token = data.get("refresh_token")
    access_token = data.get("access_token")
    if not refresh_token:
        raise RuntimeError(f"Feishu response did not contain refresh_token: {result}")
    if access_token:
        print("FEISHU_USER_ACCESS_TOKEN was issued for immediate testing.")
    print("Set this as the GitHub Actions secret FEISHU_REFRESH_TOKEN:")
    print(refresh_token)
    return 0


def command_refresh(args: argparse.Namespace) -> int:
    app_id = require_env("FEISHU_APP_ID")
    app_secret = require_env("FEISHU_APP_SECRET")
    refresh_token = require_env("FEISHU_REFRESH_TOKEN")
    base_url = os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn")
    app_token = app_access_token(base_url, app_id, app_secret)
    result = feishu_post(
        base_url,
        "/open-apis/authen/v1/refresh_access_token",
        app_token,
        {"grant_type": "refresh_token", "refresh_token": refresh_token},
    )
    data = result.get("data", result)
    if not data.get("access_token") or not data.get("refresh_token"):
        raise RuntimeError(f"Feishu response missing access_token or refresh_token: {result}")
    print("FEISHU_USER_ACCESS_TOKEN=" + str(data["access_token"]))
    print("FEISHU_REFRESH_TOKEN=" + str(data["refresh_token"]))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Feishu OAuth helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    auth_url = subparsers.add_parser("auth-url", help="Print the user authorization URL.")
    auth_url.add_argument("--scope", default="", help=f"OAuth scope string. Defaults to: {DEFAULT_DOCX_SCOPES}")
    auth_url.add_argument("--state", default="", help="Optional state value.")
    auth_url.set_defaults(func=command_auth_url)

    exchange = subparsers.add_parser("exchange-code", help="Exchange a redirected code URL or raw code for tokens.")
    exchange.add_argument("--code", default="", help="Raw code or full redirected URL. Defaults to FEISHU_AUTH_CODE.")
    exchange.set_defaults(func=command_exchange_code)

    refresh = subparsers.add_parser("refresh", help="Refresh and print a user access token.")
    refresh.set_defaults(func=command_refresh)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
