# RelayMD 🧬⚡️

**A distributed execution framework for high-throughput molecular dynamics and binding free energy calculations across heterogeneous hardware.**

 RelayMD is an open-source orchestration system built for computational chemistry and drug discovery. It allows researchers to seamlessly distribute complex, long-running molecular simulations across highly fragmented compute environments—treating university HPCs (Slurm), decentralized GPU networks (SaladCloud), and local lab workstations as a single, unified compute fabric.

## 🔬 The Problem: The "Last Mile" of Drug Design Compute

Accurate binding free energy calculations are critical for modern drug design, but they require massive amounts of GPU compute. Existing open-source orchestration tools (like alchemiscale) are incredibly powerful but are heavily optimized for large, well-funded consortiums using enterprise cloud infrastructure or massive grids like Folding@Home.

Independent academic labs, PhD researchers, and indie biotechs are often priced out of enterprise cloud GPUs, relying instead on a patchwork of low-cost, decentralized consumer GPUs (like SaladCloud), legacy university Slurm clusters, and idle lab machines.

RelayMD bridges this gap. It is the connective infrastructure that scavenges and orchestrates fragmented compute, making advanced drug design pipelines accessible to resource-constrained research environments.

## ✨ Key Features

- Hardware & Scheduler Agnostic: Native support for Slurm schedulers, Docker, SaladCloud nodes, and bare-metal lab workstations.
- Fault-Tolerant Checkpointing: Built for preemptible, low-cost spot instances. RelayMD utilizes a robust `jobs/{job_id}/checkpoints/latest` architecture, ensuring long-running MD simulations can survive sudden node preemption without data loss.
- Optimized for Binding Free Energy: Designed specifically to handle the complex state machines required for Free Energy Perturbation (FEP) and thermodynamic integration workflows.
- Engine Integrations: Architecture supports leading open-source MD engines (OpenMM, GROMACS).

## 🏗️ Architecture Overview

RelayMD utilizes a central Orchestrator that manages job states, task queues, and persistent storage, distributing workloads to lightweight Worker nodes running on disparate hardware.

## 🚀 Getting Started

RelayMD is currently under active development. The easiest way to get started is by cloning the repository and setting up the orchestrator locally using our CLI tools.

### Prerequisites

- Python 3.10+
- `uv` (recommended) or `pip`
- Docker (optional, for containerized workflows)

### Installation

Clone the repository:

```bash
git clone https://github.com/ballaneypranav/RelayMD.git
cd RelayMD
```

Install dependencies:

RelayMD uses uv for lightning-fast Python dependency management.

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

### Configuration

Copy the example configuration file to set up your environment variables and secrets:

```bash
cp deploy/config.example.yaml config.yaml
```

### Running the Orchestrator

You can start the central orchestrator and the dashboard proxy using the built-in CLI command:

```bash
relaymd-cli service up
```

(Alternatively, for a persistent local development environment, you can use the provided tmux utility: `./deploy/tmux/start-orchestrator.sh`)

### Deploying Workers

Worker nodes pull tasks from the Orchestrator and actually run the molecular dynamics simulations. Check the `deploy/` directory for specific guides on attaching workers from different environments:

- HPC / Slurm Workloads
- SaladCloud GPU Networks

## 📖 Documentation

For a deeper dive into the technical internals, check out the `docs/` folder:

- [Core Architecture](docs/architecture.md)
- [Job Lifecycle](docs/job-lifecycle.md)
- [Tech Stack & Development Guidelines](docs/tech-stack.md)
- [Deployment Guide](docs/deployment.md)

_RelayMD is actively developed to support computational chemistry research. Contributions, issues, and feature requests from the open-source science community are highly encouraged._