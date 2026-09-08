# Project Prahari
### *Distributed Rate Limiter & Machine Learning Abuse Gateway*

---

## 1. Overview & Objective

**Project Prahari** is an intelligent, high-throughput, distributed API gateway and security proxy designed to protect backend systems, databases, and microservices from **volumetric DDoS attacks, malicious web scrapers, and quota abuse**.

Traditional API gateways rely strictly on static threshold counters (e.g., *maximum 100 requests per minute*). While effective against primitive floods, static limiters fail against distributed botnets and scrapers that intentionally throttle their velocity just below fixed thresholds. 

Prahari solves this by pairing **atomic, distributed sliding-window rate limiting** with **real-time, asynchronous Machine Learning (XGBoost) traffic classification** to dynamically identify, throttle, and blacklist abusive actors based on behavioural heuristics.

---

## 2. Core Problem & Engineering Solutions

| Challenge | Traditional Approach Flaw | Prahari Architecture Solution |
| :--- | :--- | :--- |
| **Concurrency & Race Conditions** | Multi-step read-modify-write calls to databases or caches cause quota leakage under high concurrency. | **Redis + Lua Scripting**: Atomic execution directly inside Redis memory via a Sliding Window Counter algorithm using Sorted Sets (`ZSET`). |
| **Sub-Threshold Bot Traffic** | Smart bots rotate IPs or stay slightly below static rate limits while scraping data. | **Async ML Traffic Classification**: Asynchronously extracts behavioral signals (inter-arrival velocity, User-Agent heuristics, URL traversal depth) and scores traffic using XGBoost. |
| **Large-Scale Log Ingestion** | Loading multi-gigabyte server log files directly into RAM crashes the process with Out-Of-Memory (OOM) errors. | **Chunked Streaming Pipeline**: A Python generator pipeline in `data_pipeline/log_parser.py` that processes logs in 10,000-line batches, maintaining a constant **$O(1)$ memory footprint**. |

---

## 3. End-to-End System Architecture

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 Incoming HTTP Request                  │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │   FastAPI Gateway       │
                                 └────────────┬────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │   Redis + Lua Script    │
                                 │  (Sliding Window Check) │
                                 └────────────┬────────────┘
                                              │
                     ┌────────────────────────┴────────────────────────┐
                     │                                                 │
          [Quota Exceeded / Blocked]                             [Quota Valid]
                     │                                                 │
                     ▼                                                 ▼
        ┌─────────────────────────┐                       ┌─────────────────────────┐
        │ HTTP 429 Too Many Req   │                       │ Async ML Classification │
        │ or HTTP 403 Forbidden   │                       │ (XGBoost Abuse Check)   │
        └─────────────────────────┘                       └────────────┬────────────┘
                                                                       │
                                              ┌────────────────────────┴────────────────────────┐
                                              │                                                 │
                                         [Bot Detected]                                     [Benign]
                                              │                                                 │
                                              ▼                                                 ▼
                                ┌───────────────────────────┐                     ┌───────────────────────────┐
                                │ Add IP to Redis Blocklist │                     │ Proxy to Upstream Service │
                                │ & Throttle Quotas         │                     │ Return HTTP 200 OK        │
                                └───────────────────────────┘                     └───────────────────────────┘
```

### Request Lifecycle Breakdown
1. **Request Ingestion:** The client sends an HTTP request to the FastAPI gateway.
2. **Atomic Rate Limit Check:** FastAPI invokes a Redis Lua script passing the client's IP or API token. The script evaluates the sliding time window atomically.
3. **Early Gate Evaluation:** If the client has exceeded their allowed quota or exists on the dynamic blocklist, an immediate `HTTP 429 Too Many Requests` or `HTTP 403 Forbidden` is returned.
4. **Asynchronous ML Inspection:** Requests within quota proceed to upstream processing while their metadata (burst velocity, request rate, User-Agent anomaly score, URL path structure) is asynchronously fed to the XGBoost inference engine.
5. **Dynamic Mitigation:** If the model flags the request as malicious/bot traffic, the client IP is dynamically written into the Redis blacklist with a timed expiration (TTL).
6. **Response Proxy:** Legitimate requests are forwarded to the target backend service and returned with `HTTP 200 OK`.

---

## 4. Key Engineering Modules

### 4.1. Atomic Sliding Window Counter (Redis + Lua)
To prevent race conditions where concurrent requests slip through between reading and updating a counter, rate-limiting logic is executed entirely inside Redis via Lua scripts:
* Utilizes Redis **Sorted Sets (`ZSET`)** with timestamps as scores.
* Removes outdated timestamps older than the sliding window (`ZREMRANGEBYSCORE`).
* Counts surviving elements (`ZCARD`).
* If within quota, appends current timestamp (`ZADD`) and resets the key's TTL (`EXPIRE`).
* Guaranteed atomic execution: No two requests can interleave during evaluation.

### 4.2. Memory-Optimized Data Pipeline (`data_pipeline/`)
Training the abuse classification model requires parsing massive web server log files. The pipeline is built with strict memory efficiency:
* **Multi-Format Support:** Ingests Apache Access logs (Combined format), Apache Error logs, and Linux system logs (`syslog`).
* **Streaming Generator:** Implements `read_logs_chunked()` using Python generators to read 10,000 lines per batch, keeping RAM consumption constant regardless of file size ($O(1)$ space complexity).
* **Data Sanitization:** Automatically removes duplicate records, eliminates zero-variance columns, and imputes missing numeric values with medians.

### 4.3. Behavioral Feature Engineering
The data pipeline extracts high-signal features that distinguish automated abuse from human navigation:

| Feature Name | Computation Logic | Security / Abuse Signal |
| :--- | :--- | :--- |
| `request_velocity` | `groupby('ip')['timestamp'].diff()` | Measures time delta between successive requests. Sub-millisecond intervals indicate automated scripts. |
| `requests_per_ip` | `groupby('ip')['ip'].transform('count')` | Aggregates volume density per IP address within the observation period. |
| `is_bot_ua` | Regex match (`bot\|crawler\|spider\|scraper\|python\|curl\|wget`) | Identifies non-browser HTTP clients and known scrapers. |
| `is_mobile_ua` | Regex match (`mobile\|android\|iphone`) | Differentiates mobile browser clients from server scripts. |
| `url_depth` | Slash count in `url_path` | Measures directory traversal and API endpoint depth. |
| `has_query` | Query parameter detection (`?`) | Detects parameter fuzzing and dynamic search queries. |
| `is_static` | File extension match (`.css`, `.js`, `.png`, etc.) | Distinguishes static asset fetching from heavy dynamic endpoint abuse. |

---

## 5. Technology Stack

* **API Gateway & Routing:** [FastAPI](https://fastapi.tiangolo.com/) (Python) — High-throughput asynchronous ASGI web framework.
* **Distributed State & TTL Store:** [Redis](https://redis.io/) — In-memory caching, TTL expiration, and Sorted Sets.
* **Atomic Concurrency Engine:** [Lua](https://www.lua.org/) — Server-side script execution in Redis to eliminate race conditions.
* **Machine Learning & Data Processing:** [Pandas](https://pandas.pydata.org/), [Scikit-learn](https://scikit-learn.org/), [XGBoost](https://xgboost.readthedocs.io/) — Feature engineering, data sanitization, and tabular classification.
* **Load Testing & Benchmarking:** [k6](https://k6.io/) — Simulates 10,000+ concurrent connections to validate rate limiters under extreme load.
* **Traffic Monitoring Dashboard:** [React](https://react.dev/) — Cyber-security command center UI for visualizing allowed, throttled, and blocked traffic in real time.

---

## 6. Directory Structure

```text
Prahari/
├── backend/
│   ├── main.py                 # FastAPI gateway entry point
│   ├── routes/                 # Endpoint proxying and route handlers
│   ├── redis_client/           # Redis connection pooling & Lua script loader
│   └── ml_integration/         # XGBoost model inference wrapper
├── data_pipeline/
│   ├── log_parser.py           # Multi-format chunked log parser & feature extractor
│   ├── train_model.py          # XGBoost model training and evaluation script
│   └── data/                   # Raw and processed CSV data files
├── scripts/
│   ├── rate_limit.lua          # Atomic Sliding Window Lua script for Redis
│   └── load_test.js            # k6 high-concurrency benchmark script
├── dashboard/                  # React dashboard for real-time monitoring
│   └── src/
├── Architecture.md             # Detailed system flow specifications
├── Design.md                   # UI / Dashboard theme and aesthetic guidelines
├── DEVLOG.md                   # Chronological engineering log
└── requirements.txt            # Python dependencies
```

---

## 7. Getting Started

### Prerequisites
* Python 3.10+
* Redis 7.x (Local or Docker)
* Node.js 18+ (For Dashboard)

### Installation
1. **Clone the repository:**
   ```bash
   git clone https://github.com/MayurRajeshKeni/Prahari.git
   cd Prahari
   ```

2. **Set up Python virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Running the Log Parser
To parse a raw web server log file into an ML-ready CSV with extracted features:
```bash
python data_pipeline/log_parser.py <path_to_raw_log> <output_csv_path> --type apache_access
```
*Supported `--type` options:* `apache_access`, `apache_error`, `linux`.
