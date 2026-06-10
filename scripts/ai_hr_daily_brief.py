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
import uuid
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

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # pragma: no cover - optional poster dependency.
    Image = None
    ImageDraw = None
    ImageFont = None


MODULES = {
    "ai_hr": "🔮 AI+HR深度聚焦",
    "global_ai": "🌐 全球AI资讯速递",
}

QUERIES = {
    "ai_hr": [
        '("AI HR" OR "AI recruiting" OR "AI hiring")',
        '("AI hiring layoffs workforce news" OR "AI job market" OR "AI workforce disruption")',
        '("talent acquisition AI" OR "HR tech AI" OR "workforce AI")',
        '("employee experience AI" OR "people analytics AI" OR "workforce planning AI")',
        '("AI interview" OR "AI resume screening" OR "AI onboarding" OR "AI performance management")',
        '("AI skills gap" OR "AI training employees" OR "AI reskilling" OR "AI upskilling")',
        '("agentic AI HR" OR "AI agent HR" OR "enterprise AI HR")',
        '("人力资源 AI" OR "招聘 AI" OR "猎头 AI")',
        '("AI 就业" OR "AI 裁员" OR "AI 劳动力" OR "AI 技能培训")',
        '("AI员工" OR "AI面试" OR "AI简历筛选" OR "AI招聘助手")',
        '("AI绩效" OR "AI员工体验" OR "AI人才管理" OR "AI组织效率")',
        '("数字员工" OR "AI人事" OR "AI招聘系统" OR "AI人才盘点")',
        '(site:36kr.com OR site:tmtpost.com OR site:infoq.cn) ("AI HR" OR "AI招聘" OR "人力资源 AI")',
        '(site:hroot.com OR site:hrtechchina.com OR site:mokahr.com OR site:beisen.com) ("AI" OR "人工智能" OR "智能体")',
        '(site:hrtechseries.com OR site:hrexecutive.com OR site:joshbersin.com) ("AI" OR "artificial intelligence" OR "agent")',
        '(site:shrm.org OR site:workday.com OR site:linkedin.com/business/talent/blog) ("AI" OR "artificial intelligence")',
        '(site:ailayoff.live OR site:layoffhedge.com OR site:layoffs.fyi) ("AI" OR "layoff" OR "workforce" OR "hiring")',
    ],
    "global_ai": [
        '("artificial intelligence" OR "generative AI")',
        '("AI regulation" OR "AI safety" OR "AI model release")',
        '("OpenAI" OR "Google DeepMind" OR "Anthropic" OR "Microsoft AI" OR "NVIDIA AI")',
        '("AI startup funding" OR "AI IPO" OR "AI industry news")',
        '("AI model release" OR "AI product launch" OR "enterprise AI")',
        '("人工智能" OR "大模型" OR "生成式AI")',
        '("AI 最新动态" OR "人工智能 今日热点" OR "大模型 发布")',
        '(site:36kr.com OR site:tmtpost.com OR site:qbitai.com OR site:jiqizhixin.com) ("人工智能" OR "大模型" OR "AI")',
        '(site:ithome.com OR site:leiphone.com OR site:infoq.cn OR site:ifanr.com) ("AI" OR "人工智能" OR "大模型")',
        '(site:cnbc.com OR site:techcrunch.com OR site:theverge.com OR site:reuters.com) ("AI" OR "artificial intelligence")',
        '(site:openai.com OR site:anthropic.com OR site:deepmind.google OR site:huggingface.co) ("AI" OR "model" OR "research")',
    ],
}

AI_HR_FALLBACK_QUERIES = [
    '("AI workforce" OR "AI employment" OR "AI jobs" OR "AI layoffs")',
    '("AI hiring" OR "AI recruiting" OR "AI interview" OR "AI resume screening")',
    '("AI skills" OR "AI reskilling" OR "AI training" OR "learning and development AI")',
    '("HR technology AI" OR "people analytics AI" OR "talent management AI")',
    '("AI 就业" OR "AI 裁员" OR "AI 招聘" OR "AI 人才")',
    '("AI 技能" OR "AI 培训" OR "AI 学习发展" OR "AI 组织效率")',
    '(site:hroot.com OR site:hrtechchina.com OR site:mokahr.com OR site:beisen.com) ("AI" OR "人工智能" OR "招聘" OR "人才")',
    '(site:shrm.org OR site:hrexecutive.com OR site:hrtechseries.com OR site:joshbersin.com) ("AI" OR "artificial intelligence") ("workforce" OR "talent" OR "HR")',
]

AI_HR_SHORTAGE_THRESHOLD = 3

AIHOT_DISCOVERY_URLS = [
    "https://aihot.virxact.com/",
    "https://aihot.virxact.com/all",
]
AIHOT_DISCOVERY_LIMIT = 18

DIRECT_RSS_FEEDS = {
    "ai_hr": [
        ("36氪", "https://36kr.com/feed"),
        ("钛媒体", "https://www.tmtpost.com/rss.xml"),
        ("InfoQ中文", "https://www.infoq.cn/feed"),
        ("HRTech Series", "https://hrtechseries.com/feed/"),
        ("HR Executive", "https://hrexecutive.com/feed/"),
        ("Josh Bersin", "https://joshbersin.com/feed/"),
        ("HRTech Weekly", "https://hrtechweekly.com/feed/"),
    ],
    "global_ai": [
        ("36氪", "https://36kr.com/feed"),
        ("钛媒体", "https://www.tmtpost.com/rss.xml"),
        ("量子位", "https://www.qbitai.com/feed"),
        ("InfoQ中文", "https://www.infoq.cn/feed"),
        ("爱范儿", "https://www.ifanr.com/feed"),
        ("IT之家", "https://www.ithome.com/rss/"),
        ("雷峰网", "https://www.leiphone.com/feed"),
        ("开源中国", "https://www.oschina.net/news/rss"),
        ("少数派", "https://sspai.com/feed"),
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
    "headcount",
    "staffing",
    "employment",
    "employee",
    "layoff",
    "layoffs",
    "reskilling",
    "upskilling",
    "skill",
    "skills",
    "training",
    "learning and development",
    "l&d",
    "ats",
    "hcm",
    "hris",
    "people analytics",
    "employee experience",
    "workforce planning",
    "performance management",
    "onboarding",
    "workday",
    "successfactors",
    "dayforce",
    "greenhouse",
    "lever",
    "人力",
    "招聘",
    "猎头",
    "人才",
    "员工",
    "人事",
    "绩效",
    "薪酬",
    "组织",
    "就业",
    "劳动力",
    "就业市场",
    "裁员",
    "技能",
    "再培训",
    "转岗",
    "用工",
    "人效",
    "员工体验",
    "人才管理",
    "招聘系统",
    "候选人",
    "面试",
    "简历",
    "入职",
    "背调",
    "培训",
    "学习",
    "学习发展",
    "数字员工",
    "飞书人事",
    "北森",
    "Moka",
    "肯耐珂萨",
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

HR_FOCUSED_SOURCE_HINTS = [
    "hroot",
    "hrtech",
    "hr tech",
    "hr executive",
    "hrexecutive",
    "josh bersin",
    "bersin",
    "moka",
    "mokahr",
    "beisen",
    "北森",
    "肯耐珂萨",
    "shrm",
    "workday",
    "linkedin talent",
    "ailayoff",
    "layoffhedge",
    "layoffs.fyi",
]

SOURCE_PRIORITY_HINTS = [
    (12, ["openai.com", "anthropic.com", "deepmind.google", "microsoft.com", "nvidia.com", "apple.com/newsroom", "huggingface.co", "arxiv.org"]),
    (11, ["workday.com", "linkedin.com/business/talent", "shrm.org", "joshbersin.com", "hrexecutive.com", "hrtechseries.com", "hroot.com", "hrtechchina.com", "mokahr.com", "beisen.com"]),
    (10, ["reuters.com", "bloomberg.com", "wsj.com", "cnbc.com", "techcrunch.com", "theverge.com"]),
    (9, ["36kr.com", "qbitai.com", "jiqizhixin.com", "infoq.cn", "tmtpost.com", "ithome.com", "leiphone.com"]),
    (8, ["ailayoff.live", "layoffhedge.com", "layoffs.fyi"]),
]

LOW_VERIFICATION_DOMAINS = [
    "x.com",
    "twitter.com",
]

POSTER_THEME_RULES = [
    ("AI招聘", ["ai招聘", "招聘", "recruit", "hiring", "talent acquisition", "ats", "候选人", "面试", "简历", "jd"]),
    ("人才管理", ["人才管理", "talent management", "绩效", "performance", "继任", "succession", "学习发展", "培训"]),
    ("员工体验", ["员工体验", "employee experience", "onboarding", "入职", "员工服务", "员工问答"]),
    ("组织效率", ["组织", "效率", "协作", "办公", "workflow", "productivity", "knowledge management", "知识管理"]),
    ("智能体", ["agent", "agents", "agentic", "智能体", "数字员工", "ai员工"]),
    ("企业AI", ["enterprise", "企业", "business", "saas", "hcm", "hris", "workday", "successfactors", "moka", "北森"]),
    ("AI治理", ["regulation", "governance", "监管", "治理", "合规", "风险", "安全", "transparency", "透明"]),
    ("大模型", ["大模型", "model", "openai", "anthropic", "deepmind", "deepseek", "qwen", "gemini", "claude"]),
    ("开源模型", ["开源", "open-source", "open source", "github", "hugging face"]),
    ("资本动态", ["融资", "估值", "revenue", "ipo", "acquire", "funding", "投资", "并购"]),
]

POSTER_SIZE = (1080, 1440)
POSTER_REGULAR_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]
POSTER_BOLD_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.otf",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
]

WEEKDAY_LABELS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


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
    parser.add_argument("--max-candidates-per-feed", type=int, default=3)
    parser.add_argument("--max-total-candidates", type=int, default=72)
    parser.add_argument("--timeout", type=int, default=15)
    parser.add_argument("--publish-feishu", action="store_true")
    parser.add_argument("--replace-feishu", action="store_true", help="Delete existing top-level Feishu document content before publishing.")
    parser.add_argument("--allow-backfill", action="store_true", help="Allow fetch date to differ from target date.")
    parser.add_argument("--skip-poster", action="store_true", help="Skip daily 1080x1440 poster PNG generation.")
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
        today = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date()
        if day != today:
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
        compact_value = re.sub(r"\s+", " ", value.strip())
        parsed = parse_iso_datetime(compact_value.replace(" ", "T", 1))
        if parsed is None:
            for date_format in ("%Y-%m-%d %H:%M:%S %z", "%Y/%m/%d %H:%M:%S %z"):
                try:
                    parsed = dt.datetime.strptime(compact_value, date_format)
                    break
                except ValueError:
                    continue
        if parsed is None:
            return value, None
    return local_datetime_label(parsed, tz), local_date(parsed, tz)


def first_text(item: ET.Element, names: list[str]) -> str:
    for name in names:
        value = item.findtext(name)
        if value:
            return clean_text(value)
    return ""


def item_link(item: ET.Element) -> str:
    link = first_text(item, ["link", "{http://www.w3.org/2005/Atom}link"])
    if link:
        return link
    atom_link = item.find("{http://www.w3.org/2005/Atom}link")
    if atom_link is not None and atom_link.attrib.get("href"):
        return clean_text(atom_link.attrib["href"])
    return ""


def item_source(item: ET.Element, fallback: str) -> str:
    source_node = item.find("{http://www.google.com/schemas/sitemap-news/0.9}source")
    if source_node is not None and source_node.text:
        return clean_text(source_node.text)
    source = first_text(item, ["source", "{http://www.w3.org/2005/Atom}source"])
    return source or fallback


def item_published_value(item: ET.Element) -> str | None:
    return (
        item.findtext("pubDate")
        or item.findtext("published")
        or item.findtext("updated")
        or item.findtext("{http://www.w3.org/2005/Atom}published")
        or item.findtext("{http://www.w3.org/2005/Atom}updated")
    )


def is_hr_focused_source(*values: str) -> bool:
    haystack = " ".join(value or "" for value in values).lower()
    return any(hint.lower() in haystack for hint in HR_FOCUSED_SOURCE_HINTS)


def title_matches_direct_feed(module: str, title: str, source_name: str = "", feed_url: str = "") -> bool:
    if not has_keywords(title, AI_KEYWORDS):
        return False
    if module == "ai_hr":
        return has_keywords(title, HR_KEYWORDS) or is_hr_focused_source(source_name, feed_url)
    return True


def add_feed_candidates(
    root: ET.Element,
    module: str,
    feed_url: str,
    source_name: str,
    query: str,
    tz: ZoneInfo,
    max_per_feed: int,
    max_total: int,
    candidates: list[Candidate],
    seen_urls: set[str],
    direct_feed: bool = False,
    target_day: dt.date | None = None,
) -> bool:
    added = 0
    target_doc_date = fmt_doc_date(target_day) if target_day else None
    items = root.findall(".//item") or root.findall("{http://www.w3.org/2005/Atom}entry")
    for item in items:
        if len(candidates) >= max_total:
            return True
        title = first_text(item, ["title", "{http://www.w3.org/2005/Atom}title"])
        url = item_link(item)
        if not title or not url or url in seen_urls:
            continue
        if direct_feed and not title_matches_direct_feed(module, title, source_name, feed_url):
            continue
        published_at, published_date = parse_feed_datetime(item_published_value(item), tz)
        if direct_feed and target_doc_date and published_date != target_doc_date:
            continue
        seen_urls.add(url)
        candidates.append(
            Candidate(
                module=module,
                title=title,
                url=url,
                source=item_source(item, source_name),
                feed_published_at=published_at,
                feed_published_local_date=published_date,
                query=query,
                feed=feed_url,
            )
        )
        added += 1
        if added >= max_per_feed:
            break
    return False


def add_google_news_candidates(
    module: str,
    queries: list[str],
    tz: ZoneInfo,
    timeout: int,
    max_per_feed: int,
    max_total: int,
    day: dt.date | None,
    candidates: list[Candidate],
    rejected: list[RejectedItem],
    seen_urls: set[str],
) -> bool:
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

            if add_feed_candidates(root, module, feed_url, "Google News", query, tz, max_per_feed, max_total, candidates, seen_urls):
                return True
    return False


def collect_aihot_candidates(
    tz: ZoneInfo,
    timeout: int,
    max_total: int,
    day: dt.date | None,
    candidates: list[Candidate],
    rejected: list[RejectedItem],
    seen_urls: set[str],
) -> None:
    target_doc_date = fmt_doc_date(day) if day else None
    discovered: list[tuple[bool, int, str, Candidate]] = []
    local_seen_urls: set[str] = set()
    for discovery_url in AIHOT_DISCOVERY_URLS:
        try:
            status, _, body = request_url(discovery_url, timeout)
            if status != 200:
                rejected.append(RejectedItem("global_ai", "AIHot", discovery_url, f"AIHot status {status}", "AIHot", "aihot"))
                continue
        except Exception as exc:  # noqa: BLE001 - discovery failure is non-fatal.
            rejected.append(RejectedItem("global_ai", "AIHot", discovery_url, f"AIHot fetch failed: {exc}", "AIHot", "aihot"))
            continue

        for item in parse_aihot_records(body, tz):
            url = item["url"]
            normalized_url = normalize_url(url)
            if normalized_url in seen_urls or normalized_url in local_seen_urls or is_low_verification_url(url):
                continue
            published_date = item["published_local_date"]
            if target_doc_date and published_date != target_doc_date:
                continue
            local_seen_urls.add(normalized_url)
            module = "ai_hr" if aihot_ai_hr_relevance(item["title"], item["summary"], item["source"], url) else "global_ai"
            discovered.append(
                (
                    item["selected"],
                    item["score"],
                    item["published_at"] or "",
                    Candidate(
                        module=module,
                        title=item["title"],
                        url=url,
                        source=item["source"] or "AIHot",
                        feed_published_at=item["published_at"],
                        feed_published_local_date=published_date,
                        query="aihot:selected" if item["selected"] else "aihot:all",
                        feed=discovery_url,
                    ),
                )
            )

    discovered.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
    remaining_slots = max(0, max_total - len(candidates))
    for _, _, _, candidate in discovered[: min(AIHOT_DISCOVERY_LIMIT, remaining_slots)]:
        seen_urls.add(normalize_url(candidate.url))
        candidates.append(candidate)


def aihot_ai_hr_relevance(title: str, summary: str, source: str, url: str) -> bool:
    title_source = f"{title} {source}"
    if has_keywords(title_source, HR_KEYWORDS) or is_hr_focused_source(source, url):
        return True
    if keyword_hit_count(summary, HR_KEYWORDS) >= 2:
        return True
    workforce_phrases = [
        "headcount",
        "slow hiring",
        "job cuts",
        "workforce reduction",
        "员工减少",
        "放缓招聘",
        "减少员工",
        "岗位减少",
        "裁员",
    ]
    summary_lower = summary.lower()
    return any(phrase in summary_lower for phrase in workforce_phrases)


def parse_aihot_records(body: str, tz: ZoneInfo) -> list[dict[str, Any]]:
    pattern = re.compile(
        r'\{\\"id\\":\\"[^\\"]+\\",\\"url\\":\\"(?P<url>(?:\\\\.|[^\\"])*)\\",'
        r'\\"title\\":\\"(?P<title>(?:\\\\.|[^\\"])*)\\",'
        r'\\"titleZh\\":\\"(?P<title_zh>(?:\\\\.|[^\\"])*)\\",'
        r'\\"summaryZh\\":\\"(?P<summary_zh>(?:\\\\.|[^\\"])*)\\".*?'
        r'\\"publishedAt\\":\\"(?P<published_at>[^\\"]+)\\".*?'
        r'\\"aiSelected\\":(?P<selected>true|false).*?'
        r'\\"finalScore\\":(?P<score>\d+).*?'
        r'\\"source\\":\{\\"id\\":\\"[^\\"]+\\",\\"name\\":\\"(?P<source>(?:\\\\.|[^\\"])*)\\"',
        re.S,
    )
    records: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for match in pattern.finditer(body):
        url = decode_aihot_string(match.group("url"))
        normalized_url = normalize_url(url)
        if not url or normalized_url in seen_urls:
            continue
        seen_urls.add(normalized_url)

        title_zh = decode_aihot_string(match.group("title_zh"))
        title = title_zh or decode_aihot_string(match.group("title"))
        published_value = match.group("published_at")
        published_dt = parse_iso_datetime(published_value)
        published_at = local_datetime_label(published_dt, tz) if published_dt else published_value
        published_local_date = local_date(published_dt, tz) if published_dt else None
        records.append(
            {
                "url": url,
                "title": clean_text(title),
                "summary": clean_text(decode_aihot_string(match.group("summary_zh"))),
                "source": clean_text(decode_aihot_string(match.group("source"))),
                "published_at": published_at,
                "published_local_date": published_local_date,
                "selected": match.group("selected") == "true",
                "score": int(match.group("score")),
            }
        )
    return records


def decode_aihot_string(value: str) -> str:
    try:
        return html.unescape(json.loads(f'"{value}"'))
    except json.JSONDecodeError:
        return html.unescape(value.replace(r"\"", '"').replace(r"\n", " "))


def is_low_verification_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).netloc.lower()
    return any(domain == host or host.endswith(f".{domain}") for domain in LOW_VERIFICATION_DOMAINS)


def collect_candidates(tz: ZoneInfo, timeout: int, max_per_feed: int, max_total: int, day: dt.date | None = None) -> tuple[list[Candidate], list[RejectedItem]]:
    candidates: list[Candidate] = []
    rejected: list[RejectedItem] = []
    seen_urls: set[str] = set()

    collect_aihot_candidates(tz, timeout, max_total, day, candidates, rejected, seen_urls)

    # AI+HR is the core product promise, so vertical HR feeds get the first slots
    # before broader Google News and general AI feeds can fill the candidate pool.
    for source_name, feed_url in DIRECT_RSS_FEEDS.get("ai_hr", []):
        try:
            status, _, body = request_url(feed_url, timeout)
            if status != 200:
                rejected.append(RejectedItem("ai_hr", source_name, feed_url, f"RSS status {status}", source_name, "direct_rss"))
                continue
            root = ET.fromstring(body)
        except Exception as exc:  # noqa: BLE001 - recorded in verification report.
            rejected.append(RejectedItem("ai_hr", source_name, feed_url, f"Direct RSS fetch/parse failed: {exc}", source_name, "direct_rss"))
            continue

        if add_feed_candidates(
            root,
            "ai_hr",
            feed_url,
            source_name,
            f"direct_rss:{source_name}",
            tz,
            max_per_feed + 2 if is_hr_focused_source(source_name, feed_url) else max_per_feed,
            max_total,
            candidates,
            seen_urls,
            direct_feed=True,
            target_day=day,
        ):
            return candidates, rejected

    for module, queries in QUERIES.items():
        if add_google_news_candidates(module, queries, tz, timeout, max_per_feed, max_total, day, candidates, rejected, seen_urls):
            return candidates, rejected

    for module, feeds in DIRECT_RSS_FEEDS.items():
        for source_name, feed_url in feeds:
            if module == "ai_hr":
                continue
            try:
                status, _, body = request_url(feed_url, timeout)
                if status != 200:
                    rejected.append(RejectedItem(module, source_name, feed_url, f"RSS status {status}", source_name, "direct_rss"))
                    continue
                root = ET.fromstring(body)
            except Exception as exc:  # noqa: BLE001 - recorded in verification report.
                rejected.append(RejectedItem(module, source_name, feed_url, f"Direct RSS fetch/parse failed: {exc}", source_name, "direct_rss"))
                continue

            if add_feed_candidates(
                root,
                module,
                feed_url,
                source_name,
                f"direct_rss:{source_name}",
                tz,
                max_per_feed,
                max_total,
                candidates,
                seen_urls,
                direct_feed=True,
                target_day=day,
            ):
                return candidates, rejected

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


def parse_candidate_dates(candidates: list[str]) -> list[dt.datetime]:
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


def extract_structured_page_dates(markup: str) -> list[dt.datetime]:
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
    return parse_candidate_dates(candidates)


def extract_page_dates(markup: str, visible_text: str) -> list[dt.datetime]:
    candidates: list[str] = []
    text_patterns = [
        r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b",
        r"\b([A-Z][a-z]+ \d{1,2}, 20\d{2})\b",
    ]
    for match in re.findall(text_patterns[0], visible_text[:3000]):
        year, month, day = match
        candidates.append(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    for match in re.findall(text_patterns[1], visible_text[:3000]):
        candidates.append(match)
    return extract_structured_page_dates(markup) + parse_candidate_dates(candidates)


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


def ai_hr_relevance_established(title: str, text: str, source: str = "", url: str = "", query: str = "") -> bool:
    title_hits = keyword_hit_count(title, HR_KEYWORDS)
    body_hits = keyword_hit_count(text[:2500], HR_KEYWORDS)
    source_focused = is_hr_focused_source(source, url, query)
    if title_hits >= 1 and body_hits >= 1:
        return True
    if source_focused and (title_hits >= 1 or body_hits >= 1):
        return True
    if source_focused and body_hits >= 2:
        return True
    return False


def summarize(title: str, text: str) -> str:
    sentences = re.split(r"(?<=[。.!?])\s+", text)
    for sentence in sentences:
        sentence = clean_text(sentence)
        if 45 <= len(sentence) <= 220 and has_keywords(sentence, AI_KEYWORDS):
            return sentence[:220]
    return clean_text(title)[:220]


def relevance_note(module: str, title: str, text: str, source: str = "", url: str = "", query: str = "") -> str:
    combined = f"{title} {text[:1200]}"
    if module == "ai_hr":
        if has_keywords(combined, HR_KEYWORDS) or is_hr_focused_source(source, url, query):
            return "与招聘、人力资源、人才管理或组织效率直接相关，适合HR、猎头和企业主快速判断业务影响。"
        return "涉及AI对企业经营和劳动力市场的影响，但HR相关性较弱。"
    return "属于全球AI产品、监管、模型、资本或产业动态，适合补充社群的宏观AI判断。"


def source_priority(source: str = "", url: str = "", query: str = "") -> int:
    parsed_host = urllib.parse.urlparse(url or "").netloc.lower()
    haystack = f"{source} {parsed_host} {url} {query}".lower()
    for priority, hints in SOURCE_PRIORITY_HINTS:
        for hint in hints:
            normalized_hint = hint.lower()
            short_hint = re.sub(r"\.(com|org|cn|net|io|live|fyi|google)(/.*)?$", "", normalized_hint)
            if normalized_hint in haystack or (short_hint and short_hint in haystack):
                return priority
    if source and source.lower() not in {"unknown", "google news"}:
        return 6
    return 4


def score_item(module: str, title: str, text: str, source: str, url: str = "", query: str = "") -> int:
    combined = f"{title} {text[:2000]}".lower()
    score = 0
    if has_keywords(combined, AI_KEYWORDS):
        score += 3
    if module == "ai_hr":
        score += min(keyword_hit_count(title, HR_KEYWORDS) * 3, 9)
        score += min(keyword_hit_count(text[:2000], HR_KEYWORDS) * 2, 8)
        if is_hr_focused_source(source, url, query):
            score += 8
    score += source_priority(source, url, query)
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

        structured_page_dates = extract_structured_page_dates(markup)
        matching_structured_dates = [value for value in structured_page_dates if local_date(value, tz) == doc_date]
        if structured_page_dates and not matching_structured_dates:
            found = sorted({local_date(value, tz) for value in structured_page_dates})[:5]
            rejected.append(
                RejectedItem(
                    candidate.module,
                    candidate.title,
                    source_url,
                    f"Structured page date contradicts {doc_date}; found {found or ['unknown']}",
                    candidate.source,
                    candidate.query,
                )
            )
            continue

        combined = f"{candidate.title} {visible_text[:2000]}"
        if not has_keywords(combined, AI_KEYWORDS):
            rejected.append(RejectedItem(candidate.module, candidate.title, source_url, "AI relevance not established", candidate.source, candidate.query))
            continue
        if candidate.module == "ai_hr" and not ai_hr_relevance_established(
            candidate.title,
            visible_text,
            candidate.source,
            source_url,
            candidate.query,
        ):
            rejected.append(RejectedItem(candidate.module, candidate.title, source_url, "AI+HR relevance not established", candidate.source, candidate.query))
            continue

        page_date_label = (
            local_datetime_label(matching_structured_dates[0], tz)
            if matching_structured_dates
            else "页面未提供可解析的结构化发布时间，已以RSS发布时间作为当日证据"
        )
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
                relevance=relevance_note(candidate.module, candidate.title, visible_text, candidate.source, source_url, candidate.query),
                fetched_at=now.isoformat(),
                verification_note=note,
                score=score_item(candidate.module, candidate.title, visible_text, candidate.source, source_url, candidate.query),
            )
        )

    return dedupe_and_limit(accepted, max_items_per_module), rejected


def dedupe_and_limit(items: list[AcceptedItem], limit: int) -> list[AcceptedItem]:
    result: list[AcceptedItem] = []
    for module in MODULES:
        module_items = [item for item in items if item.module == module]
        unique_items = dedupe_event_items(module_items)
        unique_items.sort(
            key=lambda item: (
                item.published_at,
                item.score + source_priority(item.source, item.final_url or item.url),
                source_priority(item.source, item.final_url or item.url),
            ),
            reverse=True,
        )
        result.extend(unique_items[:limit])
    return result


def dedupe_event_items(items: list[AcceptedItem]) -> list[AcceptedItem]:
    groups: list[list[AcceptedItem]] = []
    for item in items:
        item_url = normalize_url(item.final_url or item.url)
        matched_group: list[AcceptedItem] | None = None
        for group in groups:
            if any(normalize_url(existing.final_url or existing.url) == item_url for existing in group):
                matched_group = group
                break
            if title_similarity(item.title, group[0].title) >= 0.62:
                matched_group = group
                break
        if matched_group is None:
            groups.append([item])
        else:
            matched_group.append(item)
    return [max(group, key=item_rank_key) for group in groups]


def item_rank_key(item: AcceptedItem) -> tuple[int, int, str]:
    priority = source_priority(item.source, item.final_url or item.url)
    return (priority, item.score, item.published_at)


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    query = [(key, value) for key, value in query if not key.lower().startswith("utm_")]
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", urllib.parse.urlencode(query), ""))


def title_similarity(first: str, second: str) -> float:
    first_tokens = title_tokens(first)
    second_tokens = title_tokens(second)
    if not first_tokens or not second_tokens:
        return 0.0
    overlap = len(first_tokens & second_tokens)
    union = len(first_tokens | second_tokens)
    return overlap / union if union else 0.0


def title_tokens(title: str) -> set[str]:
    text = clean_text(title).lower()
    text = re.sub(r"\s+[-–—]\s+[^-–—]{2,40}$", "", text)
    english = re.findall(r"[a-z0-9]{2,}", text)
    chinese_segments = re.findall(r"[\u4e00-\u9fff]+", text)
    chinese_tokens: list[str] = []
    for segment in chinese_segments:
        if len(segment) == 1:
            chinese_tokens.append(segment)
        else:
            chinese_tokens.extend(segment[index : index + 2] for index in range(len(segment) - 1))
    stopwords = {"news", "daily", "today", "latest", "update", "updates"}
    return {token for token in english + chinese_tokens if token not in stopwords}


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


def poster_font(size: int, bold: bool = False) -> Any:
    if ImageFont is None:
        raise RuntimeError("Pillow is required to generate poster PNGs.")
    for path in POSTER_BOLD_FONTS if bold else POSTER_REGULAR_FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def text_width(draw: Any, text: str, font: Any) -> float:
    return draw.textlength(text, font=font)


def wrap_text(draw: Any, text: str, font: Any, max_width: int, max_lines: int) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    lines: list[str] = []
    current = ""
    for char in text:
        trial = current + char
        if text_width(draw, trial, font) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = char
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and text_width(draw, "".join(lines), font) < text_width(draw, text, font):
        line = lines[-1].rstrip("，。,. ")
        while line and text_width(draw, line + "...", font) > max_width:
            line = line[:-1].rstrip()
        lines[-1] = (line or lines[-1][:1]) + "..."
    return lines


def draw_wrapped_text(
    draw: Any,
    xy: tuple[int, int],
    text: str,
    font: Any,
    fill: str,
    max_width: int,
    max_lines: int,
    line_gap: int = 10,
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width, max_lines)
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y = bbox[3] + line_gap
    return y


def module_items(accepted: list[AcceptedItem], module: str, limit: int) -> list[AcceptedItem]:
    items = [item for item in accepted if item.module == module]
    return items[:limit]


def poster_items(accepted: list[AcceptedItem], limit: int = 6) -> list[AcceptedItem]:
    ai_hr_items = module_items(accepted, "ai_hr", limit)
    global_items = module_items(accepted, "global_ai", max(0, limit - len(ai_hr_items)))
    items = ai_hr_items + global_items
    if len(items) < limit:
        seen = {normalize_url(item.final_url or item.url) for item in items}
        for item in accepted:
            key = normalize_url(item.final_url or item.url)
            if key in seen:
                continue
            items.append(item)
            seen.add(key)
            if len(items) >= limit:
                break
    return items[:limit]


def poster_theme_terms(accepted: list[AcceptedItem], limit: int = 3) -> list[str]:
    focus_items = [item for item in accepted if item.module == "ai_hr"] or accepted
    scores: dict[str, int] = {}
    for item in focus_items:
        text = f"{item.title} {item.summary} {item.source}".lower()
        for label, needles in POSTER_THEME_RULES:
            score = 0
            for needle in needles:
                if needle.lower() in text:
                    score += 1
            if score:
                if item.module == "ai_hr":
                    score += 1
                scores[label] = scores.get(label, 0) + score
    terms = [label for label, _ in sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))]
    if not terms and accepted:
        return ["企业AI", "智能体", "组织效率"][:limit]
    return terms[:limit]


def poster_headline(accepted: list[AcceptedItem]) -> tuple[str, str]:
    ai_hr_count = len([item for item in accepted if item.module == "ai_hr"])
    terms = poster_theme_terms(accepted)
    if ai_hr_count:
        return "今日AI+HR关键词", " × ".join(terms or ["AI招聘", "组织效率"])
    if accepted:
        return "今日AI速递关键词", " × ".join(terms or ["企业AI", "大模型"])
    return "今天，", "暂无高质量当日信源。"


def draw_grid(draw: Any) -> None:
    for x in range(34, POSTER_SIZE[0] - 33, 62):
        draw.line((x, 34, x, POSTER_SIZE[1] - 34), fill="#EAF0EC", width=1)
    for y in range(34, POSTER_SIZE[1] - 33, 62):
        draw.line((34, y, POSTER_SIZE[0] - 34, y), fill="#EAF0EC", width=1)


def draw_centered_text(draw: Any, box: tuple[int, int, int, int], text: str, font: Any, fill: str) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    width = bbox[2] - bbox[0]
    height = bbox[3] - bbox[1]
    x = box[0] + (box[2] - box[0] - width) / 2
    y = box[1] + (box[3] - box[1] - height) / 2 - 2
    draw.text((x, y), text, font=font, fill=fill)


def draw_news_card(
    draw: Any,
    index: int,
    item: AcceptedItem | None,
    y: int,
    accent: str,
    fonts: dict[str, Any],
    card_height: int,
    card_gap: int,
) -> int:
    left = 64
    right = POSTER_SIZE[0] - 64
    draw.rounded_rectangle((left + 5, y + 6, right + 5, y + card_height + 6), radius=20, fill="#DEE8E1")
    draw.rounded_rectangle((left, y, right, y + card_height), radius=20, fill="#FFFFFF", outline="#E2E9E5", width=1)
    draw.rounded_rectangle((left, y, left + 8, y + card_height), radius=4, fill=accent)

    number = f"{index:02d}"
    number_bbox = draw.textbbox((0, 0), number, font=fonts["card_number"])
    number_y = y + (card_height - (number_bbox[3] - number_bbox[1])) / 2 - 4
    draw.text((left + 44, number_y), number, font=fonts["card_number"], fill=accent)

    if item is None:
        draw.text((left + 150, y + 34), "当日无高质量信息源", font=fonts["item"], fill="#172033")
        return y + card_height + card_gap

    module_label = "AI+HR" if item.module == "ai_hr" else "GLOBAL AI"
    source_label = item.source if item.source and item.source != "Unknown" else "已校验"
    meta = f"{module_label}   {source_label}   已校验"
    draw.text((left + 150, y + 20), meta, font=fonts["meta"], fill=accent)
    draw_wrapped_text(
        draw,
        (left + 150, y + 52),
        item.title,
        fonts["item"],
        "#172033",
        right - left - 204,
        2,
        line_gap=2,
    )
    return y + card_height + card_gap


def render_poster(day: dt.date, accepted: list[AcceptedItem], output_path: Path) -> Path:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required to generate poster PNGs.")

    image = Image.new("RGB", POSTER_SIZE, "#F7FAF8")
    draw = ImageDraw.Draw(image)
    selected_items = poster_items(accepted, 6)
    display_count = len(selected_items) if selected_items else 3
    compact = display_count >= 6
    fonts = {
        "brand": poster_font(36, bold=True),
        "brand_sub": poster_font(17),
        "big_day": poster_font(142, bold=True),
        "month": poster_font(32, bold=True),
        "weekday": poster_font(25),
        "headline": poster_font(52, bold=True),
        "headline_small": poster_font(45 if compact else 48, bold=True),
        "subtitle": poster_font(25),
        "card_number": poster_font(34 if compact else 38, bold=True),
        "item": poster_font(23 if compact else 25, bold=True),
        "meta": poster_font(17 if compact else 18, bold=True),
        "footer": poster_font(23),
        "badge": poster_font(23, bold=True),
    }

    draw_grid(draw)
    draw.rectangle((0, 0, POSTER_SIZE[0], 28), fill="#E9F7EF")

    logo_box = (64, 58, 108, 102)
    draw.rounded_rectangle(logo_box, radius=12, fill="#20C997")
    draw_centered_text(draw, logo_box, "J", fonts["badge"], "#FFFFFF")
    draw.text((124, 50), "Jiaer AIHR", font=fonts["brand"], fill="#0C172A")
    draw.text((126, 92), "DAILY AI + HR BRIEF", font=fonts["brand_sub"], fill="#7E8EA0")
    draw.rounded_rectangle((958, 46, 1032, 92), radius=23, fill="#D9E3DD")
    draw_centered_text(draw, (958, 46, 1032, 92), "1/1", fonts["badge"], "#FFFFFF")

    day_text = f"{day.day:02d}"
    draw.rounded_rectangle((64, 150, 70, 260), radius=3, fill="#20C997")
    draw.text((98, 132), day_text, font=fonts["big_day"], fill="#18B981")
    draw.text((288, 171), day.strftime("%b %Y").upper(), font=fonts["month"], fill="#6B7A90")
    draw.text((290, 216), WEEKDAY_LABELS[day.weekday()], font=fonts["weekday"], fill="#172033")

    headline_prefix, headline_terms = poster_headline(accepted)
    draw.text((64, 318), headline_prefix, font=fonts["headline"], fill="#0C172A")
    draw_wrapped_text(
        draw,
        (64, 388),
        headline_terms,
        fonts["headline_small"],
        "#16A877",
        930,
        2,
        line_gap=2,
    )
    card_accents = ["#20C997", "#10B981", "#86D36A", "#5DBB63", "#2A9D8F"]
    card_gap = 12 if compact else 16
    card_height = 106 if compact else 116
    y = 486 if compact else 500
    if selected_items:
        for index, item in enumerate(selected_items, start=1):
            y = draw_news_card(
                draw,
                index,
                item,
                y,
                card_accents[(index - 1) % len(card_accents)],
                fonts,
                card_height,
                card_gap,
            )
    else:
        for index in range(1, 4):
            y = draw_news_card(
                draw,
                index,
                None,
                y,
                card_accents[(index - 1) % len(card_accents)],
                fonts,
                card_height,
                card_gap,
            )

    footer_y = 1280
    draw.line((64, footer_y, 1016, footer_y), fill="#DCE6E0", width=2)
    cta = "详细内容点击微信群置顶链接查看～"
    cta_bbox = draw.textbbox((0, 0), cta, font=fonts["footer"])
    cta_x = (POSTER_SIZE[0] - (cta_bbox[2] - cta_bbox[0])) / 2
    draw.text((cta_x, footer_y + 42), cta, font=fonts["footer"], fill="#16A877")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, "PNG", optimize=True)
    return output_path


def render_combined_markdown(markdown_paths: list[Path]) -> str:
    sections = [path.read_text(encoding="utf-8").strip() for path in markdown_paths]
    return "\n\n".join(section for section in sections if section).strip() + "\n"


def write_outputs(
    output_dir: Path,
    day: dt.date,
    accepted: list[AcceptedItem],
    rejected: list[RejectedItem],
    candidates: list[Candidate],
    generate_poster: bool = True,
) -> tuple[Path, Path | None]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_date = fmt_doc_date(day)
    markdown_path = output_dir / f"{doc_date}.md"
    report_path = output_dir / "verification_report.json"
    poster_path: Path | None = None
    poster_error: str | None = None
    markdown = render_markdown(day, accepted, rejected)
    markdown_path.write_text(markdown, encoding="utf-8")
    if generate_poster:
        try:
            poster_path = render_poster(day, accepted, output_dir / f"{doc_date}-poster.png")
        except Exception as exc:  # noqa: BLE001 - poster failure should not block text brief.
            poster_error = str(exc)
    report = {
        "daily_section_date": doc_date,
        "generated_at": dt.datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
        "candidate_count": len(candidates),
        "poster_path": str(poster_path) if poster_path else None,
        "poster_error": poster_error,
        "accepted": [dataclasses.asdict(item) for item in accepted],
        "rejected": [dataclasses.asdict(item) for item in rejected],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return markdown_path, poster_path


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


def feishu_patch(base_url: str, path: str, token: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    return feishu_request(base_url, path, token, payload, timeout, "PATCH")


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


def feishu_upload_media(
    base_url: str,
    token: str,
    image_block_id: str,
    image_path: Path,
    timeout: int,
    document_id: str | None = None,
) -> str:
    image_bytes = image_path.read_bytes()
    boundary = f"----aihrposter{uuid.uuid4().hex}"
    fields = {
        "file_name": image_path.name,
        "parent_type": "docx_image",
        "parent_node": image_block_id,
        "size": str(len(image_bytes)),
    }
    if document_id:
        fields["extra"] = json.dumps({"drive_route_token": document_id}, ensure_ascii=False)
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.append(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")
        )
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{image_path.name}"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode("utf-8")
    )
    parts.append(image_bytes)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)

    path = "/open-apis/drive/v1/medias/upload_all"
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            response_body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Feishu HTTP {exc.code} at {path}: {response_body}") from exc

    result = json.loads(response_body)
    if result.get("code") not in (0, None):
        raise RuntimeError(f"Feishu API error at {path}: {result}")
    file_token = result.get("data", {}).get("file_token")
    return str(file_token or "")


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


def delete_feishu_root_range(
    base_url: str,
    document_id: str,
    root_block_id: str,
    token: str,
    timeout: int,
    revision_id: int,
    start_index: int,
    end_index: int,
) -> None:
    query = urllib.parse.urlencode({"document_revision_id": revision_id})
    feishu_delete(
        base_url,
        f"/open-apis/docx/v1/documents/{document_id}/blocks/{root_block_id}/children/batch_delete?{query}",
        token,
        {"start_index": start_index, "end_index": end_index},
        timeout,
    )


def replace_feishu_image(
    base_url: str,
    document_id: str,
    image_block_id: str,
    token: str,
    timeout: int,
    revision_id: int,
    file_token: str,
) -> int:
    query = urllib.parse.urlencode({"document_revision_id": revision_id})
    result = feishu_patch(
        base_url,
        f"/open-apis/docx/v1/documents/{document_id}/blocks/{image_block_id}?{query}",
        token,
        {"replace_image": {"token": file_token}},
        timeout,
    )
    next_revision_id = result.get("data", {}).get("document_revision_id")
    return next_revision_id if isinstance(next_revision_id, int) else revision_id


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


def insert_feishu_poster(
    base_url: str,
    document_id: str,
    root_block_id: str,
    token: str,
    timeout: int,
    revision_id: int,
    poster_path: Path,
    index: int = 1,
) -> int:
    if not poster_path.exists():
        raise RuntimeError(f"Poster path does not exist: {poster_path}")

    query = urllib.parse.urlencode({"document_revision_id": revision_id})
    result = feishu_api(
        base_url,
        f"/open-apis/docx/v1/documents/{document_id}/blocks/{root_block_id}/children?{query}",
        token,
        {"children": [{"block_type": 27, "image": {}}], "index": index},
        timeout,
    )
    data = result.get("data", {})
    children = data.get("children") or []
    image_block_id = children[0].get("block_id") if children else None
    next_revision_id = data.get("document_revision_id")
    if not image_block_id or not isinstance(next_revision_id, int):
        raise RuntimeError(f"Feishu image block response did not contain block_id/revision_id: {result}")

    try:
        file_token = feishu_upload_media(base_url, token, str(image_block_id), poster_path, timeout, document_id)
        if file_token:
            next_revision_id = replace_feishu_image(
                base_url,
                document_id,
                str(image_block_id),
                token,
                timeout,
                next_revision_id,
                file_token,
            )
    except Exception:
        try:
            delete_feishu_root_range(
                base_url,
                document_id,
                root_block_id,
                token,
                timeout,
                next_revision_id,
                index,
                index + 1,
            )
        except Exception as cleanup_exc:  # noqa: BLE001 - log best-effort cleanup only.
            print(f"::warning::Failed to remove empty Feishu poster block: {cleanup_exc}")
        raise

    print(f"Feishu poster inserted: {poster_path} ({file_token or 'uploaded'})")
    return get_feishu_document_revision_id(base_url, document_id, token, timeout)


def publish_feishu(
    markdown_path: Path,
    title: str,
    timeout: int,
    replace_existing: bool = False,
    poster_path: Path | None = None,
) -> str:
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

    if poster_path:
        try:
            revision_id = insert_feishu_poster(base_url, document_id, root_block_id, token, timeout, revision_id, poster_path)
        except Exception as exc:  # noqa: BLE001 - keep the text brief live even if poster delivery needs extra scope.
            print(f"::warning::Feishu poster insert failed: {exc}")
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
    poster_paths: list[Path] = []
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
        ai_hr_count = len([item for item in accepted if item.module == "ai_hr"])
        if ai_hr_count < AI_HR_SHORTAGE_THRESHOLD:
            seen_urls = {candidate.url for candidate in candidates}
            fallback_candidates: list[Candidate] = []
            fallback_rss_rejections: list[RejectedItem] = []
            add_google_news_candidates(
                "ai_hr",
                AI_HR_FALLBACK_QUERIES,
                tz,
                args.timeout,
                args.max_candidates_per_feed + 1,
                max(args.max_total_candidates // 2, 24),
                day,
                fallback_candidates,
                fallback_rss_rejections,
                seen_urls,
            )
            if fallback_candidates:
                fallback_accepted, fallback_verification_rejections = verify_candidates(
                    fallback_candidates,
                    day,
                    tz,
                    args.timeout,
                    args.max_items_per_module,
                    args.allow_backfill or len(days) > 1,
                )
                accepted = dedupe_and_limit(accepted + fallback_accepted, args.max_items_per_module)
                candidates.extend(fallback_candidates)
                rejected.extend(fallback_rss_rejections + fallback_verification_rejections)
            else:
                rejected.extend(fallback_rss_rejections)

        markdown_path, poster_path = write_outputs(
            output_dir / fmt_doc_date(day) if len(days) > 1 else output_dir,
            day,
            accepted,
            rejected,
            candidates,
            generate_poster=not args.skip_poster,
        )
        markdown_paths.append(markdown_path)
        if poster_path:
            poster_paths.append(poster_path)
        total_accepted += len(accepted)
        total_rejected += len(rejected)

        print(f"Daily section: {fmt_doc_date(day)}")
        print(f"Markdown: {markdown_path}")
        if poster_path:
            print(f"Poster: {poster_path}")
        print(f"Accepted: {len(accepted)}")
        print(f"Rejected: {len(rejected)}")

    publish_path = markdown_paths[0]
    if len(markdown_paths) > 1:
        output_dir.mkdir(parents=True, exist_ok=True)
        publish_path = output_dir / f"{fmt_doc_date(days[-1])}_to_{fmt_doc_date(days[0])}.md"
        publish_path.write_text(render_combined_markdown(markdown_paths), encoding="utf-8")
        print(f"Combined Markdown: {publish_path}")

    if args.publish_feishu:
        feishu_poster_path = poster_paths[0] if len(days) == 1 and poster_paths else None
        url = publish_feishu(publish_path, fmt_doc_date(days[0]), args.timeout, args.replace_feishu, feishu_poster_path)
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
    print(f"Total posters: {len(poster_paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
