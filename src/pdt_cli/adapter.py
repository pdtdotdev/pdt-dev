import os
import json
import re
import tempfile
import subprocess
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ToolCall(BaseModel):
    call_id: str
    name: str
    arguments: Dict[str, Any]

class CompletionResponse(BaseModel):
    text: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)

class LLMAdapter(ABC):
    @abstractmethod
    def complete(self, prompt: str, system_instruction: str = None, tools: Optional[List[Dict[str, Any]]] = None) -> CompletionResponse:
        """Sends a prompt to the model and returns a structured response."""
        pass

class CLIDelegatorAdapter(LLMAdapter):
    def __init__(self, command: str, args: List[str]):
        self.command = command
        self.args = args

    def complete(self, prompt: str, system_instruction: str = None, tools: Optional[List[Dict[str, Any]]] = None) -> CompletionResponse:
        full_system = system_instruction or ""
        if tools:
            tools_instruction = (
                "\n\nYou have access to the following tools:\n"
                + json.dumps(tools, indent=2)
                + "\nTo call a tool, you MUST output a JSON object with a single top-level key 'tool_call', like this:\n"
                + '{"tool_call": {"name": "tool_name", "arguments": {"arg1": "val1"}}}'
                + "\nDo not output any other text when calling a tool."
            )
            full_system += tools_instruction

        full_prompt = f"{full_system}\n\n{prompt}" if full_system else prompt

        with tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".txt") as temp:
            temp.write(full_prompt)
            temp_path = temp.name

        resolved_args = [arg.replace("{prompt_file}", temp_path) for arg in self.args]

        try:
            result = subprocess.run(
                [self.command] + resolved_args,
                capture_output=True,
                text=True,
                check=True
            )
            output = result.stdout.strip()

            tool_calls = []
            # Try to parse entire output as JSON
            try:
                data = json.loads(output)
                if "tool_call" in data:
                    tc = data["tool_call"]
                    tool_calls.append(ToolCall(
                        call_id=uuid.uuid4().hex[:8],
                        name=tc["name"],
                        arguments=tc.get("arguments") or {}
                    ))
                    output = None
            except Exception:
                # Try finding JSON block in the output
                json_match = re.search(r'\{\s*"tool_call"\s*:\s*\{.*?\}\s*\}', output, re.DOTALL)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                        tc = data["tool_call"]
                        tool_calls.append(ToolCall(
                            call_id=uuid.uuid4().hex[:8],
                            name=tc["name"],
                            arguments=tc.get("arguments") or {}
                        ))
                        output = output.replace(json_match.group(0), "").strip()
                    except Exception:
                        pass

            return CompletionResponse(
                text=output if (output and output.strip()) else None,
                tool_calls=tool_calls
            )
        finally:
            os.unlink(temp_path)

class GeminiAdapter(LLMAdapter):
    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model
        # Import dynamically to avoid strict dependency loading issues
        from google import genai
        self.client = genai.Client()

    def complete(self, prompt: str, system_instruction: str = None, tools: Optional[List[Dict[str, Any]]] = None) -> CompletionResponse:
        from google.genai import types
        
        config_args = {}
        if system_instruction:
            config_args["system_instruction"] = system_instruction

        if tools:
            gemini_tools = []
            for t in tools:
                fd = types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=t.get("parameters")
                )
                gemini_tools.append(types.Tool(function_declarations=[fd]))
            config_args["tools"] = gemini_tools

        config = types.GenerateContentConfig(**config_args)

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config
        )

        tool_calls = []
        if response.function_calls:
            for fc in response.function_calls:
                tool_calls.append(ToolCall(
                    call_id=uuid.uuid4().hex[:8],
                    name=fc.name,
                    arguments=fc.args
                ))

        return CompletionResponse(
            text=response.text,
            tool_calls=tool_calls
        )

class OpenAIAdapter(LLMAdapter):
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.api_key = os.getenv("OPENAI_API_KEY")

    def complete(self, prompt: str, system_instruction: str = None, tools: Optional[List[Dict[str, Any]]] = None) -> CompletionResponse:
        import requests
        
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages
        }

        if tools:
            openai_tools = []
            for t in tools:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t.get("parameters") or {"type": "object", "properties": {}}
                    }
                })
            payload["tools"] = openai_tools

        response = requests.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        resp_json = response.json()

        message = resp_json["choices"][0]["message"]
        text = message.get("content")

        tool_calls = []
        if "tool_calls" in message:
            for tc in message["tool_calls"]:
                if tc["type"] == "function":
                    func = tc["function"]
                    try:
                        args = json.loads(func["arguments"])
                    except Exception:
                        args = {}
                    tool_calls.append(ToolCall(
                        call_id=tc["id"],
                        name=func["name"],
                        arguments=args
                    ))

        return CompletionResponse(
            text=text,
            tool_calls=tool_calls
        )
