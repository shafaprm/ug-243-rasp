import json
from typing import Any, Dict

def dumps_line(obj: Dict[str, Any]) -> bytes:
    # JSON compact + newline delimiter
    return (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")

def loads_line(line: str) -> Dict[str, Any]:
    return json.loads(line)
