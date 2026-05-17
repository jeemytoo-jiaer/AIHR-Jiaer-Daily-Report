---
name: ai-hr-daily-brief
description: Create and publish a daily AI+HR intelligence brief into one persistent Feishu document for Xiaohongshu/Feishu communities. Use when Codex needs to collect same-day AI+HR and global AI news, enforce strict date/source verification, prepend a dated Chinese Feishu-ready section, or maintain an 08:00 Asia/Shanghai scheduled news workflow for HR, recruiters, and business owners.
---

# AI+HR Daily Brief

## Purpose

Produce a same-day, source-backed daily brief for 嘉尔's HR, recruiter, and founder audience. The brief must never pad with stale news. If no same-day high-quality sources pass verification, write `当日无高质量信息源`.

## Output Contract

Use the target date in Asia/Shanghai. Publish into one existing Feishu document and prepend the daily section at the top. The daily section heading must be `YYYY.MM.DD`.

Render the document in reverse chronological order within each module:

1. `🔮 AI+HR深度聚焦`
2. `🌐 全球AI资讯速递`

Each accepted item must include:

- Title in Chinese
- One-sentence factual summary
- Why it matters to HR/recruiters/founders
- Source name
- Published date/time
- Original URL
- Verification note with fetch time and date evidence

## Mandatory Quality Gate

Before writing to Feishu, complete this checklist exactly:

1. Every news item passed three-step date verification: search/fetch timestamp, content date, and published date all support the target date.
2. No item was assigned to the wrong date. Reject old year/same month-day and same year/wrong day cases.
3. Every link opened successfully and contained substantive article content.
4. No empty day was filled with stale news. If no qualifying items exist, output `当日无高质量信息源`.
5. The daily section heading and all date blocks match the target date.

## Workflow

1. Load `references/source-and-quality-policy.md` when selecting sources, queries, and acceptance criteria.
2. Run `scripts/ai_hr_daily_brief.py` to collect, verify, rank, and render the brief.
3. If publishing to Feishu, load `references/feishu-setup.md`, provide the required environment variables, and run the script with `--publish-feishu`.
4. Review the generated `verification_report.json` before publishing when the result contains any accepted item.
5. Keep the final human-facing summary concise: daily section date, accepted item counts, rejected item counts, Feishu URL if published, and any residual risk.

## Script Quick Start

Generate local output only:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/ai_hr_daily_brief.py --output-dir output
```

Generate for a specific date:

```bash
python3 scripts/ai_hr_daily_brief.py --target-date 2026.05.17 --output-dir output
```

Publish to Feishu:

```bash
FEISHU_APP_ID=cli_xxx \
FEISHU_APP_SECRET=xxx \
FEISHU_DOCUMENT_ID=doxcnxxx \
python3 scripts/ai_hr_daily_brief.py --publish-feishu --output-dir output
```

## Scheduling

For GitHub Actions, use `.github/workflows/daily-ai-hr-brief.yml`. It runs at 08:00 Asia/Shanghai (`00:00 UTC`) and expects Feishu secrets to be configured in the GitHub repository. Each run prepends the new daily section to the same Feishu document.
