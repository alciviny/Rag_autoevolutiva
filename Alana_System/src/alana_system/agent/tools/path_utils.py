import re
import os
from pathlib import Path


def namespace_workspace(root: Path, namespace: str) -> Path:
    if not isinstance(namespace, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", namespace):
        raise ValueError("Namespace inválido.")
    root = root.resolve()
    workspace = (root / namespace).resolve()
    if not workspace.is_relative_to(root):
        raise PermissionError("Workspace fora do diretório permitido.")
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def safe_workspace_file(root: Path, namespace: str, filename: str) -> tuple[Path, Path]:
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("Nome de arquivo inválido.")
    workspace = namespace_workspace(root, namespace)
    target = (workspace / filename).resolve()
    if not target.is_relative_to(workspace):
        raise PermissionError("Acesso negado fora do workspace.")
    return workspace, target


def unsandboxed_code_execution_enabled() -> bool:
    """Code runners stay disabled until an isolated worker is configured."""
    return os.getenv("ALANA_ENABLE_UNSANDBOXED_CODE_EXECUTION", "false").lower() == "true"
