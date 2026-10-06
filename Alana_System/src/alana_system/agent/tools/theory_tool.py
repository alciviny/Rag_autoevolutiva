import logging
import asyncio
import uuid
from .base_tool import BaseTool
from .code_runners.python_runner import PythonRunnerTool
from .file_system import WriteCodeTool

logger = logging.getLogger(__name__)

class TheoryValidationTool(BaseTool):
    name = "validate_theory"
    description = (
        "Protocolo Científico Sênior. Valida uma teoria técnica através de simulação e confronto de dados. "
        "Argumentos: 'theory' (str), 'simulation_code' (str)."
    )
    
    def __init__(self):
        # Usa as ferramentas existentes como sub-componentes (Composição)
        self.writer = WriteCodeTool()
        self.runner = PythonRunnerTool()
        
    async def execute(self, theory: str, simulation_code: str) -> str:
        """
        Executa o ciclo: Hipótese -> Experimento -> Verificação.
        """
        experiment_id = str(uuid.uuid4())[:8]
        filename = f"experiment_{experiment_id}.py"
        self.writer.set_context(self.current_namespace)
        self.runner.set_context(self.current_namespace)
        
        logger.info(f"🔬 Alana iniciando validação de teoria (Exp: {experiment_id}): {theory[:50]}...")
        
        # 2. Escreve o código
        write_res = await self.writer.execute(filename, simulation_code)
        if "[ERRO]" in write_res:
            return write_res
            
        # 3. Executa a simulação
        run_res = await self.runner.execute(filename)
        
        # 4. Sintetiza o relatório científico
        report = (
            f"--- PROTOCOLO DE VALIDAÇÃO CIENTÍFICA ---\n"
            f"TEORIA ANALISADA: {theory}\n\n"
            f"RESULTADO DO EXPERIMENTO:\n{run_res}\n\n"
            f"VEREDITO: Analise os dados acima e confirme se a teoria se sustenta ou se há anomalias."
        )
        
        return report
