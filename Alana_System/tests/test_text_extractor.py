from unittest.mock import MagicMock, patch
from pathlib import Path

from alana_system.ingestion.text_extractor import TextExtractor, PageText


def test_text_extraction():
    # Mock do fitz.open para não depender de arquivo físico
    with patch("fitz.open") as mock_open:
        # Mock de uma página
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Texto de exemplo da página 1"
        
        # Mock do objeto documento retornado por fitz.open
        mock_doc = MagicMock()
        mock_doc.__iter__.return_value = [mock_page]
        mock_doc.__enter__.return_value = mock_doc
        
        mock_open.return_value = mock_doc
        
        pdf_path = Path("data/raw/exemplo.pdf")
        extractor = TextExtractor()

        pages = extractor.extract_text(pdf_path)

        assert isinstance(pages, list)
        assert len(pages) == 1
        
        page = pages[0]
        assert isinstance(page, PageText)
        assert page.page_number == 1
        assert page.text == "Texto de exemplo da página 1"
        assert page.char_count == len("Texto de exemplo da página 1")
