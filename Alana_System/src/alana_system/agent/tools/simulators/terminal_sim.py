import subprocess
from pathlib import Path
from ..base_tool import BaseTool

import shlex

class TerminalSimulatorTool(BaseTool):
    name = "run_terminal_simulator"
    description = "Executa um simulador CLI estritamente seguro e isolado (ex: python, gcc, ngspice, wokwi). Argumento: 'command' (str)"
    
    # Lista restrita de binários permitidos para evitar RCE
    ALLOWED_BINARIES = {"python", "gcc", "g++", "ngspice", "wokwi-cli", "make", "echo"}
    
    def __init__(self, workspace_path: str = "workspace"):
        self.workspace = Path(workspace_path)
        
    def execute(self, command: str) -> str:
        # Isolamento de projeto industrial
        safe_workspace = self.workspace / self.current_namespace
        safe_workspace.mkdir(parents=True, exist_ok=True)
        
        try:
            # Sanitização contra Injeção de Shell (Evita pipelines maliciosos: "gcc test.c; rm -rf /")
            args = shlex.split(command)
            if not args:
                return "[FALHA CRÍTICA] Comando vazio."
                
            base_bin = args[0]
            if base_bin not in self.ALLOWED_BINARIES:
                return f"[BLOQUEIO DE SEGURANÇA] O binário '{base_bin}' não está na whitelist autorizada de simuladores. Solicite a criação de uma ferramenta própria se necessário."
            
            # shell=False garante que metacaracteres (>, <, |, ;) não sejam avaliados
            result = subprocess.run(
                args,
                cwd=safe_workspace,
                shell=False,
                capture_output=True,
                text=True,
                timeout=45 
            )
            
            output = result.stdout
            error = result.stderr
            
            if result.returncode == 0:
                return f"[SIMULAÇÃO FINALIZADA]\nLogs:\n{output}"
            else:
                return f"[FALHA NA SIMULAÇÃO]\nLogs:\n{output}\nErros:\n{error}"
                
        except subprocess.TimeoutExpired:
            return "[FALHA CRÍTICA] A simulação excedeu o tempo máximo de 45 segundos."
        except Exception as e:
            return f"[ERRO DO SISTEMA] {str(e)}"
