import os
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from ruamel.yaml import YAML

from pdt_cli.workspace import WorkspaceConfig
from pdt_cli.parser import ProcessDocument, WorkflowStep
from pdt_cli.resolver import resolve_reference
from pdt_cli.state import StateManager, RunState, StepState, ToolCallRecord
from pdt_cli.adapter import LLMAdapter, CLIDelegatorAdapter, GeminiAdapter, OpenAIAdapter, CompletionResponse

def step_requires_approval(step: WorkflowStep) -> bool:
    content = (step.title + " " + step.instructions).lower()
    return "approval" in content or "approve" in content or "gate" in content or "confirm" in content or "review" in content

class ExecutionEngine:
    def __init__(self, workspace_root: Path, config: WorkspaceConfig, process_doc: ProcessDocument, run_id: Optional[str] = None):
        self.workspace_root = workspace_root
        self.config = config
        self.process_doc = process_doc
        self.state_manager = StateManager(workspace_root, run_id=run_id)

    def execute(self, inputs: Dict[str, str], target_step: Optional[int] = None, resume: bool = False, approval_input: Optional[str] = None) -> RunState:
        # Load or initialize state
        if resume:
            state = self.state_manager.load_state()
            state.status = "running"
            self.state_manager.save_state(state)
            
            # Register approval output if we were waiting for approval
            if state.steps:
                current_step_idx = state.current_step_index
                for s in state.steps:
                    if s.index == current_step_idx and s.status == "waiting_for_approval":
                        s.status = "completed"
                        s.end_time = datetime.now(timezone.utc)
                        s.output = approval_input or "Approved by user."
                        state.current_step_index += 1
                        self.state_manager.save_state(state)
                        self.state_manager.log_system(f"Step {current_step_idx} approved and marked completed.")
                        break
        else:
            # Check if state already exists for this run_id (if explicit run_id was provided)
            try:
                state = self.state_manager.load_state()
            except FileNotFoundError:
                # Initialize new run
                step_states = []
                for step in self.process_doc.steps:
                    step_states.append(StepState(
                        index=step.index,
                        title=step.title,
                        status="pending"
                    ))
                state = self.state_manager.initialize_run(
                    process_id=self.process_doc.frontmatter.id,
                    version=self.process_doc.frontmatter.version,
                    inputs=inputs,
                    steps=step_states
                )

        # Main step execution loop
        while state.current_step_index <= len(state.steps):
            step_idx = state.current_step_index
            
            # If target_step is specified and we are targeting a single step, check it
            if target_step is not None and step_idx != target_step:
                # If we've already done the target step or are not there yet, jump or break
                # Let's say if we target a single step, we only run that step and then break.
                if step_idx < target_step:
                    # Skip to the target step
                    state.current_step_index = target_step
                    self.state_manager.save_state(state)
                    continue
                else:
                    # We are past the target step
                    break

            step_state = state.steps[step_idx - 1]
            step_doc = self.process_doc.steps[step_idx - 1]

            self.state_manager.log_system(f"Starting execution of Step {step_idx}: {step_state.title}")
            step_state.status = "running"
            step_state.start_time = datetime.now(timezone.utc)
            self.state_manager.save_state(state)

            # Resolve references for the active step
            resolved_skills = []
            resolved_tools = []
            resolved_schemas = []

            for ref in step_doc.references:
                try:
                    abs_path = resolve_reference(ref, self.workspace_root, self.config)
                    if ref.startswith("skill/"):
                        with open(abs_path, 'r') as f:
                            resolved_skills.append((ref, f.read()))
                    elif ref.startswith("tool/"):
                        yaml = YAML(typ='safe')
                        with open(abs_path, 'r') as f:
                            tool_data = yaml.load(f) or {}
                        resolved_tools.append((ref, tool_data, abs_path.parent))
                    elif ref.startswith("schema/"):
                        with open(abs_path, 'r') as f:
                            resolved_schemas.append((ref, f.read()))
                except Exception as e:
                    self.state_manager.log_system(f"Error resolving reference {ref}: {e}")
                    step_state.status = "failed"
                    step_state.end_time = datetime.now(timezone.utc)
                    state.status = "failed"
                    self.state_manager.save_state(state)
                    raise

            # Synthesize system prompt and bounded prompt
            system_prompt = (
                "You are an operational assistant executing a step-by-step Standard Operating Procedure (SOP).\n"
                "Your actions must strictly adhere to the global boundaries and rules specified in the Process Description."
            )

            # Completed steps info
            completed_info = ""
            for s in state.steps[:step_idx - 1]:
                completed_info += f"Step {s.index}: {s.title} ({s.status})\nOutput: {s.output}\n\n"
            if not completed_info:
                completed_info = "None (this is the first step).\n"

            # Referenced skills text
            skills_text = ""
            for ref, content in resolved_skills:
                skills_text += f"Skill: {ref}\n---\n{content}\n\n"
            if not skills_text:
                skills_text = "None\n"

            # Referenced tools text
            tools_text = ""
            tools_list_for_adapter = []
            for ref, tool_data, tool_dir in resolved_tools:
                tools_text += f"Tool: {ref}\nDescription: {tool_data.get('description', '')}\nParameters Schema: {json.dumps(tool_data.get('parameters', {}))}\n\n"
                tools_list_for_adapter.append({
                    "name": tool_data.get("name") or ref.split('/')[-1],
                    "description": tool_data.get("description", ""),
                    "parameters": tool_data.get("parameters")
                })
            if not tools_text:
                tools_text = "None\n"

            # Referenced schemas text
            schemas_text = ""
            for ref, content in resolved_schemas:
                schemas_text += f"Schema: {ref}\n---\n{content}\n\n"
            if not schemas_text:
                schemas_text = "None\n"

            prompt = (
                f"[PROCESS DESCRIPTION CONTEXT]\n"
                f"Id: {self.process_doc.frontmatter.id}\n"
                f"Owner: {self.process_doc.frontmatter.owner}\n"
                f"Description:\n{self.process_doc.description}\n\n"
                f"[EXECUTION STATE]\n"
                f"The following steps have already completed:\n{completed_info}\n"
                f"[ACTIVE STEP TO EXECUTE]\n"
                f"Step Index: {step_doc.index}\n"
                f"Step Title: {step_doc.title}\n"
                f"Instructions:\n{step_doc.instructions}\n\n"
                f"[AVAILABLE CAPABILITIES]\n"
                f"Referenced Skills:\n{skills_text}\n"
                f"Referenced Tools:\n{tools_text}\n"
                f"Referenced JSON Schemas:\n{schemas_text}\n"
                f"INSTRUCTIONS:\n"
                f"Examine the active step. Invoke available tools to retrieve data or execute calculations.\n"
                f"Produce an output detailing the result, and save relevant outputs.\n"
                f"When finished, output your summary."
            )

            # Get adapter
            adapter = self.get_llm_adapter()

            self.state_manager.log_system("Sending prompt to LLM adapter...")
            response = adapter.complete(prompt, system_instruction=system_prompt, tools=tools_list_for_adapter)
            self.state_manager.log_llm(prompt, response.text or str(response.tool_calls))

            # Handle tool calls in a loop
            while response.tool_calls:
                for tc in response.tool_calls:
                    # Find tool definition
                    tool_ref = f"tool/{tc.name}"
                    tool_def = None
                    tool_dir = None
                    for ref, tool_data, t_dir in resolved_tools:
                        if ref == tool_ref or tool_data.get("name") == tc.name:
                            tool_def = tool_data
                            tool_dir = t_dir
                            break

                    if not tool_def:
                        result_str = f"Error: Tool {tc.name} is not available or referenced in this step."
                        self.state_manager.log_system(result_str)
                    else:
                        self.state_manager.log_system(f"Executing tool '{tc.name}' locally with args: {tc.arguments}")
                        
                        record = ToolCallRecord(
                            tool_id=tc.name,
                            arguments=tc.arguments
                        )
                        step_state.tool_calls.append(record)
                        self.state_manager.save_state(state)

                        try:
                            # Run tool
                            result_str = self.execute_local_tool(tool_def, tool_dir, tc.arguments)
                            
                            # Save evidence
                            evidence_filename = f"step{step_idx}_tool_{tc.name}_{uuid.uuid4().hex[:4]}.json"
                            evidence_rel_path = self.state_manager.save_evidence(evidence_filename, result_str)
                            record.output_file = str(evidence_rel_path)
                            self.state_manager.save_state(state)
                        except Exception as e:
                            result_str = f"Error executing tool {tc.name}: {e}"
                            self.state_manager.log_system(result_str)

                    # Append tool call result back to prompt history
                    prompt += f"\n\n[TOOL CALL RESULT]\nTool: {tc.name}\nResult:\n{result_str}"

                # Query LLM again with results
                self.state_manager.log_system("Sending tool results back to LLM adapter...")
                response = adapter.complete(prompt, system_instruction=system_prompt, tools=tools_list_for_adapter)
                self.state_manager.log_llm(prompt, response.text or str(response.tool_calls))

            # Once LLM completes step execution
            step_state.output = response.text
            
            # Check if approval is required
            if step_requires_approval(step_doc):
                step_state.status = "waiting_for_approval"
                state.status = "waiting_for_approval"
                self.state_manager.log_system(f"Step {step_idx} completed but requires human approval/gate.")
                self.state_manager.save_state(state)
                break

            step_state.status = "completed"
            step_state.end_time = datetime.now(timezone.utc)
            self.state_manager.log_system(f"Step {step_idx} completed successfully.")
            
            state.current_step_index += 1
            self.state_manager.save_state(state)

            if target_step is not None and step_idx == target_step:
                break

        # Finalize run status
        if state.current_step_index > len(state.steps):
            state.status = "completed"
            state.end_time = datetime.now(timezone.utc)
            self.state_manager.save_state(state)
            self.state_manager.log_system("Workflow execution completed successfully.")

        return state

    def execute_local_tool(self, tool_def: Dict[str, Any], tool_dir: Path, arguments: Dict[str, Any]) -> str:
        entrypoint = tool_def.get("entrypoint", "main.py")
        
        # Build cmd
        if entrypoint.endswith(".py") and "python" not in entrypoint:
            cmd = ["python", entrypoint]
        elif entrypoint.endswith(".js") and "node" not in entrypoint:
            cmd = ["node", entrypoint]
        else:
            cmd = entrypoint.split()

        # Workspace environment
        env = os.environ.copy()
        if self.config.deploy and self.config.deploy.env:
            for k, v in self.config.deploy.env.items():
                env[k] = v

        env["PDT_TOOL_ARGS"] = json.dumps(arguments)

        res = subprocess.run(
            cmd,
            cwd=tool_dir,
            input=json.dumps(arguments),
            capture_output=True,
            text=True,
            env=env
        )

        if res.returncode != 0:
            raise RuntimeError(f"Tool process exited with non-zero code {res.returncode}. Stderr: {res.stderr}")

        return res.stdout

    def get_llm_adapter(self) -> LLMAdapter:
        provider = self.config.llm.provider
        model = self.config.llm.model

        if provider == "cli":
            if not self.config.llm.cli:
                raise ValueError("LLM provider is set to 'cli', but 'llm.cli' is not configured in pdt.yaml")
            return CLIDelegatorAdapter(
                command=self.config.llm.cli.command,
                args=self.config.llm.cli.args
            )
        elif provider == "gemini":
            return GeminiAdapter(model=model)
        elif provider == "openai":
            return OpenAIAdapter(model=model)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")
