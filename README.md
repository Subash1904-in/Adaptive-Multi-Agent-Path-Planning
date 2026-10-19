# Adaptive Multi-Agent Path Planning for Autonomous Vehicles

[![CI Pipeline](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/workflows/ci.yml/badge.svg)](https://github.com/Subash1904-in/Adaptive-Multi-Agent-Path-Planning/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Node Version](https://img.shields.io/badge/node-22.x-green.svg)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

> **Important Notice:** This software is developed solely as an academic research and educational simulation platform. It is not intended, certified, or validated for safety-critical real-world autonomous vehicle control.

---

## 1. Project Overview

The **Adaptive Multi-Agent Path Planning (AMAPP)** platform is a comprehensive simulation framework designed to explore decentralized coordination, dynamic route optimization, and collision avoidance among autonomous vehicles operating in realistic traffic conditions.

### Key Capabilities
- **Decentralized Vehicle-to-Vehicle (V2V) Communication:** Peer-to-peer message dissemination within a spatial communication radius, simulating channel noise, packet loss, and latency.
- **Adaptive Path Planning & Hazard Avoidance:** Real-time dynamic graph-based rerouting (A* / Dijkstra) triggered by hazard and congestion alerts.
- **AI-Based Decision-Making & Reinforcement Learning:** Integrated Gymnasium multi-agent environment trained with Stable-Baselines3 for intelligent route selection.
- **Real-World Road Networks:** Ingestion and parsing of OpenStreetMap (OSM) geometries alongside a deterministic offline fallback grid.
- **Dynamic Traffic & Pedestrian Elements:** Signalized intersections, pedestrian crosswalks, jaywalking events, and emergency vehicle priority corridors.
- **Real-Time 3D Visualization Dashboard:** Interactive web dashboard powered by Django Channels (WebSockets) and Three.js for real-time telemetry rendering and simulation steering.

---

## 2. Technology Stack

- **Authoritative Backend Simulation:** Python 3.11, NetworkX, NumPy, SciPy
- **Web & Streaming Framework:** Django, Django REST Framework, Django Channels, Daphne (ASGI)
- **Reinforcement Learning:** Gymnasium, Stable-Baselines3
- **Map & Geospatial Data:** OpenStreetMap (OSM), OSMnx
- **3D Visualization & Frontend:** TypeScript, Three.js, Vite
- **Testing & Quality Assurance:** pytest, pytest-cov, Ruff, ESLint
- **DevOps & Reproducibility:** GitHub Actions, Docker, Docker Compose

---

## 3. The 14 Functional Requirements

The platform is designed around 14 core functional requirements defined in `Project_Objective_and_Requirements.pdf`:

1. **Vehicle-to-Vehicle (V2V) Communication**
2. **Multi-Agent Autonomous Vehicle Environment**
3. **Real-World Map Integration**
4. **Traffic and Pedestrian Simulation**
5. **Motion Planning and Performance Benchmarking**
6. **Decentralized Vehicle Communication**
7. **Adaptive Path Planning**
8. **AI-Based Decision-Making**
9. **Collision Detection and Avoidance**
10. **Emergency Vehicle Priority**
11. **Communication Range Detection**
12. **Communication Failure Handling**
13. **AI Model Training Using Reinforcement Learning**
14. **Real-Time 3D Visualization and Interactive Dashboard**

For complete status and mapping, see [REQUIREMENTS_TRACEABILITY.md](file:///c:/Users/ssuba/Documents/Potatoooooo/Potatooo's%20Main%20project/Adaptive-Multi-Agent-Path-Planning/REQUIREMENTS_TRACEABILITY.md).

---

## 4. System Architecture

For architectural specifications, data contracts, and component boundaries, refer to [ARCHITECTURE.md](file:///c:/Users/ssuba/Documents/Potatoooooo/Potatooo's%20Main%20project/Adaptive-Multi-Agent-Path-Planning/ARCHITECTURE.md).

```text
AMAPP Architecture
├── Frontend (Three.js 3D Scene + HUD Dashboard)
│    ↕ (WebSockets JSON stream + REST API)
├── Backend Server (Django Channels ASGI + Daphne + DRF)
│    ↕ (Internal Memory / Direct API)
├── Simulation Engine (Clock, Spatial Grid, Map Graph, Agents)
│    ├── Decentralized V2V Message Network
│    ├── Collision & Headway Safety System
│    └── Adaptive Path Planner (A*)
└── RL Subsystem (Gymnasium Multi-Agent Environment + SB3 Policy)
```

---

## 5. Development Strategy (40 Incremental Phases)

This project follows a strict 40-phase incremental development roadmap. Each phase delivers a functional, tested increment without premature code generation.

Current status and ongoing progress are tracked in [PROJECT_STATUS.md](file:///c:/Users/ssuba/Documents/Potatoooooo/Potatooo's%20Main%20project/Adaptive-Multi-Agent-Path-Planning/PROJECT_STATUS.md).

---

## 6. Getting Started & Prerequisites

### Prerequisites
- **Python:** 3.11.x
- **Node.js:** 22.x or 20.x LTS
- **npm:** 10.x
- **Git:** 2.40+

### Verification Commands
```bash
python --version  # Must be 3.11+
node --version    # Must be 20.x or 22.x
git --version     # Must be 2.40+
```

---

## 7. Documentation Directory

- [PROJECT_STATUS.md](file:///c:/Users/ssuba/Documents/Potatoooooo/Potatooo's%20Main%20project/Adaptive-Multi-Agent-Path-Planning/PROJECT_STATUS.md): Primary status and handoff notes.
- [ARCHITECTURE.md](file:///c:/Users/ssuba/Documents/Potatoooooo/Potatooo's%20Main%20project/Adaptive-Multi-Agent-Path-Planning/ARCHITECTURE.md): Comprehensive system architecture and data models.
- [REQUIREMENTS_TRACEABILITY.md](file:///c:/Users/ssuba/Documents/Potatoooooo/Potatooo's%20Main%20project/Adaptive-Multi-Agent-Path-Planning/REQUIREMENTS_TRACEABILITY.md): 14 Functional Requirements traceability matrix.
- [docs/progress/PHASE_00.md](file:///c:/Users/ssuba/Documents/Potatoooooo/Potatooo's%20Main%20project/Adaptive-Multi-Agent-Path-Planning/docs/progress/PHASE_00.md): Phase 0 preparation report.
- [docs/TESTING.md](file:///c:/Users/ssuba/Documents/Potatoooooo/Potatooo's%20Main%20project/Adaptive-Multi-Agent-Path-Planning/docs/TESTING.md): Testing standards, fixtures, and regression policies.
- [docs/API.md](file:///c:/Users/ssuba/Documents/Potatoooooo/Potatooo's%20Main%20project/Adaptive-Multi-Agent-Path-Planning/docs/API.md): API and WebSocket telemetry protocol contracts.
