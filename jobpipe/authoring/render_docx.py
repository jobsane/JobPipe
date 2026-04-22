from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path


def render_cover_letter_docx(data: dict, output_path: Path) -> bytes:
    """Render a cover letter .docx by calling the Node.js script via subprocess.

    Args:
        data: JSON-serialisable dict with cover letter content.
              Expected keys (used by the JS script):
                recipientName (str), senderName (str), date (str),
                body (list[str]) - one string per paragraph
        output_path: destination path for the .docx file.

    Returns:
        Raw .docx bytes (also written to output_path).

    Raises:
        RuntimeError: if the Node.js script exits non-zero.
        FileNotFoundError: if node is not on PATH.
    """
    js_script = Path(__file__).parent / "_render_cover_letter.js"
    env = dict(os.environ)
    npm_cmd = shutil.which("npm") or shutil.which("npm.cmd")
    if npm_cmd:
        npm_root = subprocess.run(
            [npm_cmd, "root", "-g"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if npm_root.returncode == 0:
            existing_node_path = env.get("NODE_PATH", "")
            global_node_path = npm_root.stdout.strip()
            env["NODE_PATH"] = (
                global_node_path
                if not existing_node_path
                else f"{global_node_path}{os.pathsep}{existing_node_path}"
            )
    result = subprocess.run(
        ["node", str(js_script), str(output_path)],
        input=json.dumps(data).encode("utf-8"),
        capture_output=True,
        env=env,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Node.js render failed (exit {result.returncode}):\n"
            f"{result.stderr.decode('utf-8', errors='replace')}"
        )
    return Path(output_path).read_bytes()
