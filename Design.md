# Design & UI Specifications

*Note: As an infrastructure project, the primary "interface" is the API and terminal. However, an Admin Dashboard will be built to visualize traffic.*

## 1. Aesthetic Theme
*   **Vibe:** Cyber-security command center, minimalist CLI aesthetic.
*   **Theme:** Dark Mode exclusively.

## 2. Color Palette
*   **Background:** Dark Slate (`#0f172a`)
*   **Panels/Cards:** Deep Navy (`#1e293b`)
*   **Text (Primary):** Off-White (`#f8fafc`)
*   **Text (Muted):** Slate Gray (`#94a3b8`)
*   **Accent (Safe/Allowed):** Terminal Green (`#22c55e`)
*   **Accent (Blocked/Attack):** Alert Red (`#ef4444`)
*   **Accent (Warning/Throttle):** Amber (`#f59e0b`)

## 3. Typography
*   **Headers & UI Elements:** `Inter` (sans-serif) - Clean, modern, highly legible.
*   **Data, IP Addresses & Code:** `Fira Code` or `JetBrains Mono` (monospace) - Emphasizes the technical nature of the dashboard.

## 4. Dashboard Layout (React)
*   **Header:** Project Prahari logo/title and current server status (Online/Offline).
*   **Top Row Metrics (Cards):**
    *   Total Requests (Last 1m)
    *   Active Rate Limits
    *   Blocked Bots (ML Detections)
*   **Main View:** A real-time scrolling list or simple line chart showing incoming request IPs, their HTTP status (200 vs 429 vs 403), and latency.
*   **Tech constraints:** Use standard React components. CSS Modules or Tailwind CSS can be used to quickly apply the color palette.