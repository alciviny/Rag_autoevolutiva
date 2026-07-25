import logging
import json
from dataclasses import dataclass
from typing import List

from .text_extractor import PageText
from ..core.binary_bridge import BinaryBridge

logger = logging.getLogger("alana.ingestion.cleaner")

@dataclass(frozen=True)
class CleanedPageText:
    page_number: int
    text: str
    original_char_count: int
    cleaned_char_count: int

class TextCleaner:
    """
    Limpador de texto de alta performance usando o motor Go via BinaryBridge.
    """

    def __init__(self):
        self.bridge = BinaryBridge("fast_processor.exe")

    def clean_pages(self, pages: List[PageText]) -> List[CleanedPageText]:
        if not pages:
            return []

        # Agrupa todas as páginas em uma única requisição para o Go
        pages_dict = {str(page.page_number): page.text for page in pages}
        
        try:
            # Chama a ponte Go uma única vez
            results = self.bridge.call({"pages": pages_dict})
            
            # Mapeia os resultados da resposta da ponte Go (lista de dicts)
            cleaned_map = {}
            if isinstance(results, list):
                for res in results:
                    p_num = int(res.get("page_number", 0))
                    cleaned_map[p_num] = res.get("text", "")
            
            cleaned_pages = []
            for page in pages:
                cleaned_text = cleaned_map.get(page.page_number, page.text)
                cleaned_pages.append(CleanedPageText(
                    page_number=page.page_number,
                    text=cleaned_text,
                    original_char_count=len(page.text),
                    cleaned_char_count=len(cleaned_text)
                ))
            return cleaned_pages
        except Exception as e:
            logger.warning(f"Falha na limpeza em lote via Go. Mantendo originais. Erro: {e}")
            return [
                CleanedPageText(
                    page_number=page.page_number,
                    text=page.text,
                    original_char_count=len(page.text),
                    cleaned_char_count=len(page.text)
                ) for page in pages
            ]
