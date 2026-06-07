# Step 1 - Understand Intent

## Functional Requirements

### FR-1: Show Crawler Progress
Display useful page-level crawl progress in interactive terminals while preserving stdout as machine-readable JSON and allowing progress to be disabled.

## Assumptions

- Progress is written to stderr.
- Interactive terminals receive an in-place progress bar; redirected stderr receives no animated output.
- The progress total is max_pages, even when the frontier may drain before reaching that limit.
