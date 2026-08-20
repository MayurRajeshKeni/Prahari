# Rules & AI Boundaries

## 1. General Guidelines
*   **Code Portability:** All code must be modular. Hardcoded paths should be avoided; use environment variables (`.env`) for Redis URIs and ports.
*   **Asynchronous Paradigm:** Utilize `async`/`await` strictly in FastAPI route handlers and Redis calls (`redis.asyncio`).

## 2. Libraries & Tools
*   **Allowed:** `fastapi`, `uvicorn`, `redis`, `pandas`, `xgboost`, `scikit-learn`, `python-dotenv`.
*   **Avoid:** Heavy ORMs (SQLAlchemy, Prisma) since we are not using a relational database for this gateway. Avoid `matplotlib` or heavy plotting libraries in the backend environment.

## 3. Concurrency & Performance Rules
*   **Zero Python State:** Do not use Python dictionaries to store rate-limit counters. All state must live in Redis to ensure it is distributed.
*   **Lua Atomicity:** The read-evaluate-increment logic for the rate limiter MUST be written in Lua (`scripts/rate_limit.lua`). Do not perform these steps sequentially in Python.
*   **Time Complexity:** Ensure the Lua script and Pandas processing steps are optimized for time and space complexity (e.g., using `chunksize` in Pandas, optimal Redis data structures like Sorted Sets).

## 4. Error Handling
*   Standardize all gateway rejections to return structured JSON:
    ```json
    { "error": "Rate limit exceeded", "retry_after": 30 }
    ```
*   Use specific HTTP status codes: `429` (Rate Limit Exceeded), `403` (Forbidden/Bot Detected).

## 5. AI Instructions (Antigravity Constraints)
*   **Do not hallucinate performance metrics.** Leave placeholders in the benchmarking output until `k6` is actually run.
*   **Read `Memory.md` before writing new code.** Always check the current project phase before suggesting new features.
*   **Stay in Scope:** Do not build a user login system or database models. Focus purely on the gateway logic.