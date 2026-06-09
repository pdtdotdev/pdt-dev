# PDT (Process Deploy Tool)

> **Git-native runtime for state-bounded operational AI workflows.**

`pdt` is a developer-focused Command Line Interface (CLI) and runtime engine designed to govern, parse, lint, and execute standard-conforming **`PROCESS.md`** files. 

Inspired by analytics engineering tools like `dbt`, `pdt` decouples general-purpose LLM capabilities (**skills**) from operational business logic and policies (**processes**). It provides deterministic execution boundaries, step-by-step state preservation, and human-in-the-loop (HITL) gates.

---

## Core Philosophy: Workflow Engineering

Most operational teams do not need another open-ended autonomous agent. They require a reliable framework to transform recurring, high-stakes business processes into structured, version-controlled workflows. 

PDT establishes this via **Workflow Engineering**—pairing deterministic execution structures with bounded model reasoning:
* **Decoupled Skills & Processes**: Skills describe *how* to perform a reusable task (general/mechanical); processes describe *what* should happen, in what order, and under what constraints (contextual/governing).
* **Markdown as Code**: `PROCESS.md` files are the "SQL of operations"—readable by non-developer process owners, versioned in Git, and executable by a computer.
* **Deterministic Bounding**: Instead of letting an LLM navigate a workflow in an open-ended loop (resulting in unpredictable execution costs and loops), the PDT runtime runs one isolated step at a time, enforcing boundaries and security.
* **Human-Centered Exceptions**: When exceptions or gates are hit, the runtime halts, saves state, and alerts humans to verify or approve the execution.

---

## Workspace Layout

A conforming PDT workspace is organized as follows:

```text
/workspace
├── pdt.yaml                          # Workspace configuration
├── processes/                        # Executable workflows
│   └── growth_experiment_review/
│       └── PROCESS.md
├── skills/                           # Capability guides
│   └── experiment-analysis/
│       └── SKILL.md
├── tools/                            # Code execution units
│   └── experiment_lookup/
│       ├── tool.yaml
│       └── main.py
└── schemas/                          # Data validation contracts
    └── experiment-summary.schema.json
```

---

## Anatomy of `PROCESS.md`

An executable SOP contains three main components:

```markdown
---
id: growth_experiment_review
name: Growth Experiment Review
version: 0.1.0
owner: growth-team
status: active
runtime: pdt.process.v0
---
# Description
A workflow to review growth experiments, aggregate conversions, and perform high-level evaluation before approval.

# Workflow
## Step 1: Load active experiments
Lookup all active experiments using the tool `tool/experiment_lookup`.

## Step 2: Assess statistical performance
Evaluate the total conversion metrics using `skill/experiment-analysis` and construct a structured JSON summary matching `schema/experiment-summary`.

## Step 3: Approve experiment
Review the assessment and request final business approval before closing.
```

---

## CLI Commands & Usage

Install the PDT package:
```bash
pip install run-dbt
```

### 1. `pdt init`
Initialize a new standard workspace directory layout with default configuration:
```bash
pdt init [workspace_path]
```

### 2. `pdt lint`
Validate workspace config, verify step index ordering, and resolve all inline reference links to confirm they point to valid skills, tools, processes, and schemas:
```bash
pdt lint processes/growth_experiment_review/PROCESS.md
```

### 3. `pdt parse`
Parse a `PROCESS.md` file and output a clean Abstract Syntax Tree (AST) in JSON format:
```bash
pdt parse processes/growth_experiment_review/PROCESS.md
```

### 4. `pdt run`
Execute the workflow steps sequentially. PDT automatically runs local tools, saves evidence, compiles bounded prompts, and pauses when a human gate (e.g. "approval") is encountered.

* **Execute workflow fully:**
  ```bash
  pdt run processes/growth_experiment_review/PROCESS.md --input metrics.json
  ```
* **Run a single step only:**
  ```bash
  pdt run processes/growth_experiment_review/PROCESS.md --step 2
  ```
* **Resume a paused workflow:**
  ```bash
  pdt run --resume run_98a72f1c
  ```

### 5. `pdt deploy`
Package the workspace and generate container/deployment configurations:
```bash
pdt deploy --target docker --dry-run
```

---

## Webhook Server Daemon

Deploy the workspace as a serverless runtime using the built-in FastAPI daemon:
```bash
uvicorn pdt_cli.server:app --port 8080
```
This exposes REST API endpoints to trigger and manage workflows remotely:
* `POST /run/{process_id}`: Trigger step execution with input payload.
* `GET /status/{run_id}`: Check status and inspect run evidence.
* `POST /approve/{run_id}`: Submit approval inputs to resume paused states.