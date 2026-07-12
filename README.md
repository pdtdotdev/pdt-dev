# PDT

> **Git-native execution for governed, AI-assisted operational workflows.**

PDT turns Markdown SOPs into executable workflows.

Define a process in `PROCESS.md`, commit it to Git, and use PDT to validate, run, pause, resume, and deploy it. PDT executes one step at a time, records evidence, resolves tools and skills, and stops for human approval when required.

```bash
pip install run-pdt

pdt init
pdt lint processes/example/PROCESS.md
pdt run processes/example/PROCESS.md
```

## Why PDT?

Operational workflows often live across SOP documents, prompts, scripts, spreadsheets, and automation tools. That makes important business logic difficult to review, test, govern, and reuse.

PDT brings those workflows into a common execution model:

* Processes are readable Markdown and versioned in Git.
* Deterministic tools handle predictable work.
* Skills provide reusable guidance for AI-assisted work.
* Each step receives bounded context and permissions.
* Runs preserve inputs, outputs, logs, tool calls, and evidence.
* Approval gates keep humans responsible for exceptions and judgment.

Think of PDT as **dbt for operational workflows**: conventions, validation, lineage, and deployable execution for work outside the data warehouse.

## A `PROCESS.md` file

```markdown
---
id: growth_experiment_review
name: Growth Experiment Review
version: 0.1.0
owner: growth-team
status: active
---

# Description

Review active growth experiments and prepare an assessment for approval.

# Workflow

## Step 1: Load active experiments

Load active experiments using `tool/experiment_lookup`.

## Step 2: Assess performance

Evaluate conversion metrics using `skill/experiment-analysis`.

Return a result matching `schema/experiment-summary`.

## Step 3: Approve experiment

Request final business approval before closing the experiment.
```

PDT parses the workflow, resolves its references, and executes each step in order. When it reaches an approval or exception gate, it saves the current state and waits for a human response.

## Core concepts

### Processes

Processes define what must happen: the sequence, business rules, constraints, owners, and approval points.

### Skills

Skills describe how to perform reusable AI-assisted work. They can be shared across many processes.

### Tools

Tools wrap executable code, APIs, or scripts used for deterministic actions.

### Schemas

Schemas define structured outputs and validation contracts.

This separation keeps reusable capabilities independent from the business processes that govern when and how they are used.

## Workspace layout

```text
workspace/
├── pdt.yaml
├── processes/
│   └── growth_experiment_review/
│       └── PROCESS.md
├── skills/
│   └── experiment-analysis/
│       └── SKILL.md
├── tools/
│   └── experiment_lookup/
│       ├── tool.yaml
│       └── main.py
└── schemas/
    └── experiment-summary.schema.json
```

## CLI

Initialize a workspace:

```bash
pdt init [workspace_path]
```

Validate a process and its references:

```bash
pdt lint processes/growth_experiment_review/PROCESS.md
```

Inspect the parsed process as JSON:

```bash
pdt parse processes/growth_experiment_review/PROCESS.md
```

Run a complete process:

```bash
pdt run processes/growth_experiment_review/PROCESS.md --input metrics.json
```

Run one step:

```bash
pdt run processes/growth_experiment_review/PROCESS.md --step 2
```

Resume a paused run:

```bash
pdt run --resume run_98a72f1c
```

Generate deployment configuration:

```bash
pdt deploy --target docker --dry-run
```

## API server

Run the built-in FastAPI service:

```bash
uvicorn pdt_cli.server:app --port 8080
```

Available endpoints include:

```text
POST /run/{process_id}       Start a process
GET  /status/{run_id}        Inspect status and evidence
POST /approve/{run_id}       Approve and resume a paused run
```

## Design principles

PDT is built around a discipline called **Workflow Engineering**:

1. Business processes should be readable by the people who own them.
2. Operational logic should be versioned, reviewable, and testable.
3. AI reasoning should be bounded by explicit steps, context, and tools.
4. Important decisions and exceptions should remain visible to humans.
5. Every run should leave enough evidence to understand what happened.
