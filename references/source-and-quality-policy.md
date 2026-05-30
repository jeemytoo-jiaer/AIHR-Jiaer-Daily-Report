# Source And Quality Policy

## Audience

Write for HR professionals, recruiters, headhunters, and business owners in first-tier and new first-tier cities. Prefer practical implications over generic AI excitement.

## Recommended Source Mix

Prioritize primary and high-signal sources:

- Company newsroom or official product/security/legal blog
- Regulator, court, standards body, or government source
- Research lab, university, or paper repository when the paper is the news
- Major business and technology outlets with visible publication timestamps
- Domestic technology/business media with RSS or indexable article pages, including 36Kr, TMTPost, QbitAI, InfoQ China, iFanr, ITHome, Leiphone, OSChina, and SSPAI
- HR technology outlets only when the article has concrete evidence, named companies, or product details
- Vertical HR and HR technology sources should be checked before broad AI sources, including HRoot, HRTechChina, Moka, Beisen, HRTech Series, HR Executive, Josh Bersin, Workday, LinkedIn Talent Solutions, SHRM, and credible HR SaaS vendor newsrooms when the page has a visible same-day date.

Avoid:

- Unsourced social posts
- Closed or login-gated social/community posts whose article body and date cannot be independently verified
- SEO listicles
- Rewritten syndicated snippets without original reporting
- Old articles resurfaced by search engines
- Articles where the visible date cannot be reconciled with the target date

## Query Families

AI+HR deep focus:

- `AI HR`
- `AI recruiting`
- `AI hiring`
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
- `agentic AI HR`
- `人力资源 AI`
- `招聘 AI`
- `猎头 AI`
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

Global AI speed brief:

- `artificial intelligence`
- `AI regulation`
- `AI model release`
- `AI safety`
- `generative AI enterprise`
- `OpenAI`
- `Google DeepMind`
- `Anthropic`
- `Microsoft AI`
- `NVIDIA AI`
- `人工智能`
- `大模型`
- `生成式AI`
- Domestic site-targeted searches for 36Kr, TMTPost, QbitAI, Machine Heart, ITHome, Leiphone, InfoQ China, and iFanr

## Acceptance Rules

Accept an item only when all are true:

1. The feed/search published date matches the target date in Asia/Shanghai.
2. The URL opens with HTTP 200 after redirects.
3. Extracted visible text is substantive enough to summarize.
4. The item is relevant to one of the two document modules.
5. The item is not a duplicate of a higher-quality source.

If a source has a date in another timezone, convert it to Asia/Shanghai for final matching. Reject the item when a structured source-page publish date clearly contradicts the target date. If the source page does not expose a structured publish date, use the same-day feed timestamp as the date gate and keep the missing page-date note only in `verification_report.json`; do not publish raw timestamps, source-only rows, checklists, or collection statistics into the reader-facing Feishu document.

## Ranking

Rank accepted items by:

1. Direct HR/recruiting/workforce relevance
2. Primary-source credibility
3. Business impact for HR, recruiters, and founders
4. Freshness within the target date
5. Specificity of evidence

Prefer fewer strong items over many weak ones.

## AI+HR Classification

Do not rely on the literal string `HR` alone. Treat an item as AI+HR when same-day content connects AI to at least one of these people/organization scenarios:

- recruiting, sourcing, interviewing, resume screening, ATS, candidate experience
- talent management, performance, learning and development, succession, workforce planning
- employee experience, onboarding, HR service delivery, HR shared services
- people analytics, HCM/HRIS, organization efficiency, digital employees, enterprise AI agents used by HR or managers

Vertical HR sources can provide additional confidence, but they do not override the date/link/content quality gate.
