# Project Phases & Roadmap

## Phase 1: Data Engineering & ML Pipeline
**Goal:** Process raw server logs and train the abuse detection model.
*   [x] Set up Pandas script to read raw web logs using chunking to prevent memory bloat.
*   [x] Clean data (handle missing values, drop low-variance columns).
*   [x] Extract high-variance features (e.g., request velocity, URL path patterns, User-Agent anomalies).
*   [x] **Extended parser to support Apache access, Apache error, and Linux syslog formats**
*   [ ] Train an XGBoost baseline model on the processed dataset.
*   [ ] Export the trained model as a `.json` or `.pkl` artifact.

## Phase 2: Gateway Core & Distributed Concurrency
**Goal:** Build the FastAPI reverse proxy and atomic rate limiter.
*   [ ] Initialize FastAPI app with a catch-all route or specific dummy endpoints.
*   [ ] Set up local Redis instance via Docker.
*   [ ] Write the `rate_limit.lua` script implementing the Sliding Window Counter using Redis Sorted Sets.
*   [ ] Integrate the Lua script execution into the FastAPI middleware/dependency injection.

## Phase 3: ML Integration & Dynamic Mitigation
**Goal:** Connect the ML model to the live traffic stream.
*   [ ] Load the XGBoost artifact into the FastAPI application state on startup.
*   [ ] Asynchronously pass request metadata to the model during the request lifecycle.
*   [ ] Implement logic to dynamically add flagged IPs to a Redis block-list.

## Phase 4: UI Dashboard & Load Benchmarking
**Goal:** Visualize the system and prove it works under stress.
*   [ ] Build a minimal React frontend to poll the backend for traffic stats (Allowed vs. Blocked requests).
*   [ ] Write a `k6` script (`load_test.js`) to simulate 10,000+ concurrent requests.
*   [ ] Execute benchmark and verify zero race-condition leakage.