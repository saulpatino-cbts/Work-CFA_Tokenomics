# Guided onboarding

**Status:** proposed experience and acceptance criteria. No wizard is implemented yet.

## Experience principles

Use concise task-oriented language. Explain what a permission enables and why it is needed. Show secrets only when newly issued, where applicable; stored values must not be retrievable through support views. Make steps resumable without duplicate provisioning and distinguish required, optional, skipped, pending, warning, and failed checks.

## Proposed setup flow

| Step | UI language | Verified outcome |
| --- | --- | --- |
| Environment | Check this environment | Runtime, storage, network, and required permissions are ready. |
| Identity | Connect your sign-in provider | A real OIDC login succeeds with the configured issuer/client. |
| Roles | Choose who can administer, use, and read | Claims/groups map correctly; reader write attempts are denied. |
| Provider | Connect an AI provider | Correct endpoint, customer scope, credential method, and supported model/API. |
| Collection | Choose what usage to collect | Clearly selected observation mode and resource scope. |
| Verification | Verify this connection | Separate network, identity, model, telemetry, and optional billing results. |
| Data | Start empty or import data | Validated dry-run and preview before committing an archive. |
| Activation | Review and activate | Required checks pass; customer sees data controls and vendor access disabled. |

Allow one provider to be configured without accounts on the other two. Mark missing integrations as not configured, not failed. Credential validity alone must not produce a green usage-collection status.

## Proposed language examples

- **Connected to Bedrock. Usage metrics are unavailable.** Ask your AWS administrator to grant the listed monitoring permissions, then select **Check again**.
- **This test sends a request to your selected model and may consume tokens.** Select **Run model test** to continue.
- **Import validated. No changes applied.** Review the summary before selecting **Apply import**.
- **Vendor access is off.** An administrator can authorize a scoped Assessment when needed.

These are target copy examples, not messages from a working application.

## Accessibility and recovery

Provide keyboard navigation, visible focus, labeled fields, screen-reader-friendly status changes, readable contrast, and error text that does not rely on color alone. Preserve valid nonsecret progress after refresh. Do not retain pasted secrets in browser storage or analytics.

Each failed check should state what failed, whether configuration was saved, how to fix it, and how to retry. Help links must not embed account identifiers or credentials. Connection errors must redact provider payloads that could contain secrets.

## Post-setup health

Expose credential expiry/rotation needs, last sync, partial coverage, failed permissions, collection backlog, and installed version. Rechecking a connection must be safe; any charge-bearing test requires an explicit action. Setup completion is evidence only for checks actually executed.
