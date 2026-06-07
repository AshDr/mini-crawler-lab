# Scenario: Run A JS Fallback Mini Crawler
- Given: A site profile YAML file, a seed URL file, and an injectable fetch strategy
- When: The crawler runs with a bounded page limit
- Then: It schedules URLs through SQLiteUrlFrontier, extracts same-site links, updates profiles, and writes a metrics report

## Test Steps

- Case 1 (full flow): Crawl rendered and HTTP pages, enqueue normalized links, update the rendered domain profile, and persist metrics
- Case 2 (input validation): Reject an empty seed file before creating crawl output
- Case 3 (CLI output): Run the CLI with an injected crawler and emit JSON to stdout

## Status
- [x] Write scenario document
- [x] Write solid test according to document
- [x] Run test and watch it failing
- [x] Implement to make test pass
- [x] Run test and confirm it passed
- [x] Refactor implementation without breaking test
- [x] Run test and confirm still passing after refactor
