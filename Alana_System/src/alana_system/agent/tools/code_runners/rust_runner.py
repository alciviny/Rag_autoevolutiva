import os
import uuid
import asyncio
import logging
from pathlib import Path
from ..base_tool import BaseTool
from ..path_utils import safe_workspace_file, unsandboxed_code_execution_enabled

logger = logging.getLogger(__name__)

class RustRunnerTool(BaseTool):
    name = "rust_runner"
    description = "Compila e executa um arquivo Rust (.rs) salvo no sandbox. Argumento: 'filename' (str)"
    
    def __init__(self, workspace_path: str = "data/sandbox"):
        self.workspace = Path(workspace_path)
        
    async def execute(self, filename: str) -> str:
        if not unsandboxed_code_execution_enabled():
            return "[BLOQUEADO] Execução direta de código está desativada até configurar um worker isolado."
        try:
            workspace, file_path = safe_workspace_file(self.workspace, self.current_namespace, filename)
        except (ValueError, PermissionError) as exc:
            return f"[BLOQUEIO DE CAMINHO] {exc}"
        if file_path.suffix != ".rs":
            return "[ERRO] Esperado um arquivo Rust (.rs)."
        if not file_path.exists():
            return f"[ERRO] O arquivo {filename} não existe no sandbox do projeto {self.current_namespace}."
            
        executable_name = file_path.stem
        executable_path = workspace / executable_name
        
        # O Windows gera .exe, o Linux não
        if os.name == 'nt':
            executable_path = workspace / f"{executable_name}.exe"
            
        try:
            # 1. Compilação
            compile_process = await asyncio.create_subprocess_exec(
                "rustc", str(file_path.absolute()),
                cwd=str(workspace.absolute()),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            c_stdout, c_stderr = await compile_process.communicate()
            if compile_process.returncode != 0:
                error_msg = c_stderr.decode()
                with open(file_path, "r", encoding="utf-8") as f:
                    code = f.read()
                return f"[ERRO DE COMPILAÇÃO RUST]\nCÓDIGO:\n{code}\n\nERRO DO COMPILADOR (Borrow Checker / Sintaxe):\n{error_msg}\n\nDICA: O compilador do Rust é rígido. Leia o erro acima para entender onde as regras de memória ou sintaxe foram violadas e reescreva o arquivo."

            # 2. Execução
            run_process = await asyncio.create_subprocess_exec(
                str(executable_path.absolute()),
                cwd=str(workspace.absolute()),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            try:
                r_stdout, r_stderr = await asyncio.wait_for(run_process.communicate(), timeout=30)
                output = r_stdout.decode()
                error = r_stderr.decode()
                returncode = run_process.returncode
            except asyncio.TimeoutError:
                run_process.kill()
                return "[FALHA CRÍTICA] Timeout de 30s atingido ao rodar o binário Rust."
            
            with open(file_path, "r", encoding="utf-8") as f:
                executed_code = f.read()

            if returncode == 0:
                return f"[EXECUÇÃO COM SUCESSO]\nCÓDIGO EXECUTADO:\n{executed_code}\n\nSAÍDA:\n{output}\n"
            else:
                return f"[FALHA NA EXECUÇÃO (RUNTIME)]\nCÓDIGO EXECUTADO:\n{executed_code}\n\nSAÍDA:\n{output}\nERROS (Panic):\n{error}"
                
        except Exception as e:
            return f"[ERRO DO SISTEMA RUST] {str(e)}\nTalvez o 'rustc' não esteja instalado no sistema hospedeiro ou no PATH."
