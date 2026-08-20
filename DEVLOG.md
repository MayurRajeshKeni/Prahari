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