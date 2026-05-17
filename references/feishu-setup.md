# Feishu Setup

## Required Environment Variables

- `FEISHU_APP_ID`: Feishu/Lark internal app ID.
- `FEISHU_APP_SECRET`: Feishu/Lark internal app secret.
- `FEISHU_FOLDER_TOKEN`: Cloud Drive folder token where daily docs should be created.

Optional:

- `FEISHU_BASE_URL`: Defaults to `https://open.feishu.cn`.
- `FEISHU_OPEN_ID`: Optional owner/open id if your tenant permission model requires it.

## API Flow

The script uses:

1. `POST /open-apis/auth/v3/tenant_access_token/internal` to get `tenant_access_token`.
2. `POST /open-apis/docx/v1/documents` to create a document titled `YYYY.MM.DD` in the configured folder.
3. `POST /open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children` to append Markdown-like text blocks when the Docx block API is available.

Feishu permissions vary by tenant. If publishing fails with `forbidden`, confirm that the app has document creation/edit scopes and permission to the target folder.

## Operational Notes

Use GitHub repository secrets for credentials. Never commit app secrets, tenant tokens, or generated logs containing credentials.

If the publish step fails, keep the generated Markdown and verification report as artifacts so the brief can still be reviewed manually.
