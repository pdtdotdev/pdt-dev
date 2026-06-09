import json
import sys
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional
import typer

from pdt_cli.workspace import find_workspace_root, load_config, init_workspace
from pdt_cli.parser import parse_process_markdown
from pdt_cli.resolver import resolve_reference
from pdt_cli.engine import ExecutionEngine
from pdt_cli.state import StateManager

app = typer.Typer(help="PDT (Process Deploy Tool) — Git-native operational infrastructure.")

@app.command()
def init(
    path: Path = typer.Argument(Path("."), help="Path to initialize the PDT workspace.")
):
    """Initializes a standard empty workspace directory layout & creates default pdt.yaml."""
    try:
        resolved_path = init_workspace(path)
        typer.secho(f"✔ Workspace initialized successfully at {resolved_path.absolute()}", fg=typer.colors.GREEN, bold=True)
    except Exception as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def lint(
    file_path: Path = typer.Argument(..., help="Path to the PROCESS.md file to lint.")
):
    """Verifies workspace config, parses target PROCESS.md file, checks step indexes, and resolves all inline references."""
    try:
        # Resolve absolute path
        file_path = file_path.absolute()
        
        # Find and load workspace
        try:
            workspace_root = find_workspace_root(file_path.parent)
            config = load_config(workspace_root)
            typer.echo(f"✔ Workspace configuration verified at {workspace_root / 'pdt.yaml'}")
        except Exception as e:
            typer.secho(f"Error loading workspace configuration: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        # Parse process file
        if not file_path.exists():
            typer.secho(f"Error: file not found at {file_path}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        with open(file_path, 'r') as f:
            content = f.read()

        try:
            doc = parse_process_markdown(content)
            typer.echo(f"✔ Successfully parsed {file_path}")
        except Exception as e:
            typer.secho(f"Error parsing process Markdown: {e}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        # Check step indexes
        step_errors = []
        expected_index = 1
        for step in doc.steps:
            if step.index != expected_index:
                step_errors.append(f"Step index mismatch: expected Step {expected_index}, got Step {step.index}")
            expected_index += 1

        if step_errors:
            for err in step_errors:
                typer.secho(f"✖ {err}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        else:
            typer.echo("✔ Step indexes are sequential and start at 1")

        # Resolve all references
        ref_errors = []
        for step in doc.steps:
            for ref in step.references:
                try:
                    resolve_reference(ref, workspace_root, config)
                except Exception as e:
                    ref_errors.append(f"In step {step.index} '{step.title}': failed to resolve reference '{ref}': {e}")

        if ref_errors:
            for err in ref_errors:
                typer.secho(f"✖ {err}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
        else:
            typer.echo("✔ All inline references successfully resolved")

        typer.secho("✔ Lint checks passed successfully", fg=typer.colors.GREEN, bold=True)

    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"Unexpected error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def parse(
    file_path: Path = typer.Argument(..., help="Path to the PROCESS.md file to parse.")
):
    """Parses the markdown file and outputs a JSON tree of steps, frontmatter, and references."""
    try:
        if not file_path.exists():
            typer.secho(f"Error: file not found at {file_path}", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        with open(file_path, 'r') as f:
            content = f.read()

        doc = parse_process_markdown(content)
        print(doc.model_dump_json(indent=2))

    except Exception as e:
        typer.secho(f"Error parsing PROCESS.md: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def run(
    file_path: Optional[Path] = typer.Argument(None, help="Path to the PROCESS.md file to run."),
    input_file: Optional[Path] = typer.Option(None, "--input", "-i", help="JSON file containing run inputs."),
    step: Optional[int] = typer.Option(None, "--step", "-s", help="Step index to run (runs single step)."),
    resume_id: Optional[str] = typer.Option(None, "--resume", "-r", help="Run ID to resume execution from.")
):
    """Executes the workflow. Can execute fully, target a single step, resume from a HITL approval pause."""
    try:
        if not file_path and not resume_id:
            typer.secho("Error: Either file_path or --resume <run_id> must be specified", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)

        search_path = file_path.parent if file_path else Path(".")
        workspace_root = find_workspace_root(search_path)
        config = load_config(workspace_root)

        inputs = {}
        if input_file:
            if not input_file.exists():
                typer.secho(f"Error: input file '{input_file}' not found", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
            with open(input_file, 'r') as f:
                inputs = json.load(f)

        if resume_id:
            state_mgr = StateManager(workspace_root, run_id=resume_id)
            state = state_mgr.load_state()
            process_id = state.process_id
            process_dir = workspace_root / config.paths.processes / process_id
            process_md = process_dir / "PROCESS.md"
            if not process_md.exists():
                typer.secho(f"Error: PROCESS.md not found at {process_md} for resuming run {resume_id}", fg=typer.colors.RED, err=True)
                raise typer.Exit(code=1)
        else:
            process_md = file_path.absolute()

        with open(process_md, 'r') as f:
            content = f.read()
        process_doc = parse_process_markdown(content)

        engine = ExecutionEngine(
            workspace_root=workspace_root,
            config=config,
            process_doc=process_doc,
            run_id=resume_id
        )

        if resume_id:
            typer.echo(f"Resuming run '{resume_id}'...")
            approval_val = None
            if sys.stdin.isatty():
                approval_val = typer.prompt("Enter approval input/notes (or press Enter to approve)")
            state = engine.execute(inputs=inputs, resume=True, approval_input=approval_val)
        else:
            typer.echo(f"Starting execution of '{process_doc.frontmatter.name}' (Run ID: run_{engine.state_manager.run_id})...")
            state = engine.execute(inputs=inputs, target_step=step, resume=False)

        # Report final status
        if state.status == "completed":
            typer.secho("✔ Run completed successfully", fg=typer.colors.GREEN, bold=True)
        elif state.status == "waiting_for_approval":
            typer.secho(f"⚠ Run paused: Step {state.current_step_index} requires approval.", fg=typer.colors.YELLOW, bold=True)
            typer.echo(f"To approve, run: pdt run --resume {state.run_id}")
        elif state.status == "failed":
            typer.secho("✖ Run failed", fg=typer.colors.RED, bold=True)

    except typer.Exit:
        raise
    except Exception as e:
        typer.secho(f"Execution failed with error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def deploy(
    target: str = typer.Option("docker", "--target", help="Deployment target (docker | fly.io)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Mock deployment and report files generated.")
):
    """Packages workspace, scripts, and runtime environment. Spits out container config/Dockerfile."""
    try:
        workspace_root = find_workspace_root()
        config = load_config(workspace_root)
        
        # Create distribution directory
        dist_dir = workspace_root / ".pdt" / "dist"
        dist_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Generate Dockerfile
        dockerfile_content = """# 1. Base Python Runtime
FROM python:3.11-slim-bookworm

# 2. System dependencies (Node.js setup for JS-based tools)
RUN apt-get update && apt-get install -y \\
    curl \\
    gnupg \\
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \\
    && apt-get install -y nodejs \\
    && rm -rf /var/lib/apt/lists/*

# 3. Workspace Copying
WORKDIR /app
COPY pdt.yaml /app/
COPY processes/ /app/processes/
COPY skills/ /app/skills/
COPY schemas/ /app/schemas/
COPY tools/ /app/tools/

# 4. Dependency Packaging
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN find /app/tools -name "requirements.txt" -exec pip install -r {} \\;
RUN find /app/tools -name "package.json" -exec sh -c 'cd $(dirname {}) && npm install' \\;

# 5. PDT Runtime Installation
RUN pip install run-dbt

# 6. Expose HTTP API Port for process triggers
EXPOSE 8080

# 7. Start Webhook Listener Daemon
CMD ["uvicorn", "pdt_cli.server:app", "--host", "0.0.0.0", "--port", "8080"]
"""
        dockerfile_path = dist_dir / "Dockerfile"
        with open(dockerfile_path, "w") as f:
            f.write(dockerfile_content)
            
        fly_toml_path = None
        if target == "fly.io":
            app_name = "company-ops-pdt"
            region = "iad"
            if config.deploy:
                if config.deploy.app_name:
                    app_name = config.deploy.app_name
                if config.deploy.region:
                    region = config.deploy.region
                    
            fly_toml_content = f"""app = "{app_name}"
primary_region = "{region}"

[http_service]
  internal_port = 8080
  force_https = true
  auto_rollback = true
"""
            fly_toml_path = dist_dir / "fly.toml"
            with open(fly_toml_path, "w") as f:
                f.write(fly_toml_content)
                
        # Handle dry-run
        if dry_run:
            typer.secho("✔ Dry run: validation clean. Generated configurations:", fg=typer.colors.GREEN, bold=True)
            typer.echo(f"Dockerfile: {dockerfile_path.absolute()}")
            if fly_toml_path:
                typer.echo(f"fly.toml: {fly_toml_path.absolute()}")
            return

        # Verification of dependencies for actual deployment
        if target == "docker":
            if not shutil.which("docker"):
                typer.secho("Warning: 'docker' command line tool not found in PATH", fg=typer.colors.YELLOW)
            typer.echo("To deploy using Docker, run:")
            typer.secho(f"  docker build -t pdt-app -f {dockerfile_path} .", fg=typer.colors.CYAN)
        elif target == "fly.io":
            if not shutil.which("flyctl"):
                typer.secho("Warning: 'flyctl' command line tool not found in PATH", fg=typer.colors.YELLOW)
            typer.echo("To deploy to Fly.io, run:")
            typer.secho(f"  cd {dist_dir} && fly deploy", fg=typer.colors.CYAN)
            
    except Exception as e:
        typer.secho(f"Deploy failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

def cli():
    app()

if __name__ == "__main__":
    cli()
