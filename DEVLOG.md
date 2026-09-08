# Development Log - Session 2026-08-20

## 1. What Was Built Today (High-Level Summary)
Built a memory-efficient log parser (`data_pipeline/log_parser.py`) that reads massive web server log files in small chunks (10,000 lines at a time), parses each line using regex into structured fields, extracts behavioral features for ML training (request velocity, URL patterns, User-Agent anomalies), and outputs clean CSV data ready for XGBoost model training.

## 2. Significance & Engineering Purpose
This component sits at the start of the ML pipeline (Phase 1). Production API gateways generate gigabytes of logs daily—loading all into RAM crashes the process. Chunked streaming keeps memory usage constant (O(1) w.r.t. file size) regardless of log volume. The extracted features (IP velocity, bot-like UA, request patterns) are the exact signals the XGBoost model needs to distinguish benign users from scrapers/bots in Phase 3.

## 3. Core Code Concepts Explained Simply

**Key Functions/Methods:**
- `read_logs_chunked()` — Generator yielding DataFrames of 10k rows; uses Python iterator protocol to stream from disk
- `parse_log_line()` — Regex with named capture groups extracts 8 fields from combined log format
- `extract_features()` — Vectorized Pandas ops: `dt.hour`, `str.contains()`, `groupby().diff()` for per-IP velocity
- `clean_data()` — Drops duplicate rows, removes columns with ≤1 unique value, fills numeric NaNs with median

**Time & Space Complexity:**
- Time: O(N) single pass through file; feature extraction is vectorized (C-speed)
- Space: O(chunk_size) = O(1) w.r.t. total file size; only one chunk in memory at a time

**Why Not the Naive Way?**
`pd.read_csv(file)` loads entire file → RAM. A 10GB log file on an 8GB machine = OOM kill. Chunking processes 10k rows, releases memory, processes next 10k — constant footprint.

## 4. Viva / Interview Quick-Check

**Q:** How does `read_logs_chunked` avoid loading the full file into memory?  
**A:** It's a Python generator (`yield`) that reads line-by-line, accumulates 10k parsed dicts, yields a DataFrame, then clears the list — only one chunk exists in RAM at any moment.

**Q:** Why use `groupby('ip')['timestamp'].diff()` for request velocity?  
**A:** Computes time delta between consecutive requests per IP in vectorized C code; O(N) vs O(N²) loop. Identifies burst traffic (bot signature).

**Q:** What happens if a log line doesn't match the regex?  
**A:** `parse_log_line` returns `None`; the chunk builder skips it — malformed lines are silently dropped, keeping pipeline robust.

---

# Development Log - Session 2026-08-30

## 1. What Was Built Today (High-Level Summary)
Completed Phase 1 of Project Prahari by building a synthetic Apache access log generator (`data_pipeline/generate_sample_logs.py`), testing the multi-format log parser on 3 distinct log formats (Apache error, Linux syslog, and Apache access), and implementing the end-to-end XGBoost model training script (`data_pipeline/train_model.py`) that outputs production-ready model artifacts (`.json` and `.pkl`) along with runtime feature metadata.

## 2. Significance & Engineering Purpose
This milestone completes the data science foundation of Prahari. To protect live API endpoints against sophisticated scrapers and DDoS traffic in Phase 3, the gateway needs a trained binary classifier capable of distinguishing human browsing patterns from automated attack vectors based on behavioral features. By exporting both the serialized model and schema metadata (`feature_metadata.json`), the FastAPI gateway can load and execute zero-copy inferences in real time.

## 3. Core Code Concepts Explained Simply

**Key Functions/Methods:**
- `generate_apache_access_logs()` — Synthesizes realistic HTTP access traffic with randomized human inter-arrival pacing (1.5–25s) vs. bot burst intervals (0.01–0.45s).
- `load_and_prepare_data()` — Ingests clean CSV, resolves abuse labels via behavioral heuristics, and fills null values.
- `train_xgboost_model()` — Trains an `XGBClassifier` with class-weight rebalancing (`scale_pos_weight`) to handle real-world class imbalance between benign users and attack traffic.
- `evaluate_model()` — Computes Precision, Recall, F1-Score, ROC-AUC (1.0000 on test split), and ranks feature importances (`request_velocity` = 66.7%, `requests_per_ip` = 12.5%, `ua_length` = 12.2%).
- `export_artifacts()` — Exports native XGBoost JSON (`xgboost_abuse_model.json`), Joblib pickle (`xgboost_abuse_model.pkl`), feature metadata, and metrics.

**Time & Space Complexity:**
- **Training Time:** $O(M \cdot K \cdot d \cdot n_{\text{trees}})$ where $M$ is sample count (35,000), $K$ is feature count (11), and $d$ is max tree depth (5) — completes in sub-second CPU time.
- **Inference Time (Phase 3 Gateway):** $O(\text{depth} \cdot n_{\text{trees}})$ per request — executes in $<0.5\text{ ms}$, ensuring near-zero gateway latency overhead.

**Why Not the Naive Way?**
A naive approach would use hardcoded regex or static IP rules. However, attackers continuously rotate IPs and spoof User-Agents. Combining multiple behavioral signals (request velocity, volume density, URI depth) into a gradient-boosted decision tree allows the gateway to catch attackers even when they forge individual header fields.

## 4. Viva / Interview Quick-Check

**Q:** Why is `request_velocity` the top feature in the XGBoost model (~67% importance)?  
**A:** Automated bots and scrapers execute HTTP requests in rapid programmatic bursts (<500ms), creating an unambiguous mathematical separation from human click intervals.

**Q:** Why did we export both `.json` and `.pkl` formats for the trained model?  
**A:** Native JSON format is cross-platform, version-independent, and safe from pickle deserialization vulnerabilities; `.pkl` enables instant Python loading with scikit-learn compatibility.

**Q:** What is the purpose of `feature_metadata.json`?  
**A:** It records the exact list and order of feature columns expected by the model so the live FastAPI gateway in Phase 3 can construct identical feature vectors for incoming requests without schema drift.

---

# Development Log - Session 2026-09-08

## 1. What Was Built Today (High-Level Summary)
Implemented the core distributed gateway infrastructure for Phase 2:
1. Created an atomic Sliding Window Counter script in Lua (`scripts/rate_limit.lua`) running directly inside Redis via Sorted Sets (`ZSET`).
2. Built asynchronous Redis connection pooling and script SHA registration (`backend/redis_client/client.py`).
3. Implemented `RateLimitMiddleware` and dependency injection (`backend/middleware/rate_limiter.py`) providing standardized HTTP 429 JSON responses and rate-limit headers (`Retry-After`, `X-RateLimit-*`).
4. Created the FastAPI reverse proxy core (`backend/main.py`) with configurable environment settings (`backend/config.py`, `.env.example`) and API routes (`backend/routes/api.py`).
5. Created an automated test suite (`tests/test_rate_limiter.py`) with 10 passing tests verifying atomic window enforcement, quota resets, fail-open resilience, and client IP isolation.

## 2. Significance & Engineering Purpose
This milestone establishes the high-performance traffic control foundation of Project Prahari. In distributed architectures, naive rate limiting in Python process memory suffers from double-counting and race conditions under concurrent requests. By delegating sliding-window calculations to an atomic Lua script executed inside Redis via `EVALSHA`, we ensure:
- Zero race conditions across distributed gateway replicas.
- O(1) network overhead per check by caching script SHAs.
- Precise millisecond sliding-window granularity with exact `retry_after` calculation.
- Memory leak prevention via automatic `PEXPIRE` key lifecycle management.

## 3. Core Code Concepts Explained Simply

**Key Functions/Methods:**
- `scripts/rate_limit.lua` — Prunes timestamps older than `now - window` (`ZREMRANGEBYSCORE`), checks count (`ZCARD`), adds current timestamp (`ZADD`), and sets key TTL (`PEXPIRE`).
- `init_redis()` — Establishes `redis.asyncio.ConnectionPool` and pre-compiles the Lua script SHA using `register_script`.
- `RateLimitMiddleware.dispatch()` — Intercepts non-exempt HTTP requests, extracts client identity (supporting `X-Forwarded-For` and `X-API-Key`), invokes atomic Redis evaluation, and injects standard rate-limit headers.
- `get_client_identifier()` — Resolves unique client fingerprints prioritizing API keys, upstream load-balancer headers, and socket addresses.

**Time & Space Complexity:**
- **Time Complexity:** $O(\log N + M)$ where $N$ is total elements in the client's ZSET and $M$ is the number of expired items pruned. Since $N \le \text{limit}$ (e.g. 100), execution completes in $<1\text{ ms}$.
- **Space Complexity:** $O(\text{limit})$ memory per active client in Redis. Keys automatically expire after the window duration via `PEXPIRE`, yielding $O(1)$ idle state.

**Why Not the Naive Way?**
The naive way executes separate Redis commands (`ZREMRANGEBYSCORE`, then `ZCARD`, then `ZADD`). In a concurrent environment with multiple clients hitting the gateway at the same millisecond, two requests can both read `count = 99` and both succeed, leaking through a hard quota of 100 (TOCTOU: Time-of-Check to Time-of-Use race condition). An in-engine Lua script runs single-threaded and atomically inside Redis, preventing concurrency leaks entirely.

## 4. Viva / Interview Quick-Check

**Q:** Why use Redis Sorted Sets (`ZSET`) instead of simple Redis counters (`INCR`) for rate limiting?  
**A:** `INCR` only supports fixed-window counters, which suffer from the "boundary burst" problem (a client sends 100 requests at 00:59 and 100 requests at 01:00, achieving 200 requests within 2 seconds). `ZSET` stores request timestamps as scores, enabling a true rolling sliding window.

**Q:** What is the benefit of registering the Lua script (`register_script`) instead of sending the script text each time?  
**A:** It computes the SHA1 digest of the script once and executes via `EVALSHA`. This drastically minimizes network payload between FastAPI and Redis on every request.

**Q:** How does the gateway handle Redis outages or network partitions?  
**A:** The middleware implements a fail-open pattern with an `X-RateLimit-Error: Service Degraded` header, ensuring critical backend availability is maintained during temporary datastore hiccups.