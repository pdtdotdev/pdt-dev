import re
from typing import Dict, Any, List
from pydantic import BaseModel
from ruamel.yaml import YAML

class ProcessFrontmatter(BaseModel):
    id: str
    name: str
    version: str
    owner: str
    status: str = "active"
    runtime: str = "pdt.process.v0"
    extra: Dict[str, Any] = {}

class WorkflowStep(BaseModel):
    index: int
    title: str
    instructions: str
    references: List[str]

class ProcessDocument(BaseModel):
    frontmatter: ProcessFrontmatter
    description: str
    steps: List[WorkflowStep]

def parse_process_markdown(content: str) -> ProcessDocument:
    # 1. Parse YAML Frontmatter
    frontmatter_dict = {}
    yaml_pattern = re.compile(r'^---\s*\n(.*?)\n---\s*\n', re.DOTALL | re.MULTILINE)
    match = yaml_pattern.search(content)
    remaining_content = content
    if match:
        frontmatter_str = match.group(1)
        yaml = YAML(typ='safe')
        frontmatter_dict = yaml.load(frontmatter_str) or {}
        remaining_content = content[match.end():]
        
    standard_keys = {"id", "name", "version", "owner", "status", "runtime"}
    extra = {k: v for k, v in frontmatter_dict.items() if k not in standard_keys}
    
    frontmatter_args = {k: frontmatter_dict.get(k) for k in standard_keys if k in frontmatter_dict}
    frontmatter_args["extra"] = extra
    
    # Try parsing frontmatter
    try:
        frontmatter = ProcessFrontmatter(**frontmatter_args)
    except Exception as e:
        raise ValueError(f"Invalid PROCESS.md frontmatter: {e}")
        
    # 2. Extract Description and Workflow
    description = ""
    workflow_content = ""
    
    desc_match = re.search(r'^#\s+Description\b', remaining_content, re.MULTILINE)
    wf_match = re.search(r'^#\s+Workflow\b', remaining_content, re.MULTILINE)
    
    if wf_match:
        if desc_match:
            description = remaining_content[desc_match.end():wf_match.start()].strip()
        else:
            description = remaining_content[:wf_match.start()].strip()
        workflow_content = remaining_content[wf_match.end():].strip()
    else:
        if desc_match:
            description = remaining_content[desc_match.end():].strip()
        else:
            description = remaining_content.strip()
            
    # 3. Parse Steps
    # Look for ## Step <N>: <Title>
    # Note that <Title> can be optional or have spaces.
    step_pattern = re.compile(r'^##\s+Step\s+(\d+):\s*(.*?)\s*$', re.MULTILINE)
    
    # Find all steps
    step_headers = list(step_pattern.finditer(workflow_content))
    steps = []
    
    for idx, match in enumerate(step_headers):
        step_num = int(match.group(1))
        title = match.group(2).strip()
        
        start_idx = match.end()
        end_idx = step_headers[idx+1].start() if idx + 1 < len(step_headers) else len(workflow_content)
        
        instructions = workflow_content[start_idx:end_idx].strip()
        
        # Extract references
        ref_pattern = re.compile(r'`(skill|tool|schema|process)/([a-zA-Z0-9_\-]+)`')
        refs = []
        for ref_match in ref_pattern.finditer(instructions):
            ref_str = f"{ref_match.group(1)}/{ref_match.group(2)}"
            if ref_str not in refs:
                refs.append(ref_str)
                
        steps.append(WorkflowStep(
            index=step_num,
            title=title,
            instructions=instructions,
            references=refs
        ))
        
    return ProcessDocument(
        frontmatter=frontmatter,
        description=description,
        steps=steps
    )
