from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from ruamel.yaml import YAML

class ProjectConfig(BaseModel):
    id: str
    name: str

class PathConfig(BaseModel):
    processes: Path = Path("./processes")
    skills: Path = Path("./skills")
    tools: Path = Path("./tools")
    schemas: Path = Path("./schemas")

class PolicyConfig(BaseModel):
    dry_run_blocks_side_effects: bool = True
    require_approval_for_external_writes: bool = True

class CLIAdapterConfig(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)

class LLMConfig(BaseModel):
    provider: str = "gemini"  # cli | gemini | openai
    model: str = "gemini-2.5-flash"
    cli: Optional[CLIAdapterConfig] = None

class MCPServerConfig(BaseModel):
    command: str
    args: List[str] = Field(default_factory=list)

class MCPConfig(BaseModel):
    servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)

class DeployConfig(BaseModel):
    target: str = "docker"  # docker | fly.io
    app_name: Optional[str] = None
    region: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)

class WorkspaceConfig(BaseModel):
    project: ProjectConfig
    paths: PathConfig = Field(default_factory=PathConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    mcp: MCPConfig = Field(default_factory=MCPConfig)
    deploy: Optional[DeployConfig] = None

def find_workspace_root(start_path: Path = Path(".")) -> Path:
    """Search upwards from start_path to find a directory containing pdt.yaml."""
    current = start_path.resolve()
    for parent in [current] + list(current.parents):
        if (parent / "pdt.yaml").exists():
            return parent
    raise FileNotFoundError("Could not find pdt.yaml in any parent directory. Run 'pdt init' to initialize a workspace.")

def load_config(workspace_root: Path) -> WorkspaceConfig:
    config_path = workspace_root / "pdt.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found at {config_path}")
    
    yaml = YAML(typ='safe')
    with open(config_path, 'r') as f:
        data = yaml.load(f)
    
    if not data:
        raise ValueError(f"Configuration file at {config_path} is empty")
        
    return WorkspaceConfig.model_validate(data)

def init_workspace(path: Path) -> Path:
    """Initializes a workspace folder with pdt.yaml and subdirectories."""
    path.mkdir(parents=True, exist_ok=True)
    
    # Create standard directories
    for folder in ["processes", "skills", "tools", "schemas"]:
        (path / folder).mkdir(parents=True, exist_ok=True)
        
    config_path = path / "pdt.yaml"
    if not config_path.exists():
        yaml_content = """# Global PDT configuration file
project:
  id: my_project
  name: My Project

paths:
  processes: ./processes
  skills: ./skills
  tools: ./tools
  schemas: ./schemas

policy:
  dry_run_blocks_side_effects: true
  require_approval_for_external_writes: true

llm:
  provider: gemini
  model: gemini-2.5-flash

mcp:
  servers: {}
"""
        with open(config_path, "w") as f:
            f.write(yaml_content)
            
    return path
