# Feishu Setup

## Required Environment Variables

- `FEISHU_APP_ID`: Feishu/Lark internal app ID.
- `FEISHU_APP_SECRET`: Feishu/Lark internal app secret.
- `FEISHU_DOCUMENT_ID`: Existing Feishu Docx document ID where daily sections should be prepended.

Optional:

- `FEISHU_BASE_URL`: Defaults to `https://open.feishu.cn`.
- `FEISHU_ROOT_BLOCK_ID`: Optional root block ID. Defaults to `FEISHU_DOCUMENT_ID`, which is the usual root block for Docx documents.

## Document Setup

Create one Feishu document manually, for example `AIHR 嘉尔日报`. Copy the document ID from the URL:

```text
https://xxx.feishu.cn/docx/doxcnxxxxxxxx
```

Use the `doxcnxxxxxxxx` part as `FEISHU_DOCUMENT_ID`.

## API Flow

The script uses:

1. `POST /open-apis/auth/v3/tenant_access_token/internal` to get `tenant_access_token`.
2. `POST /open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children` to insert Markdown-like text blocks at index `0`.

Feishu permissions vary by tenant. If publishing fails with `forbidden`, confirm that the app has Docx read/write scopes and permission to edit the target document.

## Operational Notes

Use GitHub repository secrets for credentials. Never commit app secrets, tenant tokens, or generated logs containing credentials.

If the publish step fails, keep the generated Markdown and verification report as artifacts so the brief can still be reviewed manually.
