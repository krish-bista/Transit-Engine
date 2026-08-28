# 1-Click Cloud Deployment Guide (Get Your Live Resume Link)

This guide walks you through deploying your **TransitEngine** full-stack system to the cloud for free so you can showcase a live, interactive link directly on your Resume, Portfolio, and GitHub profile.

---

## Recommended Free Cloud Platforms

| Platform | Best For | Setup Time | Custom Domain & SSL |
| :--- | :--- | :--- | :--- |
| **Render** (Recommended) | Easiest 1-click Docker deploy | ~2 minutes | Free Automatic HTTPS |
| **Railway** | Full-stack monorepos with Redis | ~3 minutes | Free Automatic HTTPS |
| **Fly.io** | Low-latency global edge | ~3 minutes | Free Automatic HTTPS |

---

## Option 1: Deploying to Render (Recommended)

Render offers free web service hosting and automatic GitHub deployments.

### Step 1: Push Code to GitHub
```bash
git add .
git commit -m "feat: complete full-stack RAPTOR transit engine with live web app"
git push origin main
```

### Step 2: Create Web Service on Render
1. Go to [https://dashboard.render.com](https://dashboard.render.com) and sign in with GitHub.
2. Click **New +** → **Web Service**.
3. Select your repository `transit-engine`.
4. Configure the service:
   - **Name**: `transit-engine` (or `yourname-transit-engine`)
   - **Runtime**: `Docker`
   - **Dockerfile Path**: `infra/Dockerfile.gateway`
   - **Docker Context**: `.` (root of repo)
   - **Plan**: `Free`
5. Click **Create Web Service**.

Within ~2 minutes, Render will build your container and give you a live HTTPS URL:
`https://your-transit-engine.onrender.com`

---

## Option 2: Deploying with Docker Compose (Railway / DigitalOcean / VPS)

You can run the entire cluster (`transit-engine`, `redis`, `telemetry`, `gateway`) using the included `docker-compose.yml`:

```bash
cd infra
docker compose up -d
```

Access the web interface at:
`http://localhost:8000`

---

## What to Put on Your Resume

### Project Title
**TransitEngine – High-Performance Multi-Modal Transit Engine & Live Telemetry Platform**  
*Live Demo: `https://your-transit-engine.onrender.com` | GitHub: `github.com/your-username/transit-engine`*

### Bullet Points
- **Engineered a high-throughput C++20 transit routing engine** implementing the RAPTOR (Round-based Public Transit Routing) algorithm on zero-copy Compressed Sparse Row (CSR) binary indices, achieving sub-millisecond query latencies ($< 1\text{ ms}$).
- **Built a real-time GTFS-RT streaming pipeline** using Redis Pub/Sub to dynamically ingest simulated vehicle delay deltas into live schedule vectors under thread-safe shared mutex locks.
- **Developed an interactive full-stack web dashboard & API Gateway** using FastAPI, WebSockets, and Leaflet/MapLibre, streaming 60 FPS live vehicle telemetry and rendering multi-leg itineraries.
- **Architected containerized microservices** with Docker Compose and deployed a cloud-ready platform serving REST, gRPC, and WebSocket clients.
