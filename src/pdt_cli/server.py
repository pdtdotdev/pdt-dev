import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional, Any
from pathlib import Path

from pdt_cli.workspace import find_workspace_root, load_config
from pdt_cli.parser import parse_process_markdown
from pdt_cli.engine import ExecutionEngine
from pdt_cli.state import StateManager

app = FastAPI(title="PDT Server Daemon")

class RunPayload(BaseModel):
    inputs: Dict[str, str] = {}
    target_step: Optional[int] = None
    run_id: Optional[str] = None

class ApprovePayload(BaseModel):
    approval_input: Optional[str] = None

@app.post("/run/{process_id}")
def run_process(process_id: str, payload: RunPayload):
    try:
        workspace_root = find_workspace_root()
        config = load_config(workspace_root)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load workspace configuration: {e}")

    process_dir = workspace_root / config.paths.processes / process_id
    process_md = process_dir / "PROCESS.md"
    if not process_md.exists():
        raise HTTPException(status_code=404, detail=f"Process '{process_id}' not found at {process_md}")

    try:
        with open(process_md, 'r') as f:
            content = f.read()
        process_doc = parse_process_markdown(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse PROCESS.md: {e}")

    try:
        engine = ExecutionEngine(
            workspace_root=workspace_root,
            config=config,
            process_doc=process_doc,
            run_id=payload.run_id
        )
        state = engine.execute(
            inputs=payload.inputs,
            target_step=payload.target_step,
            resume=False
        )
        return state
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {e}")

@app.get("/status/{run_id}")
def get_status(run_id: str):
    try:
        workspace_root = find_workspace_root()
        state_mgr = StateManager(workspace_root, run_id=run_id)
        state = state_mgr.load_state()
        return state
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load run status: {e}")

@app.post("/approve/{run_id}")
def approve_run(run_id: str, payload: ApprovePayload):
    try:
        workspace_root = find_workspace_root()
        config = load_config(workspace_root)
        
        state_mgr = StateManager(workspace_root, run_id=run_id)
        state = state_mgr.load_state()
        process_id = state.process_id
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load run: {e}")

    process_dir = workspace_root / config.paths.processes / process_id
    process_md = process_dir / "PROCESS.md"
    if not process_md.exists():
        raise HTTPException(status_code=404, detail=f"Process '{process_id}' not found at {process_md}")

    try:
        with open(process_md, 'r') as f:
            content = f.read()
        process_doc = parse_process_markdown(content)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse PROCESS.md: {e}")

    try:
        engine = ExecutionEngine(
            workspace_root=workspace_root,
            config=config,
            process_doc=process_doc,
            run_id=run_id
        )
        new_state = engine.execute(
            inputs=state.inputs,
            resume=True,
            approval_input=payload.approval_input
        )
        return new_state
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to approve and resume run: {e}")
