---
paths:
  - "**/tests/**/*.py"
  - "**/*test*.py"
  - "frontend/**/*.{test,spec}.{js,jsx,ts,tsx}"
---
# Test rules

- Prefer the smallest test that proves changed behavior, then the owning lane when justified.
- Keep compatibility tests with the compatibility behavior they protect; do not delete a failing compatibility test without retiring the supported path.
- Do not hide collection/plugin failures or use broad exclusions to claim PASS.
- Test names should state the behavioral contract, not implementation trivia.
