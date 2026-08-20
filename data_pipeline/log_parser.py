import pandas as pd
import re
from pathlib import Path
from typing import Iterator, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LOG_PATTERN = re.compile(
    r'(?P<ip>\S+) \S+ \S+ \[(?P<timestamp>[^\]]+)\] "(?P<method>\S+) (?P<url>\S+) \S+" (?P<status>\d+) (?P<size>\S+) "(?P<referer>[^"]*)" "(?P<user_agent>[^"]*)"'
)

CHUNK_SIZE = 10000


def parse_log_line(line: str) -> Optional[dict]:
    match = LOG_PATTERN.match(line.strip())
    if not match:
        return None
    return match.groupdict()


def read_logs_chunked(file_path: str, chunk_size: int = CHUNK_SIZE) -> Iterator[pd.DataFrame]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Log file not found: {file_path}")

    logger.info(f"Reading logs from {file_path} in chunks of {chunk_size}")

    chunks = []
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            parsed = parse_log_line(line)
            if parsed:
                chunks.append(parsed)
            if len(chunks) >= chunk_size:
                yield pd.DataFrame(chunks)
                chunks = []

    if chunks:
        yield pd.DataFrame(chunks)


def extract_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

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


def process_logs(input_path: str, output_path: str, chunk_size: int = CHUNK_SIZE) -> None:
    logger.info(f"Starting log processing: {input_path} -> {output_path}")

    all_chunks = []
    for i, chunk in enumerate(read_logs_chunked(input_path, chunk_size)):
        logger.info(f"Processing chunk {i + 1} ({len(chunk)} rows)")
        chunk = extract_features(chunk)
        chunk = clean_data(chunk)
        all_chunks.append(chunk)

    if all_chunks:
        final_df = pd.concat(all_chunks, ignore_index=True)
        final_df.to_csv(output_path, index=False)
        logger.info(f"Processed {len(final_df)} total rows. Saved to {output_path}")
    else:
        logger.warning("No valid log entries found")


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python log_parser.py <input_log_file> <output_csv_file>")
        sys.exit(1)

    process_logs(sys.argv[1], sys.argv[2])