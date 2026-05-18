#!/usr/bin/env python3
"""
Collect, verify, render, and optionally publish a same-day AI+HR daily brief.

The script intentionally favors false negatives over stale or unverifiable news.
It uses only Python standard-library modules so the skill can run in GitHub
Actions without dependency installation.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import email.utils
import html
import json
import os
import re
import time
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
import warnings
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL.*")

try:
    from googlenewsdecoder import gnewsdecoder  # type: ignore
except Exception:  # pragma: no cover - optional dependency.
    gnewsdecoder = None


MODULES = {
    "ai_hr": "🔮 AI+HR深度聚焦",
    "global_ai": "🌐 全球AI资讯速递",
}

QUERIES = {
    "ai_hr": [
        '("AI HR" OR "AI recruiting" OR "AI hiring")',
        '("talent acquisition AI" OR "HR tech AI" OR "workforce AI")',
        '("人力资源 AI" OR "招聘 AI" OR "猎头 AI")',
    ],
    "global_ai": [
        '("artificial intelligence" OR "generative AI")',
        '("AI regulation" OR "AI safety" OR "AI model release")',
        '("OpenAI" OR "Google DeepMind" OR "Anthropic" OR "Microsoft AI" OR "NVIDIA AI")',
    ],
}

HR_KEYWORDS = [
    "hr",
    "human resources",
    "recruit",
    "recruiting",
    "hiring",
    "job",
    "jobs",
    "talent",
    "workforce",
    "employee",
    "人力",
    "招聘",
    "猎头",
    "人才",
    "员工",
]

AI_KEYWORDS = [
    "ai",
    "artificial intelligence",
    "generative",
    "model",
    "人工智能",
    "大模型",
    "生成式",
]


@dataclasses.dataclass
class Candidate:
    module: str
    title: str
    url: str
    source: str
    feed_published_at: str | None
    feed_published_local_date: str | None
    query: str
    feed: str


@dataclasses.dataclass
class AcceptedItem:
    module: str
    title: str
    url: str
    final_url: str
    source: str
    published_at: str
    published_local_date: str
    summary: str
    relevance: str
    fetched_at: str
    verification_note: str
    score: int


@dataclasses.dataclass
class RejectedItem:
    module: str
    title: str
    url: str
    reason: str
    source: str = ""
    query: str = ""


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", html.unescape(data)).strip()
        if len(text) >= 2:
            self.parts.append(text)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a verified AI+HR daily brief.")
    parser.add_argument("--target-date", help="Target date in YYYY.MM.DD. Defaults to today in timezone.")
    parser.add_argument("--start-date", help="Backfill start date in YYYY.MM.DD. Requires --end-date.")
    parser.add_argument("--end-date", help="Backfill end date in YYYY.MM.DD. Requires --start-date.")
    parser.add_argument("--timezone", default="Asia/Shanghai", help="IANA timezone. Default: Asia/Shanghai.")
    parser.add_argument("--output-dir", default="output", help="Directory for Markdown and verification JSON.")
    parser.add_argument("--max-items-per-module", type=int, default=6)
    parser.add_argument("--max-candidates-per-feed", type=int, default=2)
    parser.add_argument("--max-total-candidates", type=int, default=24)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--publish-feishu", action="store_true")
    parser.add_argument("--replace-feishu", action="store_true", help="Delete existing top-level Feishu document content before publishing.")
    parser.add_argument("--allow-backfill", action="store_true", help="Allow fetch date to differ from target date.")
    return parser.parse_args()


def target_date(args: argparse.Namespace, tz: ZoneInfo) -> dt.date:
    if args.target_date:
        return dt.datetime.strptime(args.target_date, "%Y.%m.%d").date()
    return dt.datetime.now(tz).date()


def target_dates(args: argparse.Namespace, tz: ZoneInfo) -> list[dt.date]:
    if bool(args.start_date) != bool(args.end_date):
        raise RuntimeError("--start-date and --end-date must be used together.")
    if args.start_date and args.end_date:
        start = dt.datetime.strptime(args.start_date, "%Y.%m.%d").date()
        end = dt.datetime.strptime(args.end_date, "%Y.%m.%d").date()
        if start > end:
            raise RuntimeError("--start-date must be on or before --end-date.")
        days = (end - start).days
        return [end - dt.timedelta(days=offset) for offset in range(days + 1)]
    return [target_date(args, tz)]


def fmt_doc_date(day: dt.date) -> str:
    return day.strftime("%Y.%m.%d")


def local_date(value: dt.datetime, tz: ZoneInfo) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(tz).strftime("%Y.%m.%d")


def local_datetime_label(value: dt.datetime, tz: ZoneInfo) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz)
    local_value = value.astimezone(tz)
    return f"{local_value.strftime('%Y-%m-%d %H:%M:%S')} UTC{local_value.strftime('%z')[:3]}:{local_value.strftime('%z')[3:]}（北京时间）"


def request_url(url: str, timeout: int, headers: dict[str, str] | None = None) -> tuple[int, str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 ai-hr-daily-brief/1.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            **(headers or {}),
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")
        return response.status, response.geturl(), body


def decode_source_url(url: str) -> str:
    if "news.google.com/" not in url or gnewsdecoder is None:
        return url
    try:
        result = gnewsdecoder(url, interval=0)
    except Exception:
        return url
    if isinstance(result, dict) and result.get("status") and result.get("decoded_url"):
        return str(result["decoded_url"])
    return url


def google_news_rss_url(query: str, lang: str, day: dt.date | None = None) -> str:
    date_filter = "when:1d"
    if day is not None:
        next_day = day + dt.timedelta(days=1)
        date_filter = f"after:{day.isoformat()} before:{next_day.isoformat()}"
    if lang == "zh":
        params = {"q": f"{query} {date_filter}", "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
    else:
        params = {"q": f"{query} {date_filter}", "hl": "en-US", "gl": "US", "ceid": "US:en"}
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode(params)


def parse_feed_datetime(value: str | None, tz: ZoneInfo) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return value, None
    return local_datetime_label(parsed, tz), local_date(parsed, tz)


def collect_candidates(tz: ZoneInfo, timeout: int, max_per_feed: int, max_total: int, day: dt.date | None = None) -> tuple[list[Candidate], list[RejectedItem]]:
    candidates: list[Candidate] = []
    rejected: list[RejectedItem] = []
    seen_urls: set[str] = set()

    for module, queries in QUERIES.items():
        for query in queries:
            langs = ["zh", "en"] if module == "ai_hr" else ["en", "zh"]
            for lang in langs:
                feed_url = google_news_rss_url(query, lang, day)
                try:
                    status, _, body = request_url(feed_url, timeout)
                    if status != 200:
                        rejected.append(RejectedItem(module, query, feed_url, f"RSS status {status}", query=query))
                        continue
                    root = ET.fromstring(body)
                except Exception as exc:  # noqa: BLE001 - recorded in verification report.
                    rejected.append(RejectedItem(module, query, feed_url, f"RSS fetch/parse failed: {exc}", query=query))
                    continue

                for item in root.findall(".//item"):
                    if len(candidates) >= max_total:
                        return candidates, rejected
                    title = clean_text(item.findtext("title") or "")
                    url = clean_text(item.findtext("link") or "")
                    if not title or not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    source = ""
                    source_node = item.find("{http://www.google.com/schemas/sitemap-news/0.9}source")
                    if source_node is not None and source_node.text:
                        source = clean_text(source_node.text)
                    if not source:
                        source = clean_text(item.findtext("source") or "")
                    published_at, published_date = parse_feed_datetime(item.findtext("pubDate"), tz)
                    candidates.append(
                        Candidate(
                            module=module,
                            title=title,
                            url=url,
                            source=source or "Unknown",
                            feed_published_at=published_at,
                            feed_published_local_date=published_date,
                            query=query,
                            feed=feed_url,
                        )
                    )
                    if len([candidate for candidate in candidates if candidate.feed == feed_url]) >= max_per_feed:
                        break

    return candidates, rejected


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def extract_visible_text(markup: str) -> str:
    parser = TextExtractor()
    try:
        parser.feed(markup)
    except Exception:
        return ""
    return parser.text()


def parse_iso_datetime(value: str) -> dt.datetime | None:
    text = value.strip().strip('"').strip("'")
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return dt.datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None
    try:
        return dt.datetime.fromisoformat(text)
    except ValueError:
        return None


def extract_page_dates(markup: str, visible_text: str) -> list[dt.datetime]:
    candidates: list[str] = []
    patterns = [
        r'property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'name=["\']pubdate["\'][^>]+content=["\']([^"\']+)["\']',
        r'name=["\']publishdate["\'][^>]+content=["\']([^"\']+)["\']',
        r'itemprop=["\']datePublished["\'][^>]+content=["\']([^"\']+)["\']',
        r'"datePublished"\s*:\s*"([^"]+)"',
        r'<time[^>]+datetime=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        candidates.extend(re.findall(pattern, markup, flags=re.IGNORECASE))

    text_patterns = [
        r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b",
        r"\b([A-Z][a-z]+ \d{1,2}, 20\d{2})\b",
    ]
    for match in re.findall(text_patterns[0], visible_text[:3000]):
        year, month, day = match
        candidates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    for match in re.findall(text_patterns[1], visible_text[:3000]):
        candidates.append(match)

    parsed: list[dt.datetime] = []
    for candidate in candidates:
        value = parse_iso_datetime(candidate)
        if value is None:
            try:
                value = dt.datetime.strptime(candidate, "%B %d, %Y").replace(tzinfo=dt.timezone.utc)
            except ValueError:
                continue
        parsed.append(value)
    return parsed


def has_keywords(text: str, words: list[str]) -> bool:
    return keyword_hit_count(text, words) > 0


def keyword_hit_count(text: str, words: list[str]) -> int:
    lower = text.lower()
    hits = 0
    for word in words:
        needle = word.lower()
        if re.search(r"[\u4e00-\u9fff]", needle):
            if needle in lower:
                hits += 1
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", lower):
            hits += 1
    return hits


def ai_hr_relevance_established(title: str, text: str) -> bool:
    title_hits = keyword_hit_count(title, HR_KEYWORDS)
    body_hits = keyword_hit_count(text[:1200], HR_KEYWORDS)
    return title_hits >= 1 and body_hits >= 1


def summarize(title: str, text: str) -> str:
    sentences = re.split(r"(?<=[。.!?])\s+", text)
    for sentence in sentences:
        sentence = clean_text(sentence)
        if 45 <= len(sentence) <= 220 and has_keywords(sentence, AI_KEYWORDS):
            return sentence[:220]
    return clean_text(title)[:220]


def relevance_note(module: str, title: str, text: str) -> str:
    combined = f"{title} {text[:1200]}"
    if module == "ai_hr":
        if has_keywords(combined, HR_KEYWORDS):
            return "与招聘、人力资源、人才管理或组织效率直接相关，适合HR、猎头和企业主快速判断业务影响。"
        return "涉及AI对企业经营和劳动力市场的影响，但HR相关性较弱。"
    return "属于全球AI产品、监管、模型、资本或产业动态，适合补充社群的宏观AI判断。"


def score_item(module: str, title: str, text: str, source: str) -> int:
    combined = f"{title} {text[:2000]}".lower()
    score = 0
    if has_keywords(combined, AI_KEYWORDS):
        score += 3
    if module == "ai_hr" and has_keywords(combined, HR_KEYWORDS):
        score += 5
    if source and source.lower() not in {"unknown", "google news"}:
        score += 2
    if any(name in combined for name in ["openai", "anthropic", "google", "microsoft", "nvidia"]):
        score += 1
    return score


def verify_candidates(
    candidates: list[Candidate],
    target: dt.date,
    tz: ZoneInfo,
    timeout: int,
    max_items_per_module: int,
    allow_backfill: bool,
) -> tuple[list[AcceptedItem], list[RejectedItem]]:
    accepted: list[AcceptedItem] = []
    rejected: list[RejectedItem] = []
    now = dt.datetime.now(tz)
    doc_date = fmt_doc_date(target)
    now_doc_date = fmt_doc_date(now.date())

    for candidate in candidates:
        if not allow_backfill and now.date() != target:
            rejected.append(
                RejectedItem(
                    candidate.module,
                    candidate.title,
                    candidate.url,
                    f"Fetch date {now_doc_date} does not match target date {doc_date}",
                    candidate.source,
                    candidate.query,
                )
            )
            continue

        if candidate.feed_published_local_date != doc_date:
            rejected.append(
                RejectedItem(
                    candidate.module,
                    candidate.title,
                    candidate.url,
                    f"Feed published date {candidate.feed_published_local_date or 'unknown'} does not match {doc_date}",
                    candidate.source,
                    candidate.query,
                )
            )
            continue

        source_url = decode_source_url(candidate.url)
        try:
            status, final_url, markup = request_url(source_url, timeout)
        except urllib.error.HTTPError as exc:
            rejected.append(RejectedItem(candidate.module, candidate.title, source_url, f"HTTP error {exc.code}", candidate.source, candidate.query))
            continue
        except Exception as exc:  # noqa: BLE001 - recorded for audit.
            rejected.append(RejectedItem(candidate.module, candidate.title, source_url, f"Open failed: {exc}", candidate.source, candidate.query))
            continue

        if status != 200:
            rejected.append(RejectedItem(candidate.module, candidate.title, source_url, f"Link status {status}", candidate.source, candidate.query))
            continue

        visible_text = extract_visible_text(markup)
        if len(visible_text) < 500:
            rejected.append(RejectedItem(candidate.module, candidate.title, source_url, "Opened link lacks substantive article text", candidate.source, candidate.query))
            continue

        page_dates = extract_page_dates(markup, visible_text)
        matching_page_dates = [value for value in page_dates if local_date(value, tz) == doc_date]
        if not matching_page_dates:
            found = sorted({local_date(value, tz) for value in page_dates})[:5]
            rejected.append(
                RejectedItem(
                    candidate.module,
                    candidate.title,
                    source_url,
                    f"Page date evidence does not match {doc_date}; found {found or ['unknown']}",
                    candidate.source,
                    candidate.query,
                )
            )
            continue

        combined = f"{candidate.title} {visible_text[:2000]}"
        if not has_keywords(combined, AI_KEYWORDS):
            rejected.append(RejectedItem(candidate.module, candidate.title, source_url, "AI relevance not established", candidate.source, candidate.query))
            continue
        if candidate.module == "ai_hr" and not ai_hr_relevance_established(candidate.title, visible_text):
            rejected.append(RejectedItem(candidate.module, candidate.title, source_url, "AI+HR relevance not established", candidate.source, candidate.query))
            continue

        page_date_label = local_datetime_label(matching_page_dates[0], tz)
        note = (
            f"三步校验通过：抓取时间 {local_datetime_label(now, tz)}；RSS发布时间（北京时间）{candidate.feed_published_at}；"
            f"页面日期证据（北京时间）{page_date_label}；目标日期 {doc_date}。"
        )
        accepted.append(
            AcceptedItem(
                module=candidate.module,
                title=candidate.title,
                url=candidate.url,
                final_url=final_url,
                source=candidate.source,
                published_at=candidate.feed_published_at or page_date_label,
                published_local_date=doc_date,
                summary=summarize(candidate.title, visible_text),
                relevance=relevance_note(candidate.module, candidate.title, visible_text),
                fetched_at=now.isoformat(),
                verification_note=note,
                score=score_item(candidate.module, candidate.title, visible_text, candidate.source),
            )
        )

    return dedupe_and_limit(accepted, max_items_per_module), rejected


def dedupe_and_limit(items: list[AcceptedItem], limit: int) -> list[AcceptedItem]:
    by_url: dict[str, AcceptedItem] = {}
    for item in items:
        key = normalize_url(item.final_url or item.url)
        old = by_url.get(key)
        if old is None or item.score > old.score:
            by_url[key] = item

    result: list[AcceptedItem] = []
    for module in MODULES:
        module_items = [item for item in by_url.values() if item.module == module]
        module_items.sort(key=lambda item: (item.published_at, item.score), reverse=True)
        result.extend(module_items[:limit])
    return result


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    query = [(key, value) for key, value in query if not key.lower().startswith("utm_")]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", urllib.parse.urlencode(query), ""))


def render_markdown(day: dt.date, accepted: list[AcceptedItem], rejected: list[RejectedItem]) -> str:
    doc_date = fmt_doc_date(day)
    lines = [
        f"# {doc_date}",
        "",
    ]

    for module, heading in MODULES.items():
        lines.append(f"## {heading}")
        lines.append("")
        module_items = [item for item in accepted if item.module == module]
        if not module_items:
            lines.append("当日无高质量信息源")
            lines.append("")
            continue
        for index, item in enumerate(module_items, start=1):
            lines.extend(
                [
                    f"### {index}. {item.title}",
                    f"- 摘要：{item.summary}",
                    f"- 链接：{item.final_url}",
                    "",
                ]
            )

    return "\n".join(lines).strip() + "\n"


def render_combined_markdown(markdown_paths: list[Path]) -> str:
    sections = [path.read_text(encoding="utf-8").strip() for path in markdown_paths]
    return "\n\n".join(section for section in sections if section).strip() + "\n"


def write_outputs(output_dir: Path, day: dt.date, accepted: list[AcceptedItem], rejected: list[RejectedItem], candidates: list[Candidate]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_date = fmt_doc_date(day)
    markdown_path = output_dir / f"{doc_date}.md"
    report_path = output_dir / "verification_report.json"
    markdown = render_markdown(day, accepted, rejected)
    markdown_path.write_text(markdown, encoding="utf-8")
    report = {
        "daily_section_date": doc_date,
        "generated_at": dt.datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "candidate_count": len(candidates),
        "accepted": [dataclasses.asdict(item) for item in accepted],
        "rejected": [dataclasses.asdict(item) for item in rejected],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return markdown_path


def feishu_request(
    base_url: str,
    path: str,
    token: str | None,
    payload: dict[str, Any] | None,
    timeout: int,
    method: str,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
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


def feishu_api(base_url: str, path: str, token: str | None, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    return feishu_request(base_url, path, token, payload, timeout, "POST")


def feishu_delete(base_url: str, path: str, token: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    return feishu_request(base_url, path, token, payload, timeout, "DELETE")


def feishu_get(base_url: str, path: str, token: str, timeout: int) -> dict[str, Any]:
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="GET",
    )
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


def extract_feishu_token(value: str) -> tuple[str, str]:
    text = value.strip()
    wiki_match = re.search(r"/wiki/([A-Za-z0-9_-]+)", text)
    if wiki_match:
        return wiki_match.group(1), "wiki"
    docx_match = re.search(r"/docx/([A-Za-z0-9_-]+)", text)
    if docx_match:
        return docx_match.group(1), "docx"
    if text.startswith("http"):
        raise RuntimeError("FEISHU_DOCUMENT_ID must be a /docx/ URL, /wiki/ URL, docx token, or wiki node token.")
    return text, "docx"


def resolve_feishu_document_id(base_url: str, raw_value: str, token: str, timeout: int) -> tuple[str, str]:
    extracted, token_type = extract_feishu_token(raw_value)
    if token_type == "docx":
        return extracted, "docx"

    query = urllib.parse.urlencode({"token": extracted})
    try:
        result = feishu_get(base_url, f"/open-apis/wiki/v2/spaces/get_node?{query}", token, timeout)
    except RuntimeError as exc:
        raise RuntimeError(
            "Failed to resolve Feishu Wiki token. If FEISHU_DOCUMENT_ID is a /wiki/ link, "
            "the Feishu app must have Wiki read permission and must be a member/admin of the target Wiki space or page. "
            f"Raw Feishu response: {exc}"
        ) from exc
    node = result.get("data", {}).get("node", {})
    obj_type = node.get("obj_type")
    obj_token = node.get("obj_token")
    if obj_type != "docx" or not obj_token:
        raise RuntimeError(f"Wiki token resolved to obj_type={obj_type!r}, not a docx document: {result}")
    return str(obj_token), "wiki"


def get_feishu_document_revision_id(base_url: str, document_id: str, token: str, timeout: int) -> int:
    result = feishu_get(base_url, f"/open-apis/docx/v1/documents/{document_id}", token, timeout)
    document = result.get("data", {}).get("document", {})
    revision_id = document.get("revision_id")
    if not isinstance(revision_id, int):
        raise RuntimeError(f"Feishu document info response did not contain integer revision_id: {result}")
    return revision_id


def list_feishu_root_children(base_url: str, document_id: str, root_block_id: str, token: str, timeout: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page_token = ""
    while True:
        params = {"page_size": 500}
        if page_token:
            params["page_token"] = page_token
        query = urllib.parse.urlencode(params)
        result = feishu_get(
            base_url,
            f"/open-apis/docx/v1/documents/{document_id}/blocks/{root_block_id}/children?{query}",
            token,
            timeout,
        )
        data = result.get("data", {})
        items.extend(data.get("items", []))
        if not data.get("has_more") or not data.get("page_token"):
            return items
        page_token = str(data["page_token"])


def clear_feishu_document(base_url: str, document_id: str, root_block_id: str, token: str, timeout: int) -> int:
    deleted = 0
    while True:
        children = list_feishu_root_children(base_url, document_id, root_block_id, token, timeout)
        if not children:
            return deleted
        revision_id = get_feishu_document_revision_id(base_url, document_id, token, timeout)
        count = len(children)
        query = urllib.parse.urlencode({"document_revision_id": revision_id})
        feishu_delete(
            base_url,
            f"/open-apis/docx/v1/documents/{document_id}/blocks/{root_block_id}/children/batch_delete?{query}",
            token,
            {"start_index": 0, "end_index": count},
            timeout,
        )
        deleted += count
        time.sleep(0.3)


def get_feishu_tenant_access_token(base_url: str, app_id: str, app_secret: str, timeout: int) -> str:
    token_result = feishu_api(
        base_url,
        "/open-apis/auth/v3/tenant_access_token/internal",
        None,
        {"app_id": app_id, "app_secret": app_secret},
        timeout,
    )
    token = token_result.get("tenant_access_token")
    if not token:
        raise RuntimeError(f"Feishu token response did not contain tenant_access_token: {token_result}")
    return str(token)


def get_feishu_app_access_token(base_url: str, app_id: str, app_secret: str, timeout: int) -> str:
    token_result = feishu_api(
        base_url,
        "/open-apis/auth/v3/app_access_token/internal",
        None,
        {"app_id": app_id, "app_secret": app_secret},
        timeout,
    )
    token = token_result.get("app_access_token")
    if not token:
        raise RuntimeError(f"Feishu token response did not contain app_access_token: {token_result}")
    return str(token)


def maybe_write_rotated_refresh_token(refresh_token: str) -> None:
    output_path = os.environ.get("FEISHU_TOKEN_OUTPUT_PATH")
    if not output_path:
        return
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(refresh_token.strip() + "\n", encoding="utf-8")


def get_feishu_write_token(base_url: str, app_id: str, app_secret: str, timeout: int) -> tuple[str, str]:
    explicit_user_token = os.environ.get("FEISHU_USER_ACCESS_TOKEN") or os.environ.get("FEISHU_ACCESS_TOKEN")
    if explicit_user_token:
        return explicit_user_token, "user_access_token"

    refresh_token = os.environ.get("FEISHU_REFRESH_TOKEN")
    if refresh_token:
        app_token = get_feishu_app_access_token(base_url, app_id, app_secret, timeout)
        refresh_result = feishu_api(
            base_url,
            "/open-apis/authen/v1/refresh_access_token",
            app_token,
            {"grant_type": "refresh_token", "refresh_token": refresh_token},
            timeout,
        )
        data = refresh_result.get("data", refresh_result)
        access_token = data.get("access_token")
        rotated_refresh_token = data.get("refresh_token")
        if not access_token:
            raise RuntimeError(f"Feishu OAuth refresh response did not contain access_token: {refresh_result}")
        if rotated_refresh_token:
            maybe_write_rotated_refresh_token(str(rotated_refresh_token))
        return str(access_token), "user_access_token"

    return get_feishu_tenant_access_token(base_url, app_id, app_secret, timeout), "tenant_access_token"


def publish_feishu(markdown_path: Path, title: str, timeout: int, replace_existing: bool = False) -> str:
    app_id = os.environ.get("FEISHU_APP_ID")
    app_secret = os.environ.get("FEISHU_APP_SECRET")
    raw_document_id = os.environ.get("FEISHU_DOCUMENT_ID")
    base_url = os.environ.get("FEISHU_BASE_URL", "https://open.feishu.cn")
    if not app_id or not app_secret or not raw_document_id:
        raise RuntimeError("Missing FEISHU_APP_ID, FEISHU_APP_SECRET, or FEISHU_DOCUMENT_ID.")

    token, token_source = get_feishu_write_token(base_url, app_id, app_secret, timeout)

    document_id, resolved_from = resolve_feishu_document_id(base_url, raw_document_id, token, timeout)
    root_block_id = os.environ.get("FEISHU_ROOT_BLOCK_ID") or document_id
    if replace_existing:
        deleted = clear_feishu_document(base_url, document_id, root_block_id, token, timeout)
        print(f"Feishu cleared top-level blocks: {deleted}")
    revision_id = get_feishu_document_revision_id(base_url, document_id, token, timeout)

    content = markdown_path.read_text(encoding="utf-8")
    blocks = markdown_to_feishu_blocks(content)
    for chunk in reversed(chunk_blocks(blocks, size=40)):
        query = urllib.parse.urlencode({"document_revision_id": revision_id})
        result = feishu_api(
            base_url,
            f"/open-apis/docx/v1/documents/{document_id}/blocks/{root_block_id}/children?{query}",
            token,
            {"children": chunk, "index": 0},
            timeout,
        )
        next_revision_id = result.get("data", {}).get("document_revision_id")
        if isinstance(next_revision_id, int):
            revision_id = next_revision_id
        else:
            revision_id = get_feishu_document_revision_id(base_url, document_id, token, timeout)
    print(f"Feishu token source: {token_source}")
    if raw_document_id.startswith("http"):
        return raw_document_id
    doc_base_url = os.environ.get("FEISHU_DOC_BASE_URL")
    if doc_base_url:
        return f"{doc_base_url.rstrip('/')}/docx/{document_id}"
    return f"docx:{document_id}"


def chunk_blocks(blocks: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [blocks[index:index + size] for index in range(0, len(blocks), size)]


def text_elements(content: str) -> dict[str, Any]:
    return {
        "elements": [
            {
                "text_run": {
                    "content": content,
                    "text_element_style": {},
                }
            }
        ],
        "style": {},
    }


def markdown_to_feishu_blocks(markdown: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        block_type = 2
        content_key = "text"
        text = line
        if line.startswith("# "):
            block_type = 3
            content_key = "heading1"
            text = line[2:]
        elif line.startswith("## "):
            block_type = 4
            content_key = "heading2"
            text = line[3:]
        elif line.startswith("### "):
            block_type = 5
            content_key = "heading3"
            text = line[4:]
        elif line.startswith("- "):
            block_type = 12
            content_key = "bullet"
            text = line[2:]
        elif line.startswith("> "):
            block_type = 15
            content_key = "quote"
            text = line[2:]
        blocks.append(
            {
                "block_type": block_type,
                content_key: text_elements(text),
            }
        )
    return blocks


def main() -> int:
    args = parse_args()
    tz = ZoneInfo(args.timezone)
    days = target_dates(args, tz)
    output_dir = Path(args.output_dir)
    markdown_paths: list[Path] = []
    total_accepted = 0
    total_rejected = 0

    for day in days:
        candidates, rss_rejections = collect_candidates(tz, args.timeout, args.max_candidates_per_feed, args.max_total_candidates, day)
        accepted, verification_rejections = verify_candidates(
            candidates,
            day,
            tz,
            args.timeout,
            args.max_items_per_module,
            args.allow_backfill or len(days) > 1,
        )
        rejected = rss_rejections + verification_rejections
        markdown_path = write_outputs(output_dir / fmt_doc_date(day) if len(days) > 1 else output_dir, day, accepted, rejected, candidates)
        markdown_paths.append(markdown_path)
        total_accepted += len(accepted)
        total_rejected += len(rejected)

        print(f"Daily section: {fmt_doc_date(day)}")
        print(f"Markdown: {markdown_path}")
        print(f"Accepted: {len(accepted)}")
        print(f"Rejected: {len(rejected)}")

    publish_path = markdown_paths[0]
    if len(markdown_paths) > 1:
        output_dir.mkdir(parents=True, exist_ok=True)
        publish_path = output_dir / f"{fmt_doc_date(days[-1])}_to_{fmt_doc_date(days[0])}.md"
        publish_path.write_text(render_combined_markdown(markdown_paths), encoding="utf-8")
        print(f"Combined Markdown: {publish_path}")

    if args.publish_feishu:
        url = publish_feishu(publish_path, fmt_doc_date(days[0]), args.timeout, args.replace_feishu)
        print(f"Feishu document: {url}")

    if total_accepted == 0:
        print(textwrap.dedent(
            """
            No same-day high-quality sources passed the gate.
            The generated document uses: 当日无高质量信息源
            """
        ).strip())
    print(f"Total accepted: {total_accepted}")
    print(f"Total rejected: {total_rejected}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
