# Step 1 - Understand Intent

## Functional Requirements

### FR-1: Run A JS Fallback Mini Crawler
Load site profiles and seed URLs, schedule crawl work through URLFrontier, fetch with FetchStrategy, extract links with HTMLParser, learn profile verification/render behavior, and write a JSON metrics report.

## Assumptions

- The crawler follows only HTTP(S) URLs whose domains appear in the seed file.
- Site profile learning is applied after the run so one render fallback does not force every later page in the same run to render.
- A successful rendered fetch changes default_fetch_mode to render; successful HTTP fetches preserve the configured mode.
- The crawler does not perform robots.txt checks because that was not included in the requested pipeline.
