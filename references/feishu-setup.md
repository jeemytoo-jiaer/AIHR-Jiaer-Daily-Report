# Feishu Setup

## Required Environment Variables

- `FEISHU_APP_ID`: Feishu/Lark internal app ID.
- `FEISHU_APP_SECRET`: Feishu/Lark internal app secret.
- `FEISHU_DOCUMENT_ID`: Existing Feishu Docx document ID, Docx URL, Wiki node token, or Wiki URL where daily sections should be prepended.

Optional:

- `FEISHU_BASE_URL`: Defaults to `https://open.feishu.cn`.
- `FEISHU_ROOT_BLOCK_ID`: Optional root block ID. Defaults to `FEISHU_DOCUMENT_ID`, which is the usual root block for Docx documents.

## Document Setup

Create one Feishu document manually, for example `AIHR 嘉尔日报`. Copy either the Docx URL/token or the Wiki URL/token.

Docx URL:

```text
https://xxx.feishu.cn/docx/doxcnxxxxxxxx
```

Wiki URL:

```text
https://xxx.feishu.cn/wiki/FfDlwTA3Ji3DU3kaxLJcV3D7nIf
```

The script resolves Wiki tokens to the underlying Docx `obj_token` through the Wiki API before writing.

## API Flow

The script uses:

1. `POST /open-apis/auth/v3/tenant_access_token/internal` to get `tenant_access_token`.
2. If `FEISHU_DOCUMENT_ID` is a Wiki token or URL, `GET /open-apis/wiki/v2/spaces/get_node?token=...` to resolve the underlying Docx `obj_token`.
3. `POST /open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children` to insert Markdown-like text blocks at index `0`.

Feishu permissions vary by tenant. If publishing fails while resolving a Wiki URL, confirm that the app has Wiki read scope, such as `wiki:wiki:readonly`, and that the app or bot has read access to the target Wiki space/page. If publishing fails while inserting blocks, confirm that the app has Docx read/write scopes and permission to edit the target document.

## Operational Notes

Use GitHub repository secrets for credentials. Never commit app secrets, tenant tokens, or generated logs containing credentials.

If the publish step fails, keep the generated Markdown and verification report as artifacts so the brief can still be reviewed manually.
