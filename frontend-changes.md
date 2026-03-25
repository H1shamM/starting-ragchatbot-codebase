# Frontend Changes — Dark/Light Theme Toggle

## Summary

Added a dark/light theme toggle button to the UI, allowing users to switch between the existing dark theme and a new light theme.

---

## Files Modified

### `frontend/style.css`

1. **Light theme CSS variables** — Added a `[data-theme="light"]` block after `:root` with a full set of overrides:
   - Background: `#f8fafc` (near-white)
   - Surface: `#ffffff`
   - Surface hover: `#f1f5f9`
   - Text primary: `#0f172a` (near-black for high contrast)
   - Text secondary: `#64748b`
   - Border color: `#e2e8f0`
   - Assistant message bg: `#f1f5f9`
   - Shadow: lighter `rgba(0,0,0,0.1)` drop shadow
   - Welcome background: `#dbeafe`
   - Primary/accent colors unchanged (`#2563eb`)

2. **Body transition** — Added `transition: background-color 0.3s ease, color 0.3s ease` to `body` so theme switches animate smoothly.

3. **`.theme-toggle` button styles** — New styles for a fixed, circular button positioned at `top: 1rem; right: 1rem`:
   - 40x40px circle with border and surface background
   - Hover: scales up 10%, highlights with primary color border
   - Focus ring using `--focus-ring` variable for accessibility
   - Active state: slight scale-down press effect
   - Sun/moon SVG icons absolutely positioned within the button, animated with opacity and rotation transitions
   - In dark mode (default): sun icon visible, moon icon hidden
   - In light mode (`[data-theme="light"]`): moon icon visible, sun icon hidden

### `frontend/index.html`

- Added a `<button class="theme-toggle" id="themeToggle">` element just before the closing `</body>` tag
- Contains two inline SVGs:
  - `.icon-sun` — rays + circle sun, shown in dark mode (click to switch to light)
  - `.icon-moon` — crescent moon path, shown in light mode (click to switch to dark)
- `aria-label="Toggle theme"` and `title` attribute for accessibility and tooltip

### `frontend/script.js`

1. **`initTheme()`** — Reads `localStorage.getItem('theme')`; if `'light'`, sets `data-theme="light"` on `<html>` so the chosen theme persists across page reloads.

2. **`toggleTheme()`** — Checks current `data-theme` on `<html>`:
   - If light: removes attribute (reverts to default dark), saves `'dark'` to `localStorage`
   - If dark: sets `data-theme="light"`, saves `'light'` to `localStorage`

3. **`setupEventListeners()`** — Wires `themeToggle.addEventListener('click', toggleTheme)`.

4. **`DOMContentLoaded`** handler — Grabs `themeToggle` element and calls `initTheme()` before session setup.

---

# Backend Testing Infrastructure Changes

No frontend changes were made for the testing feature. This enhancement targeted the backend testing infrastructure only.

## What Was Added

### `backend/tests/conftest.py` (updated)
- Added shared test data constants: `SAMPLE_ANSWER`, `SAMPLE_SOURCES`, `SAMPLE_SESSION_ID`, `SAMPLE_COURSES`
- Added `mock_rag` fixture — a fully mocked `RAGSystem` with pre-configured return values
- Added `make_test_app(rag_system)` helper — builds a minimal FastAPI app with the same `/api/query`, `/api/courses`, and `/api/session/{id}` endpoints but **without** the static file mount, avoiding file-system dependency on `../frontend/`
- Added `test_app` and `client` fixtures that compose `make_test_app` + `starlette.testclient.TestClient`

### `backend/tests/test_api_endpoints.py` (new file)
16 tests across three classes:
- `TestQueryEndpoint` — `POST /api/query`: status codes, response shape, session creation vs reuse, RAG delegation, 500 on error, 422 on missing field
- `TestCoursesEndpoint` — `GET /api/courses`: status code, response shape, mocked data, 500 on error
- `TestSessionEndpoint` — `DELETE /api/session/{id}`: status code, response body, correct ID forwarded to `session_manager.clear_session`

### `pyproject.toml` (updated)
- Added `httpx>=0.27.0` to `[dependency-groups] dev` (required by `starlette.testclient.TestClient`)
- Added `[tool.pytest.ini_options]` section:
  - `testpaths = ["backend/tests"]` — pytest discovers tests without specifying the path manually
  - `pythonpath = ["backend"]` — backend modules importable without `sys.path` hacks in each test file
  - `addopts = "-v"` — verbose output by default
