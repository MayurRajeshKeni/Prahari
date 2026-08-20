# Project Requirement Document (PRD)

## 1. Project Name
**Project Prahari** (Distributed Rate Limiter & ML Abuse Gateway)

## 2. Objective
Build an intelligent, distributed API gateway that intercepts incoming HTTP traffic, enforces atomic rate-limiting rules, and dynamically detects and mitigates bot/abuse traffic using a machine learning classifier.

## 3. Target Users
*   **Backend Engineers & System Admins:** To protect vulnerable backend services and databases from volumetric DDoS attacks and malicious web scrapers.
*   **API Providers:** To enforce tier-based API quotas reliably across concurrent clients.

## 4. Core Features
*   **Distributed Rate Limiting:** Implements a Sliding Window Counter algorithm to track request velocity.
*   **Atomic Concurrency Control:** Prevents race conditions and double-counting under heavy load using in-memory data structures.
*   **Real-time ML Traffic Classification:** Analyzes request patterns asynchronously to classify traffic as `benign` or `bot`.
*   **Dynamic Mitigation:** Automatically reduces quotas or blocks IPs identified as malicious actors.
*   **Data Pipeline:** Processes raw web server logs to extract behavioral features for model training.
*   **Admin Dashboard (Optional/Lightweight):** A clean, real-time visualization of allowed vs. blocked requests.

## 5. Out of Scope (For V1)
*   User authentication / OAuth workflows.
*   Billing integrations.
*   Complex multi-node cluster deployment (Kubernetes).