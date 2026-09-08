"""
Synthetic Log Generator for Project Prahari
Generates realistic Apache Access Logs containing both benign human traffic
and abusive bot/scraper/DDoS traffic for training the XGBoost abuse classifier.
"""

import random
import datetime
from pathlib import Path

BENIGN_IPS = [f"192.168.1.{i}" for i in range(10, 50)] + [f"10.0.0.{i}" for i in range(10, 40)]
BOT_IPS = [f"203.0.113.{i}" for i in range(1, 15)] + [f"198.51.100.{i}" for i in range(1, 10)]

BENIGN_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
]

BOT_USER_AGENTS = [
    "python-requests/2.31.0",
    "curl/8.4.0",
    "Wget/1.21.4",
    "Scrapy/2.11.0 (+https://scrapy.org)",
    "Go-http-client/2.0",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; SemrushBot/7~bl; +http://www.semrush.com/bot.html)",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36" # Spoofed UA
]

BENIGN_ENDPOINTS = [
    ("/index.html", "GET", 200, 4500),
    ("/about", "GET", 200, 3200),
    ("/products", "GET", 200, 12800),
    ("/products?category=electronics", "GET", 200, 15400),
    ("/products?id=101", "GET", 200, 6800),
    ("/static/css/main.css", "GET", 200, 8900),
    ("/static/js/app.js", "GET", 200, 45200),
    ("/static/images/logo.png", "GET", 200, 18400),
    ("/api/v1/user/profile", "GET", 200, 1200),
    ("/api/v1/search?q=laptop", "GET", 200, 9400),
    ("/contact", "POST", 200, 850),
    ("/favicon.ico", "GET", 200, 1150)
]

BOT_ENDPOINTS = [
    ("/api/v1/users", "GET", [200, 429]),
    ("/api/v1/data/export", "GET", [200, 429, 403]),
    ("/admin", "GET", [403, 404]),
    ("/admin/login.php", "POST", [403, 401]),
    ("/.env", "GET", [404, 403]),
    ("/wp-login.php", "GET", [404]),
    ("/api/v1/products/dump", "GET", [429, 403]),
    ("/products?id=99999", "GET", [404, 429]),
    ("/api/v1/search?q=a", "GET", [200, 429])
]


def generate_apache_access_logs(output_file: str, num_records: int = 30000) -> None:
    path = Path(output_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    current_time = datetime.datetime(2026, 8, 20, 8, 0, 0, tzinfo=datetime.timezone.utc)
    
    # Track per-IP last request timestamp
    ip_timers = {ip: current_time for ip in BENIGN_IPS + BOT_IPS}
    
    lines = []
    
    # 70% benign traffic, 30% bot/abuse traffic
    for _ in range(num_records):
        is_bot = random.random() < 0.30
        
        if not is_bot:
            ip = random.choice(BENIGN_IPS)
            ua = random.choice(BENIGN_USER_AGENTS)
            endpoint, method, status, size = random.choice(BENIGN_ENDPOINTS)
            # Humans wait between 1 and 25 seconds between requests
            delta_seconds = random.uniform(1.5, 25.0)
            ip_timers[ip] += datetime.timedelta(seconds=delta_seconds)
            req_time = ip_timers[ip]
            referer = "https://example.com/index.html" if random.random() > 0.3 else "-"
            line = f'{ip} - - [{req_time.strftime("%d/%b/%Y:%H:%M:%S +0000")}] "{method} {endpoint} HTTP/1.1" {status} {size} "{referer}" "{ua}"\n'
        else:
            ip = random.choice(BOT_IPS)
            ua = random.choice(BOT_USER_AGENTS)
            endpoint_tuple = random.choice(BOT_ENDPOINTS)
            endpoint = endpoint_tuple[0]
            method = endpoint_tuple[1]
            status_opts = endpoint_tuple[2]
            status = random.choice(status_opts) if isinstance(status_opts, list) else status_opts
            size = random.randint(120, 1500)
            # Bots send requests in rapid bursts (0.01s to 0.4s)
            delta_seconds = random.uniform(0.01, 0.45)
            ip_timers[ip] += datetime.timedelta(seconds=delta_seconds)
            req_time = ip_timers[ip]
            referer = "-" if random.random() > 0.1 else "http://bot-source.net"
            line = f'{ip} - - [{req_time.strftime("%d/%b/%Y:%H:%M:%S +0000")}] "{method} {endpoint} HTTP/1.1" {status} {size} "{referer}" "{ua}"\n'
            
        lines.append((req_time, line))
        
    # Sort chronologically by timestamp
    lines.sort(key=lambda x: x[0])
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for _, line in lines:
            f.write(line)
            
    print(f"Generated {num_records} access log entries at {output_file}")


if __name__ == "__main__":
    generate_apache_access_logs("data/raw/Apache/access.log", 35000)
