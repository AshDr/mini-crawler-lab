# Step 1 - Understand Intent

## Functional Requirements

### FR-1: Select And Normalize Fetching
Fetch a URL through HTTP first, use SiteProfile and RenderDecisionEngine to decide whether browser rendering is needed, and return a unified FetchResult that records the actual fetch mode.

## Assumptions

- render_policy never takes precedence over other render signals.
- render_policy always, default_fetch_mode render, and matching js_required_patterns force rendering after the initial HTTP attempt.
- default_fetch_mode api remains on the HTTP result because API discovery is outside FetchStrategy's requested HTTP/render scope.
- parse_embedded_json and uncertain decisions do not trigger rendering.
