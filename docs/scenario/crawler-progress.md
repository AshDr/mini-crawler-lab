# Scenario: Show Crawler Progress
- Given: A bounded crawler running in an interactive terminal
- When: Pages are processed
- Then: A progress bar is refreshed on stderr without corrupting the JSON report on stdout

## Test Steps

- Case 1 (TTY progress): Render page counts, success/failure counts, fetch modes, queue growth, timing, and the current URL
- Case 2 (crawler callback): Emit one progress event after every attempted page
- Case 3 (quiet mode): Disable progress reporting through the CLI

## Status
- [x] Write scenario document
- [x] Write solid test according to document
- [x] Run test and watch it failing
- [x] Implement to make test pass
- [x] Run test and confirm it passed
- [x] Refactor implementation without breaking test
- [x] Run test and confirm still passing after refactor
