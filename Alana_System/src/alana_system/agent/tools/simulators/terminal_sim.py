import asyncio
from pathlib import Path
from ..base_tool import BaseTool
from ..path_utils import namespace_workspace


class TerminalSimulatorTool(BaseTool):
    name = "run_terminal_simulator"
    description = "Executa o comando de saída seguro 'echo' dentro do workspace atual. Para código, use as ferramentas de execução dedicadas. Argumento: 'command' (str)"
    
    # Lista restrita de binários permitidos para evitar RCE
    ALLOWED_BINARIES = {"echo"}
    
    def __init__(self, workspace_path: str = "workspace"):
        self.workspace = Path(workspace_path)
        
    async def execute(self, command: str) -> str:
        try:
            safe_workspace = namespace_workspace(self.workspace, self.current_namespace)
            args = command.split()
            if not args:
                return "[FALHA CRÍTICA] Comando vazio."
                
            base_bin = args[0]
            if base_bin not in self.ALLOWED_BINARIES:
                return f"[BLOQUEIO DE SEGURANÇA] O binário '{base_bin}' não está na whitelist autorizada de simuladores. Solicite a criação de uma ferramenta própria se necessário."
            
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(safe_workspace),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5)
            output, error = stdout.decode(errors="replace"), stderr.decode(errors="replace")
            
            if process.returncode == 0:
                return f"[SIMULAÇÃO FINALIZADA]\nLogs:\n{output}"
            else:
                return f"[FALHA NA SIMULAÇÃO]\nLogs:\n{output}\nErros:\n{error}"
                
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return "[FALHA CRÍTICA] O comando excedeu o limite de 5 segundos."
        except (ValueError, PermissionError) as e:
            return f"[BLOQUEIO DE CAMINHO] {e}"
        except Exception as e:
            return f"[ERRO DO SISTEMA] {str(e)}"
