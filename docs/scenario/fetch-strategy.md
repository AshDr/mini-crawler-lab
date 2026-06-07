# Scenario: Select HTTP Or Render Fetching
- Given: A URL, optional site profile, and injectable HTTP/render fetchers
- When: FetchStrategy fetches the URL
- Then: It tries HTTP first, renders only when policy or quality requires it, and returns a FetchResult with the actual fetch mode

## Test Steps

- Case 1 (HTTP path): Rich static HTML is returned directly with fetch_mode set to http
- Case 2 (quality fallback): An app shell triggers rendering and returns rendered HTML with fetch_mode set to render
- Case 3 (profile selection): Site profile policy and URL patterns can force or prevent rendering
- Case 4 (render failure): A failed render is normalized into FetchResult

## Status
- [x] Write scenario document
- [x] Write solid test according to document
- [x] Run test and watch it failing
- [x] Implement to make test pass
- [x] Run test and confirm it passed
- [x] Refactor implementation without breaking test
- [x] Run test and confirm still passing after refactor
