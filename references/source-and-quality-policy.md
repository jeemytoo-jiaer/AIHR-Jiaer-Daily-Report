# Source And Quality Policy

## Audience

Write for HR professionals, recruiters, headhunters, and business owners in first-tier and new first-tier cities. Prefer practical implications over generic AI excitement.

## Recommended Source Mix

Prioritize primary and high-signal sources:

- Structured AI daily aggregators such as AIHot, only as discovery input. Borrow selected status, quality/final score, publish time, tags, duplicate count, source name, and recommendation reason as ranking signals. The original article still needs date, link, and content verification before it can enter the Feishu document.
- Company newsroom or official product/security/legal blog
- Regulator, court, standards body, or government source
- Research lab, university, or paper repository when the paper is the news
- Major business and technology outlets with visible publication timestamps
- Domestic technology/business media with RSS or indexable article pages, including 36Kr, TMTPost, QbitAI, InfoQ China, iFanr, ITHome, Leiphone, OSChina, and SSPAI
- HR technology outlets only when the article has concrete evidence, named companies, or product details
- Vertical HR and HR technology sources should be checked before broad AI sources, including HRoot, HRTechChina, Moka, Beisen, HRTech Series, HR Executive, Josh Bersin, Workday, LinkedIn Talent Solutions, SHRM, and credible HR SaaS vendor newsrooms when the page has a visible same-day date.
- Employment-impact sources such as AILayoff.live, LayoffHedge, and Layoffs.fyi can be used for AI/workforce context when the original event date and source page are independently verifiable.

Avoid:

- Unsourced social posts
- Weakly verifiable X/Twitter links unless there is a separate original article, newsroom page, report, or transcript to verify
- Closed or login-gated social/community posts whose article body and date cannot be independently verified
- SEO listicles
- Rewritten syndicated snippets without original reporting
- Old articles resurfaced by search engines
- Articles where the visible date cannot be reconciled with the target date

## Query Families

Run queries in parallel across Chinese and English where possible. Use a same-day date filter first; do not accept older items into the daily brief.

AI+HR deep focus:

- `AI HR`
- `AI recruiting`
- `AI hiring`
- `AI hiring layoffs workforce news`
- `AI job market`
- `AI workforce disruption`
- `talent acquisition AI`
- `HR tech AI`
- `workforce AI`
- `employee experience AI`
- `people analytics AI`
- `workforce planning AI`
- `AI interview`
- `AI resume screening`
- `AI onboarding`
- `AI performance management`
- `AI skills gap`
- `AI training employees`
- `AI reskilling`
- `AI upskilling`
- `agentic AI HR`
- `人力资源 AI`
- `招聘 AI`
- `猎头 AI`
- `AI 就业`
- `AI 裁员`
- `AI 劳动力`
- `AI 技能培训`
- `AI员工`
- `AI面试`
- `AI简历筛选`
- `AI招聘助手`
- `AI绩效`
- `AI员工体验`
- `AI人才管理`
- `AI组织效率`
- `数字员工`
- `AI人事`
- `AI招聘系统`
- Domestic site-targeted searches for 36Kr, TMTPost, InfoQ China, HRoot, HRTechChina, and Moka when the query is AI+HR-specific
- Employment/workforce site-targeted searches for SHRM, Workday, LinkedIn Talent Blog, HR Executive, HRTech Series, AILayoff, LayoffHedge, and Layoffs.fyi. Vertical HR queries must still include AI terms; do not admit ordinary HR articles merely because they mention workforce, talent, or benefits.

Global AI speed brief:

- `artificial intelligence`
- `AI regulation`
- `AI model release`
- `AI safety`
- `generative AI enterprise`
- `AI model release product launch`
- `AI startup funding`
- `AI IPO`
- `AI industry news`
- `OpenAI`
- `Google DeepMind`
- `Anthropic`
- `Microsoft AI`
- `NVIDIA AI`
- `人工智能`
- `大模型`
- `生成式AI`
- Domestic site-targeted searches for 36Kr, TMTPost, QbitAI, Machine Heart, ITHome, Leiphone, InfoQ China, and iFanr
- English source-targeted searches for CNBC, TechCrunch, The Verge, Reuters, OpenAI, Anthropic, Google DeepMind, Hugging Face, and arXiv

## Acceptance Rules

Accept an item only when all are true:

1. The feed/search published date matches the target date in Asia/Shanghai.
2. The URL opens with HTTP 200 after redirects.
3. Extracted visible text is substantive enough to summarize.
4. The item is relevant to one of the two document modules.
5. The item is not a duplicate of a higher-quality source.

If a source has a date in another timezone, convert it to Asia/Shanghai for final matching. Reject the item when a structured source-page publish date clearly contradicts the target date. If the source page does not expose a structured publish date, use the same-day feed timestamp as the date gate and keep the missing page-date note only in `verification_report.json`; do not publish raw timestamps, source-only rows, checklists, or collection statistics into the reader-facing Feishu document.

If fewer than three AI+HR items pass, run a same-day fallback search across employment, layoff, skills, reskilling, training, recruiting, people analytics, and HR technology terms. The fallback widens topic vocabulary, not the final accepted date window.

## Ranking

Rank accepted items by:

1. Direct HR/recruiting/workforce relevance
2. Primary-source credibility
3. Business impact for HR, recruiters, and founders
4. Freshness within the target date
5. Specificity of evidence

Prefer fewer strong items over many weak ones.

When the same event appears in several sources, deduplicate by event-title similarity instead of URL alone. Keep the source in this order: official/company/regulator page, major mainstream or technology media, evidence-rich HR vertical source, domestic technology/business media, then smaller secondary sources.

## AI+HR Classification

Do not rely on the literal string `HR` alone. Treat an item as AI+HR when same-day content connects AI to at least one of these people/organization scenarios:

- recruiting, sourcing, interviewing, resume screening, ATS, candidate experience
- talent management, performance, learning and development, succession, workforce planning
- employee experience, onboarding, HR service delivery, HR shared services
- people analytics, HCM/HRIS, organization efficiency, digital employees, enterprise AI agents used by HR or managers

Vertical HR sources can provide additional confidence, but they do not override the date/link/content quality gate.
