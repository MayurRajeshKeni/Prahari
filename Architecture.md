# Architecture & System Flow

## 1. Tech Stack
*   **Backend Framework:** FastAPI (Python) - *Chosen for native async support and ML ecosystem compatibility.*
*   **Datastore:** Redis - *Used for distributed state and TTL management.*
*   **Concurrency Logic:** Lua Scripting - *Executes atomic read-and-increment operations inside Redis.*
*   **Data Science:** Pandas, Scikit-learn, XGBoost.
*   **Load Testing:** k6 (Go-based).
*   **Dashboard:** React (Vanilla JS/CSS) - *Leveraging standard web programming patterns.*

## 2. System Flow
1.  **Request Ingestion:** Client sends HTTP request to FastAPI Gateway.
2.  **State Check (Redis):** FastAPI forwards the client IP/Token to Redis. A Lua script executes the Sliding Window algorithm.
3.  **Evaluation:**
    *   *If Quota Exceeded:* Return `HTTP 429 Too Many Requests`.
    *   *If Quota Valid:* Proceed to ML Evaluation.
4.  **ML Classification (Async):** Request metadata (velocity, User-Agent, endpoint) is passed to the XGBoost model.
    *   *If Bot:* Redis dynamically updates the IP's block-list status.
5.  **Response:** The gateway proxies the request to the dummy upstream service and returns `HTTP 200`.

## 3. Directory Structure
```text
project-prahari/
├── backend/
│   ├── main.py                 # FastAPI application entry point
│   ├── routes/                 # API endpoint definitions
│   ├── redis_client/           # Redis connection and Lua script loading
│   └── ml_integration/         # XGBoost model inference wrapper
├── data_pipeline/
│   ├── log_parser.py           # Pandas chunking and feature extraction
│   ├── train_model.py          # XGBoost training script
│   └── data/                   # (Ignored) Raw and processed CSV files
├── scripts/
│   ├── rate_limit.lua          # Core Sliding Window Lua script
│   └── load_test.js            # k6 benchmarking script
├── dashboard/                  # Lightweight React UI for traffic monitoring
│   └── src/
└── Memory.md                   # AI State Tracking