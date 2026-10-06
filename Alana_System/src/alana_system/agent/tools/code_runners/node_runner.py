import os
import uuid
import asyncio
import logging
from pathlib import Path
from ..base_tool import BaseTool
from ..path_utils import safe_workspace_file, unsandboxed_code_execution_enabled

logger = logging.getLogger(__name__)

class NodeRunnerTool(BaseTool):
    name = "node_runner"
    description = "Executa um arquivo JavaScript/TypeScript (Node.js) salvo no sandbox. Argumento: 'filename' (str)"
    
    def __init__(self, workspace_path: str = "data/sandbox"):
        self.workspace = Path(workspace_path)
        
    async def execute(self, filename: str) -> str:
        if not unsandboxed_code_execution_enabled():
            return "[BLOQUEADO] Execução direta de código está desativada até configurar um worker isolado."
        try:
            workspace, file_path = safe_workspace_file(self.workspace, self.current_namespace, filename)
        except (ValueError, PermissionError) as exc:
            return f"[BLOQUEIO DE CAMINHO] {exc}"
        if not file_path.exists():
            return f"[ERRO] O arquivo {filename} não existe no sandbox do projeto {self.current_namespace}."
            
        try:
            # Executa o código de forma assíncrona usando o Node.js
            process = await asyncio.create_subprocess_exec(
                "node", str(file_path.absolute()),
                cwd=str(workspace.absolute()),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=45)
                output = stdout.decode()
                error = stderr.decode()
                returncode = process.returncode
            except asyncio.TimeoutError:
                process.kill()
                return "[FALHA CRÍTICA] Timeout de 45s atingido no Node.js."
            
            with open(file_path, "r", encoding="utf-8") as f:
                executed_code = f.read()

            if returncode == 0:
                return f"[EXECUÇÃO COM SUCESSO]\nCÓDIGO EXECUTADO:\n{executed_code}\n\nSAÍDA:\n{output}\n"
            else:
                return f"[FALHA NA EXECUÇÃO]\nCÓDIGO EXECUTADO:\n{executed_code}\n\nSAÍDA:\n{output}\nERROS (Stack Trace):\n{error}\n\nDICA: Leia o Stack Trace acima para encontrar o erro de sintaxe ou lógica e corrija o arquivo usando a ferramenta correspondente."
                
        except Exception as e:
            return f"[ERRO DO SISTEMA NODE.JS] {str(e)}\nTalvez o Node.js não esteja instalado no sistema hospedeiro."
