"""OpenAI-compatible HTTP client. Works with Ollama, OpenRouter, Anthropic proxy."""
from __future__ import annotations

import json
import re
from typing import Optional
from urllib import request as urllib_request

from workflow_kit.runtime.config import LLMConfig


def call_llm(prompt: str, cfg: LLMConfig, system: str = "") -> Optional[str]:
    """Send prompt to one LLM endpoint, return response text or None on failure."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = json.dumps({
        "model": cfg.model,
        "messages": messages,
        "temperature": 0.2,
    }).encode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.api_key}",
    }
    try:
        req = urllib_request.Request(
            cfg.endpoint, data=payload, headers=headers, method="POST"
        )
        with urllib_request.urlopen(req, timeout=cfg.timeout) as resp:
            body = json.loads(resp.read().decode())
        return body["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[worker] LLM call failed ({cfg.model}): {e}")
        return None


def call_llm_with_fallback(
    prompt: str,
    cfgs: list[LLMConfig],
    system: str = "",
) -> Optional[str]:
    """Try each LLM config in order; return the first successful response.

    Logs which model is called and when falling back occurs.  Returns None
    only if every config in the list fails.

    Args:
        prompt:  User prompt.
        cfgs:    Ordered list of LLMConfig.  Index 0 is primary; subsequent
                 entries are fallbacks.
        system:  Optional system message.
    """
    for i, cfg in enumerate(cfgs):
        label = "primary" if i == 0 else f"fallback-{i}"
        print(f"[worker] Calling {cfg.model} ({label})...")
        result = call_llm(prompt, cfg, system)
        if result is not None:
            return result
        if i < len(cfgs) - 1:
            print(f"[worker] Falling back to {cfgs[i + 1].model}...")
    return None


def parse_file_blocks(response: str) -> dict[str, str]:
    """Parse LLM response into {filename: code} mapping.

    Handles:
    - **path/to/file.py**\\n```lang\\ncode\\n```
    - ```lang:path/to/file.py\\ncode\\n```
    """
    result: dict[str, str] = {}

    # Pattern 1: **filename**\n```lang\ncode```
    for m in re.finditer(r"\*\*(.+?)\*\*\s*\n```\w*\n(.*?)```", response, re.DOTALL):
        fname, code = m.group(1).strip(), m.group(2).strip()
        if fname and code:
            result[fname] = code

    # Pattern 2: ```lang:filename\ncode```
    for m in re.finditer(r"```(?:\w+)?:(.+?)\n(.*?)```", response, re.DOTALL):
        fname, code = m.group(1).strip(), m.group(2).strip()
        if fname and code and fname not in result:
            result[fname] = code

    return result
