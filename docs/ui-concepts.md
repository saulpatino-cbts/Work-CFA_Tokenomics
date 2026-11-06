# UI concepts

**Status:** concept drawings, not an implemented UI. **[REVIEW REQUIRED]** Brand approval is pending. All values are synthetic and no provider was contacted.

Files: [`design/concepts/`](../design/concepts/) holds static HTML (`dashboard.html`, `setup.html`), shared tokens (`tokens.css`) and rendered images (`images/`). Re-render with Playwright at 1440×1024.

## Source and rules applied

Built from the CBTS Brand Guidelines v1.10 (colour pp. 24-30, typography pp. 34-36, design system pp. 52-61); other sections were not read. Applied: the primary palette as transcribed in `tokens.css`; the secondary palette only inside the chart; rounded corners on every visible edge (14px, 1.5% of the shortest side); 38px margins (3.7%); dark teal/dark blue title blocks and light supporting blocks; hex-dot background on Light Gray; no gradient fills; Bright Teal only as a highlight; flush-left text.

Product rules applied: provider and app figures are never added; the app figure is shown inside the provider figure; unknown is "unknown", never zero; the unattributed gap is counted only for fully reconciled models; every total sits next to its freshness; status never relies on colour alone.

## Placeholders and open questions

- **Logo:** placeholder only; the real logo asset has not been supplied or read from the guide.
- **Typeface:** Aeonik and Eurocat are licensed and not bundled. Images render with Inter as a stand-in. Licence and redistribution rights are unconfirmed (brand to confirm).
- **Product name:** "CFA Tokenomics" is the repository's working name, not an approved product name.
- **Hex-dot colour:** the guide says Dark Gray in text and Gray in a callout; the concepts use Gray.
- **Not drawn:** role and account management, Assessment, export/import, error states, mobile.
- **Figma:** not used; the connector was not enabled in this session.
