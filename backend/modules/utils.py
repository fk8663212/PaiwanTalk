import json
import re
from typing import Optional, Tuple

def extract_structured(text: str) -> Tuple[str, Optional[str]]:
    """
    Best-effort extraction of reply/thinking fields from LLM output.
    Handles Markdown code blocks, partial JSON, and regex fallback.
    """
    clean_content = text.strip()

    # Remove ```json ... ``` or ``` ... ``` wrappers
    if clean_content.startswith("```"):
        # Find the first newline to skip the language identifier (e.g., ```json)
        first_newline = clean_content.find("\n")
        if first_newline != -1:
            # Check if it ends with ```
            if clean_content.endswith("```"):
                clean_content = clean_content[first_newline+1:-3].strip()
            else:
                # Maybe it didn't close properly, just take from newline
                clean_content = clean_content[first_newline+1:].strip()

    # Helper to try parsing JSON
    def try_parse_json(candidate: str):
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return (
                    str(parsed.get("reply") or "").strip(),
                    str(parsed.get("thinking") or "").strip(),
                )
        except json.JSONDecodeError:
            pass
        return None

    # 1) Try parsing the cleaned content directly
    result = try_parse_json(clean_content)
    if result:
        return result[0] or text, result[1] or None

    # 2) Try to find the last JSON object {...}
    if "{" in clean_content and "}" in clean_content:
        last_open = clean_content.rfind("{")
        last_close = clean_content.rfind("}")
        if last_close > last_open:
            maybe_json = clean_content[last_open : last_close + 1]
            result = try_parse_json(maybe_json)
            if result:
                return result[0] or text, result[1] or None

    # 3) Regex fallback
    # This is a bit fragile for nested quotes but works for simple cases
    reply_match = re.search(r'"reply"\s*:\s*"([^"]+)"', clean_content)
    thinking_match = re.search(r'"thinking"\s*:\s*"([^"]+)"', clean_content)
    
    if reply_match:
        reply_val = reply_match.group(1)
        thinking_val = thinking_match.group(1) if thinking_match else None
        return reply_val, thinking_val

    # Fallback: return original text as reply
    return text, None
