import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class ToolCallRecord(BaseModel):
    tool_id: str
    arguments: Dict[str, Any]
    output_file: Optional[str] = None

class StepState(BaseModel):
    index: int
    title: str
    status: str = "pending"  # pending | running | completed | waiting_for_approval | failed
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    output: Optional[str] = None

class RunState(BaseModel):
    run_id: str
    process_id: str
    version: str
    status: str = "running"  # running | completed | waiting_for_approval | failed
    start_time: datetime
    end_time: Optional[datetime] = None
    inputs: Dict[str, str] = Field(default_factory=dict)
    current_step_index: int = 1
    steps: List[StepState] = Field(default_factory=list)
    outputs: Dict[str, Any] = Field(default_factory=dict)

class StateManager:
    def __init__(self, workspace_root: Path, run_id: Optional[str] = None):
        self.workspace_root = workspace_root
        self.runs_dir = workspace_root / ".pdt" / "runs"
        
        if run_id:
            # Normalize run_id to always have the run_ prefix
            if run_id.startswith("run_"):
                self.run_id = run_id[4:]
            else:
                self.run_id = run_id
        else:
            self.run_id = uuid.uuid4().hex[:8]
            
        self.run_dir = self.runs_dir / f"run_{self.run_id}"
        self.run_json_path = self.run_dir / "run.json"
        self.logs_dir = self.run_dir / "logs"
        self.evidence_dir = self.run_dir / "evidence"
        
    def initialize_run(self, process_id: str, version: str, inputs: Dict[str, str], steps: List[StepState]) -> RunState:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        
        state = RunState(
            run_id=f"run_{self.run_id}",
            process_id=process_id,
            version=version,
            status="running",
            start_time=datetime.now(timezone.utc),
            inputs=inputs,
            current_step_index=1,
            steps=steps,
            outputs={}
        )
        self.save_state(state)
        return state
        
    def save_state(self, state: RunState):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with open(self.run_json_path, 'w') as f:
            f.write(state.model_dump_json(indent=2))
            
    def load_state(self) -> RunState:
        if not self.run_json_path.exists():
            # Try to search for run_id directly as folder name if it didn't match
            # (e.g. if the user specified the folder name directly)
            alt_path = self.runs_dir / self.run_id / "run.json"
            if alt_path.exists():
                self.run_dir = self.runs_dir / self.run_id
                self.run_json_path = alt_path
                self.logs_dir = self.run_dir / "logs"
                self.evidence_dir = self.run_dir / "evidence"
            else:
                raise FileNotFoundError(f"Run state file not found at {self.run_json_path}")
                
        with open(self.run_json_path, 'r') as f:
            data = json.load(f)
        return RunState.model_validate(data)
        
    def log_system(self, message: str):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.logs_dir / "system.log"
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(log_path, 'a') as f:
            f.write(f"[{timestamp}] {message}\n")
            
    def log_llm(self, prompt: str, response: str):
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        log_path = self.logs_dir / "llm_prompts.log"
        timestamp = datetime.now(timezone.utc).isoformat()
        with open(log_path, 'a') as f:
            f.write(f"--- PROMPT ({timestamp}) ---\n{prompt}\n--- RESPONSE ---\n{response}\n\n")
            
    def save_evidence(self, filename: str, content: str) -> Path:
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = self.evidence_dir / filename
        with open(evidence_path, 'w') as f:
            f.write(content)
        # Return path relative to the run directory (e.g. evidence/step1...)
        return Path("evidence") / filename
