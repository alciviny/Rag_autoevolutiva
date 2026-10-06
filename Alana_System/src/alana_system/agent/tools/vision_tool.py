# c:\Users\JC INFO\Documents\Alana LLM\Alana_System\src\alana_system\agent\tools\vision_tool.py
import os
import logging
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from .base_tool import BaseTool
from .path_utils import safe_workspace_file

logger = logging.getLogger("alana.agent.tools.vision")

class VisionAnalysisTool(BaseTool):
    """
    O 'Olho de JARVIS': Permite que o agente analise imagens, diagramas e esquemáticos técnicos.
    Utiliza o processador multimodal industrial (Gemini 2.0 Flash).
    """
    def __init__(self, vision_processor):
        self.vision = vision_processor

    @property
    def name(self) -> str:
        return "analyze_visual_data"

    @property
    def description(self) -> str:
        return "Analisa imagens, diagramas ou esquemáticos técnicos. Suporta múltiplos arquivos (passar lista ou caminhos separados por vírgula)."

    async def execute(self, image_paths: Union[str, List[str]], prompt: str = "Analise tecnicamente esta imagem.") -> str:
        """
        Executa a analise visual de um ou mais arquivos.
        """
        paths = [p.strip() for p in image_paths.split(",")] if isinstance(image_paths, str) else image_paths
        
        valid_bytes = []
        for path in paths:
            try:
                _workspace, safe_path = safe_workspace_file(Path("data/uploads"), self.current_namespace, path)
            except (ValueError, PermissionError):
                logger.warning("Caminho de imagem fora do upload do namespace: %s", path)
                continue
            if safe_path.is_file():
                def _read(p):
                    with open(p, "rb") as f: return f.read()
                valid_bytes.append(await asyncio.to_thread(_read, safe_path))
            else:
                logger.warning(f"Arquivo não encontrado: {path}")

        if not valid_bytes:
            return "ERRO: Nenhum arquivo de imagem válido foi encontrado nos caminhos fornecidos."

        try:
            return await self.vision.analyze_image(valid_bytes, prompt)

        except Exception as e:
            logger.error(f"❌ Falha na analise de visao: {e}")
            return f"Nao consegui processar as imagens. Erro: {str(e)}"
