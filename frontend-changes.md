# Frontend Changes

No frontend changes were made. This feature enhancement targeted the backend testing infrastructure only.

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
