This file documents per-token usage patterns specific to this kit.

If this file is empty or contains only this placeholder, treat the kit's
compiled stylesheet as the source of truth — see `/guidelines/setup.md`
Step 2 for how to enumerate the available CSS custom properties (e.g.
`--primary-button`, `--text-default`, `--spacer-md`). Always use
`var(--token-name)` over hardcoded color, spacing, or typography values
so the kit's theming continues to apply.

<!--
Tip for kit authors: replace this content with per-token guidance.

Token guidelines teach Make what tokens are available and how to use them correctly.

Create a file for each token type. In each file, cover:
* Naming pattern — How token names are structured so Make can find tokens independently
* Semantic purpose — What each token group means (success, neutral, etc.)
* Usage frequency — How often each value is used, so the agent knows which are defaults vs. edge cases
* Decision tree — A quick lookup the agent can follow to pick the right token
* Examples — Correct and incorrect usage, especially for common mistakes

For more tips, check our guide:
https://developers.figma.com/docs/code/write-design-system-guidelines
-->