---
name: ai-hr-daily-brief
description: Create and publish a daily AI+HR intelligence brief into one persistent Feishu document for Xiaohongshu/Feishu communities. Use when Codex needs to collect same-day AI+HR and global AI news, enforce strict date/source verification, prepend a dated Chinese Feishu-ready section, or maintain an 08:00 Asia/Shanghai scheduled news workflow for HR, recruiters, and business owners.
---

# AI+HR Daily Brief

## Purpose

Produce a same-day, source-backed daily brief for 嘉尔's HR, recruiter, and founder audience. The brief must never pad with stale news. If no same-day high-quality sources pass verification, write `当日无高质量信息源`.

This is a standing daily requirement. Do not ask the user to restate the freshness, date, or Feishu update rules each day; enforce them from this skill and the scheduled workflow.

In addition to the Feishu text brief, generate one daily poster image for easy sharing in Xiaohongshu, Feishu groups, and WeChat groups. For single-day scheduled runs, insert the poster into the same Feishu daily section after the date heading. Always keep the PNG as a GitHub Actions artifact as a fallback.

## Output Contract

Use the target date in Asia/Shanghai. Publish into one existing Feishu document and prepend the daily section at the top. The daily section heading must be `YYYY.MM.DD`.

Render the document in reverse chronological order within each module:

1. `🔮 AI+HR深度聚焦`
2. `🌐 全球AI资讯速递`

Each accepted item must include:

- Title in Chinese
- One-sentence factual summary
- Original URL

Do not include backend audit details in the Feishu document body, including source-only rows, raw publish timestamps, verification notes, self-check checklists, or collection statistics. Keep those details only in `verification_report.json`.

## Poster Contract

Generate a 1080x1440 PNG poster for every daily section unless `--skip-poster` is explicitly set. Save it next to the Markdown output as `YYYY.MM.DD-poster.png`.

Poster layout:

1. Light grid background with a green-first palette, `Jiaer AIHR` brand mark, and `DAILY AI + HR BRIEF` subtitle.
2. Large day number, month/year, and weekday as the first visual focus.
3. Main headline must be generated from the day’s accepted items. Use 2-3 concrete topic keywords such as `AI招聘 × 员工体验 × 企业智能体`. If there are no AI+HR items, do not claim AI+HR progress; use `今日AI速递关键词` or `今天，暂无高质量当日信源。`.
4. Show up to six rounded news cards in reverse-priority order, mixing AI+HR and global AI items while prioritizing AI+HR when available. Card typography and spacing must adapt so every title stays inside its card.
5. Footer call-to-action: `详细内容点击微信群置顶链接查看～`.

Poster body must not include raw timestamps, backend verification notes, collection statistics, stale filler, or generic slogans unrelated to the accepted items. If a module has no accepted item, write `当日无高质量...信息源` for that module.

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
FEISHU_DOCUMENT_ID='https://xxx.feishu.cn/docx/U8xXd7p5toLGWKxSScmc2CfAnde' \
FEISHU_REFRESH_TOKEN=xxx \
python3 scripts/ai_hr_daily_brief.py --publish-feishu --output-dir output
```

For manually owned Feishu cloud documents, generate the first personal OAuth refresh token:

```bash
FEISHU_APP_ID=cli_xxx \
FEISHU_REDIRECT_URI='https://example.com/feishu-oauth-callback' \
python3 scripts/feishu_oauth.py auth-url

FEISHU_APP_ID=cli_xxx \
FEISHU_APP_SECRET=xxx \
python3 scripts/feishu_oauth.py exchange-code --code 'PASTE_REDIRECTED_URL_HERE'
```

## Scheduling

For GitHub Actions, use `.github/workflows/daily-ai-hr-brief.yml`. It runs at 08:00 Asia/Shanghai (`00:00 UTC`) and expects Feishu secrets to be configured in the GitHub repository. Each run prepends the new daily section to the same Feishu document.

The scheduled run must search both overseas and domestic sources by default. AI+HR is the first-priority product promise: search vertical HR technology and HR analyst sources before broad AI feeds, then use global AI sources as a supplement. Closed platforms may only be used when the article body, link, and date can be verified without login or manual screenshots.

The scheduled run inserts the daily poster into the Feishu document for single-day runs and also uploads the PNG as a GitHub Actions artifact together with the Markdown and verification report.

If a manually created Feishu document rejects app writes, run `.github/workflows/create-feishu-doc.yml` once with `FEISHU_FOLDER_TOKEN` configured. Use its printed `FEISHU_DOCUMENT_ID` for the daily workflow.

If Feishu also rejects app-created documents or folders, use personal OAuth instead. Add `FEISHU_REFRESH_TOKEN` and `GH_SECRET_PAT` as GitHub Actions secrets so the scheduled workflow can write as the document owner and rotate the Feishu refresh token after every run.

For personal OAuth, the Feishu app must open the Docx permissions as user-identity scopes, not only app-identity scopes. The OAuth helper requests `docx:document docx:document:write_only` by default.

To insert posters into Feishu, the Feishu app also needs `docs:document.media:upload` for adding images/attachments to documents, and the OAuth refresh token must be regenerated after the permission is published. If this scope is missing, the workflow must still publish the text brief and keep the poster PNG in the GitHub Actions artifact.
