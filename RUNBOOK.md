# Runbook: Project Prahari — Log Parser

> Quick-start guide for running the multi-format log parser (`data_pipeline/log_parser.py`)

---

## Prerequisites

- **Python 3.11+** (tested on 3.14)
- **Virtual environment** (already created at `.venv/`)

---

## Setup

```bash
# Clone repo
git clone https://github.com/MayurRajeshKeni/Prahari
cd Prahari

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Windows (cmd):
.venv\Scripts\activate.bat
# Linux/macOS:
source .venv/bin/activate

# Verify dependencies installed
python -c "import pandas, xgboost, sklearn, fastapi, redis; print('OK')"
```

---

## Log Parser Usage

```bash
python data_pipeline/log_parser.py <input_log_file> <output_csv_file> --type <apache_access|apache_error|linux> [--chunk-size N]
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `input` | Yes | Path to raw log file |
| `output` | Yes | Path for output CSV (features) |
| `--type` | Yes | Log format: `apache_access`, `apache_error`, `linux` |
| `--chunk-size` | No | Rows per chunk (default: 10000) |

---

## Supported Log Formats

### 1. Apache Access Log (`--type apache_access`)
**Format:** Combined Log Format (Apache/Nginx default)
```
127.0.0.1 - - [21/Aug/2026:10:30:45 +0000] "GET /api/users HTTP/1.1" 200 1234 "-" "Mozilla/5.0..."
```
**Extracted fields:** `ip`, `timestamp`, `method`, `url`, `status`, `size`, `referer`, `user_agent`
**Features:** request velocity, URL depth/query/static, bot/mobile UA flags, time features

### 2. Apache Error Log (`--type apache_error`)
**Format:** Apache error log
```
[Thu Jun 09 06:07:04 2005] [notice] LDAP: Built with OpenLDAP LDAP SDK
[Thu Jun 09 06:07:05 2005] [error] env.createBean2(): Factory error creating channel.jni:jni
```
**Extracted fields:** `timestamp`, `level`, `message`
**Features:** `is_error`, `is_warn`, `is_notice`, `msg_length`, `has_exception`

### 3. Linux Syslog (`--type linux`)
**Format:** Standard syslog (RFC 3164)
```
Jun  9 06:06:20 combo kernel: BIOS-provided physical RAM map:
Jun  9 06:06:20 combo syslog: syslogd startup succeeded
```
**Extracted fields:** `timestamp`, `host`, `service`, `message`
**Features:** `is_kernel`, `msg_length`, `has_hardware`

---

## Examples

```bash
# Apache access log
python data_pipeline/log_parser.py data/raw/access.log data/processed/access_features.csv --type apache_access

# Apache error log
python data_pipeline/log_parser.py data/raw/error.log data/processed/error_features.csv --type apache_error

# Linux syslog
python data_pipeline/log_parser.py data/raw/syslog.log data/processed/linux_features.csv --type linux

# Custom chunk size (e.g., 5000 rows)
python data_pipeline/log_parser.py data/raw/access.log data/processed/access_features.csv --type apache_access --chunk-size 5000
```

---

## Output

- CSV file with extracted features per log line
- Columns vary by `--type` (see feature lists above)
- Ready for ML training (`train_model.py` — Phase 1, next step)

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ModuleNotFoundError: pandas` | Run `pip install -r requirements.txt` inside `.venv` |
| `FileNotFoundError` | Check input path; use absolute paths if needed |
| Zero rows parsed | Verify log format matches `--type`; check sample lines |
| MemoryError | Reduce `--chunk-size` (e.g., 5000) |

---

---

## Model Training & Artifact Export

Once `data/processed_access.csv` (or any processed feature CSV) has been generated:

```bash
python data_pipeline/train_model.py data/processed_access.csv --output-dir models
```

### Artifacts Exported
* `models/xgboost_abuse_model.json` — Native XGBoost tree serialization for fast runtime loading.
* `models/xgboost_abuse_model.pkl` — Scikit-learn / joblib model object.
* `models/feature_metadata.json` — Feature names and runtime column order for Phase 3 Gateway inference.
* `models/evaluation_metrics.json` — Precision, recall, F1, ROC-AUC, and feature importances.

---

## Synthetic Data Generation (Testing)

To generate synthetic Apache access logs with realistic human traffic vs. rapid bot/scraper bursts:

```bash
python data_pipeline/generate_sample_logs.py
```

---

## Project Structure

```
Prahari/
├── .venv/                 # Virtual environment (gitignored)
├── data/
│   ├── raw/               # Input raw logs (Apache, Linux)
│   └── processed_access.csv # Processed feature dataset
├── data_pipeline/
│   ├── log_parser.py      # Multi-format streaming log parser
│   ├── generate_sample_logs.py # Synthetic traffic generator
│   └── train_model.py     # XGBoost classifier training & export
├── models/
│   ├── xgboost_abuse_model.json
│   ├── xgboost_abuse_model.pkl
│   ├── feature_metadata.json
│   └── evaluation_metrics.json
├── requirements.txt
├── .gitignore
├── Memory.md
├── Phases.md
├── PRD.md
└── RUNBOOK.md             # This file
```