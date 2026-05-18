# Feishu Setup

## Required Environment Variables

- `FEISHU_APP_ID`: Feishu/Lark internal app ID.
- `FEISHU_APP_SECRET`: Feishu/Lark internal app secret.
- `FEISHU_DOCUMENT_ID`: Existing Feishu Docx document ID, Docx URL, or Wiki URL where daily sections should be prepended. Bare tokens are treated as Docx IDs; use the full `/wiki/...` URL for Wiki documents.

Recommended for personal cloud documents:

- `FEISHU_REFRESH_TOKEN`: OAuth refresh token for the document owner. When present, the workflow writes with a user access token instead of the app/tenant token.
- `GH_SECRET_PAT`: GitHub token with permission to update repository Actions secrets. Required for fully automatic daily runs because Feishu returns a new refresh token after refresh.

Optional:

- `FEISHU_BASE_URL`: Defaults to `https://open.feishu.cn`.
- `FEISHU_ROOT_BLOCK_ID`: Optional root block ID. Defaults to `FEISHU_DOCUMENT_ID`, which is the usual root block for Docx documents.
- `FEISHU_USER_ACCESS_TOKEN`: Short-lived user access token for one-off testing. Do not use this for the scheduled workflow because it expires.
- `FEISHU_TOKEN_OUTPUT_PATH`: Path where the script writes the rotated refresh token. The GitHub workflow sets this automatically.

## Document Setup

Create one Feishu document manually, for example `AIHR 嘉尔日报`. Copy either the Docx URL/token or the full Wiki URL.

If manually created documents return `forbidden`, create the fixed document with the app itself:

1. Save a folder URL or token as GitHub secret `FEISHU_FOLDER_TOKEN`.
2. Run the `Create Feishu Doc` workflow.
3. Copy the printed `FEISHU_DOCUMENT_ID` into the `FEISHU_DOCUMENT_ID` secret.
4. Run the daily workflow.

Docx URL:

```text
https://xxx.feishu.cn/docx/doxcnxxxxxxxx
```

Wiki URL:

```text
https://xxx.feishu.cn/wiki/FfDlwTA3Ji3DU3kaxLJcV3D7nIf
```

The script resolves Wiki tokens to the underlying Docx `obj_token` through the Wiki API before writing.

## Personal OAuth Setup

Use this path when Feishu returns `1770032 forbidden` while inserting document blocks, or `1770040 no folder permission` while creating a document. Those errors mean the app identity cannot edit the personal cloud document/folder. OAuth lets the workflow write as the document owner.

1. In the Feishu developer console, add user-identity permissions for Docx document read/write, especially `docx:document` or `docx:document:write_only`, then publish the app version.
2. Add a redirect URL for the app. For a manual setup, a placeholder you control is enough, for example `https://example.com/feishu-oauth-callback`.
3. Set local environment variables `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, and `FEISHU_REDIRECT_URI`.
4. Run `python3 scripts/feishu_oauth.py auth-url`, open the printed URL, approve access, and copy the redirected URL. The helper requests `docx:document docx:document:write_only` by default.
5. Run `python3 scripts/feishu_oauth.py exchange-code --code 'PASTE_REDIRECTED_URL_HERE'`.
6. Save the printed value as GitHub Actions secret `FEISHU_REFRESH_TOKEN`.
7. Add GitHub Actions secret `GH_SECRET_PAT`, using a GitHub token that can update repository Actions secrets.

After this, `.github/workflows/daily-ai-hr-brief.yml` refreshes the Feishu user token, writes the daily section, then rotates `FEISHU_REFRESH_TOKEN` in GitHub Secrets.

## API Flow

With app/tenant token only, the script uses:

1. `POST /open-apis/auth/v3/tenant_access_token/internal` to get `tenant_access_token`.
2. If `FEISHU_DOCUMENT_ID` is a Wiki token or URL, `GET /open-apis/wiki/v2/spaces/get_node?token=...` to resolve the underlying Docx `obj_token`.
3. `POST /open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children` to insert Markdown-like text blocks at index `0`.

With personal OAuth, the script uses:

1. `POST /open-apis/auth/v3/app_access_token/internal` to get an app token for OAuth refresh.
2. `POST /open-apis/authen/v1/refresh_access_token` to exchange `FEISHU_REFRESH_TOKEN` for a user access token and a rotated refresh token.
3. `POST /open-apis/docx/v1/documents/{document_id}/blocks/{block_id}/children` with the user access token.

Feishu permissions vary by tenant. If publishing fails while resolving a Wiki URL, confirm that the app has Wiki read scope, such as `wiki:wiki:readonly`, and that the app or bot has read access to the target Wiki space/page. If publishing fails while inserting blocks, confirm that the app has Docx read/write scopes and permission to edit the target document.

## Operational Notes

Use GitHub repository secrets for credentials. Never commit app secrets, tenant tokens, or generated logs containing credentials.

If the publish step fails, keep the generated Markdown and verification report as artifacts so the brief can still be reviewed manually.
