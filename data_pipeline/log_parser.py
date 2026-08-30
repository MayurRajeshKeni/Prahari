import pandas as pd
import re
import argparse
from pathlib import Path
from typing import Iterator, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CHUNK_SIZE = 10000

APACHE_ACCESS_PATTERN = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] "(?P<method>\S+) (?P<url>\S+) \S+" (?P<status>\d+) (?P<size>\S+) "(?P<referer>[^"]*)" "(?P<user_agent>[^"]*)"'
)

APACHE_ERROR_PATTERN = re.compile(
    r'\[(?P<timestamp>[^\]]+)\] \[(?P<level>\w+)\] (?P<message>.+)'
)

LINUX_SYSLOG_PATTERN = re.compile(
    r'(?P<timestamp>\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<service>\S+?):\s*(?P<message>.+)'
)

LOG_PATTERNS = {
    'apache_access': APACHE_ACCESS_PATTERN,
    'apache_error': APACHE_ERROR_PATTERN,
    'linux': LINUX_SYSLOG_PATTERN,
}


def parse_log_line(line: str, log_type: str) -> Optional[dict]:
    pattern = LOG_PATTERNS.get(log_type)
    if not pattern:
        raise ValueError(f"Unknown log type: {log_type}")
    match = pattern.match(line.strip())
    if not match:
        return None
    return match.groupdict()


def read_logs_chunked(file_path: str, log_type: str, chunk_size: int = CHUNK_SIZE) -> Iterator[pd.DataFrame]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {file_path}")

    logger.info(f"Reading {log_type} logs from {file_path} in chunks of {chunk_size}")

    chunks = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parsed = parse_log_line(line, log_type)
            if parsed:
                chunks.append(parsed)
            if len(chunks) >= chunk_size:
                yield pd.DataFrame(chunks)
                chunks = []

    if chunks:
        yield pd.DataFrame(chunks)


def extract_features(df: pd.DataFrame, log_type: str) -> pd.DataFrame:
    df = df.copy()

    if log_type == 'apache_access':
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='%d/%b/%Y:%H:%M:%S %z', errors='coerce')
        df['status'] = pd.to_numeric(df['status'], errors='coerce')
        df['size'] = pd.to_numeric(df['size'].replace('-', '0'), errors='coerce')

        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)

        df['url_path'] = df['url'].str.extract(r'([^?#]+)')
        df['url_depth'] = df['url_path'].str.count('/')
        df['has_query'] = df['url'].str.contains(r'\?').astype(int)
        df['is_static'] = df['url_path'].str.contains(r'\.(css|js|png|jpg|jpeg|gif|ico|woff|svg)$', case=False).astype(int)

        df['ua_length'] = df['user_agent'].str.len()
        df['is_bot_ua'] = df['user_agent'].str.contains(r'bot|crawler|spider|scraper|python|curl|wget|go-http', case=False, na=False).astype(int)
        df['is_mobile_ua'] = df['user_agent'].str.contains(r'mobile|android|iphone', case=False, na=False).astype(int)

        df['request_velocity'] = df.groupby('ip')['timestamp'].diff().dt.total_seconds().fillna(0)
        df['requests_per_ip'] = df.groupby('ip')['ip'].transform('count')

        df = df.dropna(subset=['timestamp', 'ip'])

    elif log_type == 'apache_error':
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='%a %b %d %H:%M:%S %Y', errors='coerce')
        df['level'] = df['level'].str.lower()
        df['is_error'] = (df['level'] == 'error').astype(int)
        df['is_warn'] = (df['level'] == 'warn').astype(int)
        df['is_notice'] = (df['level'] == 'notice').astype(int)
        df['msg_length'] = df['message'].str.len()
        df['has_exception'] = df['message'].str.contains(r'exception|error|fail|fatal', case=False, na=False).astype(int)
        df = df.dropna(subset=['timestamp'])

    elif log_type == 'linux':
        df['timestamp'] = pd.to_datetime(df['timestamp'], format='%b %d %H:%M:%S', errors='coerce')
        df['service'] = df['service'].str.replace(':', '', regex=False)
        df['msg_length'] = df['message'].str.len()
        df['is_kernel'] = (df['service'] == 'kernel').astype(int)
        df['has_hardware'] = df['message'].str.contains(r'bios|memory|cpu|disk|usb|pci', case=False, na=False).astype(int)
        df = df.dropna(subset=['timestamp'])

    return df


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    df = df.drop_duplicates()

    low_variance_cols = [col for col in df.columns if df[col].nunique() <= 1]
    if low_variance_cols:
        logger.info(f"Dropping low-variance columns: {low_variance_cols}")
        df = df.drop(columns=low_variance_cols)

    numeric_cols = df.select_dtypes(include=['number']).columns
    for col in numeric_cols:
        if df[col].isnull().any():
            df[col] = df[col].fillna(df[col].median())

    return df


def process_logs(input_path: str, output_path: str, log_type: str, chunk_size: int = CHUNK_SIZE) -> None:
    logger.info(f"Starting {log_type} log processing: {input_path} -> {output_path}")

    all_chunks = []
    for i, chunk in enumerate(read_logs_chunked(input_path, log_type, chunk_size)):
        logger.info(f"Processing chunk {i + 1} ({len(chunk)} rows)")
        chunk = extract_features(chunk, log_type)
        chunk = clean_data(chunk)
        all_chunks.append(chunk)

    if all_chunks:
        final_df = pd.concat(all_chunks, ignore_index=True)
        final_df.to_csv(output_path, index=False)
        logger.info(f"Processed {len(final_df)} total rows. Saved to {output_path}")
    else:
        logger.warning("No valid log entries found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse and extract features from log files")
    parser.add_argument("input", help="Input log file path")
    parser.add_argument("output", help="Output CSV file path")
    parser.add_argument("--type", choices=['apache_access', 'apache_error', 'linux'], required=True,
                        help="Log format type")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE, help="Chunk size for processing")

    args = parser.parse_args()
    process_logs(args.input, args.output, args.type, args.chunk_size)