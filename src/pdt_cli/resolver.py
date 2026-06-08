from pathlib import Path
from pdt_cli.workspace import WorkspaceConfig

def resolve_reference(ref_str: str, workspace_root: Path, config: WorkspaceConfig) -> Path:
    """
    Resolves a reference string (e.g. "tool/experiment_lookup") to an absolute path in the workspace.
    Raises FileNotFoundError if the resolved path or required file does not exist.
    """
    parts = ref_str.split('/', 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid reference format: '{ref_str}'. References must be in 'type/id' format.")
        
    ref_type, ref_id = parts
    
    if ref_type == "tool":
        # Check tools/<id>/tool.yaml
        tools_dir = workspace_root / config.paths.tools
        tool_dir = tools_dir / ref_id
        tool_yaml = tool_dir / "tool.yaml"
        if not tool_yaml.exists():
            raise FileNotFoundError(f"Tool reference '{ref_str}' resolved to '{tool_yaml}', but it does not exist.")
        return tool_yaml.absolute()
        
    elif ref_type == "skill":
        # Check skills/<id>/SKILL.md
        skills_dir = workspace_root / config.paths.skills
        skill_dir = skills_dir / ref_id
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise FileNotFoundError(f"Skill reference '{ref_str}' resolved to '{skill_md}', but it does not exist.")
        return skill_md.absolute()
        
    elif ref_type == "schema":
        # Check schemas/<id>.schema.json or schemas/<id>.json
        schemas_dir = workspace_root / config.paths.schemas
        schema_path1 = schemas_dir / f"{ref_id}.schema.json"
        schema_path2 = schemas_dir / f"{ref_id}.json"
        if schema_path1.exists():
            return schema_path1.absolute()
        elif schema_path2.exists():
            return schema_path2.absolute()
        else:
            raise FileNotFoundError(f"Schema reference '{ref_str}' resolved to '{schema_path1}' or '{schema_path2}', but neither exists.")
            
    elif ref_type == "process":
        # Check processes/<id>/PROCESS.md
        processes_dir = workspace_root / config.paths.processes
        process_dir = processes_dir / ref_id
        process_md = process_dir / "PROCESS.md"
        if not process_md.exists():
            raise FileNotFoundError(f"Process reference '{ref_str}' resolved to '{process_md}', but it does not exist.")
        return process_md.absolute()
        
    else:
        raise ValueError(f"Unknown reference type: '{ref_type}'. Supported: 'tool', 'skill', 'schema', 'process'.")
