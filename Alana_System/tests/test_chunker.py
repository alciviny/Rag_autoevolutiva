"""
tests/test_chunker.py

Testes para a lógica de chunking semântico.
"""
import pytest
from alana_system.preprocessing.chunker import TextChunker
from alana_system.ingestion.cleaner import CleanedPageText

# ============================================================
# Fixtures
# ============================================================

from unittest.mock import patch, MagicMock

@pytest.fixture
def chunker():
    """Retorna uma instância do TextChunker com parâmetros padrão para teste."""
    return TextChunker(max_chars=100, overlap_chars=30, min_chars=20)

@pytest.fixture
def single_page():
    """Retorna uma página de texto limpo para os testes."""
    text = (
        "Primeiro parágrafo do texto. Ele é curto e direto.\n\n"
        "Segundo parágrafo é um pouco mais longo, com mais detalhes. "
        "Ele serve para testar a junção de parágrafos em um único chunk.\n\n"
        "Terceiro. Curto.\n\n"
        "Quarto parágrafo é deliberadamente muito, muito, muito longo para exceder o limite "
        "de caracteres de cem, forçando o chunker a tratá-lo como um caso especial e isolado."
    )
    return CleanedPageText(
        page_number=1,
        text=text,
        original_char_count=len(text),
        cleaned_char_count=len(text),
    )

# ============================================================
# Test Cases
# ============================================================

@patch("alana_system.preprocessing.chunker.BinaryBridge")
def test_chunking_normal(mock_bridge, chunker, single_page):
    """
    Testa o fluxo normal de chunking com a ponte.
    """
    mock_bridge_instance = MagicMock()
    # Simula o retorno de 4 chunks do Go
    mock_bridge_instance.call.return_value = [
        {"content": "Primeiro parágrafo do texto. Ele é curto e direto."},
        {"content": "Segundo parágrafo é um pouco mais longo, com mais detalhes."},
        {"content": "Terceiro. Curto."}, # será filtrado pois len < min_chars (16 < 20)
        {"content": "Quarto parágrafo é deliberadamente muito, muito, muito longo para exceder o limite de caracteres de cem, forçando o chunker a tratá-lo como um caso especial e isolado."}
    ]
    mock_bridge.return_value = mock_bridge_instance
    
    # Precisamos recriar o chunker para pegar o mock da bridge
    chunker = TextChunker(max_chars=100, overlap_chars=30, min_chars=20)
    chunks = chunker.chunk_pages([single_page], source_name="test_source")
    
    assert len(chunks) == 3
    assert "Primeiro parágrafo" in chunks[0].text
    assert "Segundo parágrafo" in chunks[1].text
    assert "Quarto parágrafo" in chunks[2].text

@patch("alana_system.preprocessing.chunker.BinaryBridge")
def test_paragraph_too_long(mock_bridge, single_page):
    """
    Testa o caso crítico onde um único parágrafo excede `max_chars`.
    """
    long_paragraph = "a" * 150
    page = CleanedPageText(
        page_number=1,
        text=long_paragraph,
        original_char_count=len(long_paragraph),
        cleaned_char_count=len(long_paragraph),
    )
    
    mock_bridge_instance = MagicMock()
    # Simula o corte do Go
    mock_bridge_instance.call.return_value = [
        {"content": "a" * 100},
        {"content": "a" * 50}
    ]
    mock_bridge.return_value = mock_bridge_instance
    chunker = TextChunker(max_chars=100, overlap_chars=30, min_chars=20)
    
    chunks = chunker.chunk_pages([page], source_name="test_source")
    
    assert len(chunks) == 2
    assert chunks[0].text.startswith("a")
    assert chunks[0].char_count == 100
    assert chunks[-1].char_count == 50

@patch("alana_system.preprocessing.chunker.BinaryBridge")
def test_overlap_logic(mock_bridge):
    """
    Testa se o overlap semântico está funcionando, mantendo parágrafos.
    """
    p1 = "a" * 30
    p2 = "b" * 30
    p3 = "c" * 30
    p4 = "d" * 30
    text = f"{p1}\n\n{p2}\n\n{p3}\n\n{p4}"
    page = CleanedPageText(
        page_number=1,
        text=text,
        original_char_count=len(text),
        cleaned_char_count=len(text),
    )

    mock_bridge_instance = MagicMock()
    mock_bridge_instance.call.return_value = [
        {"content": f"{p1}\n\n{p2}\n\n{p3}"},
        {"content": f"{p3}\n\n{p4}"}
    ]
    mock_bridge.return_value = mock_bridge_instance
    chunker = TextChunker(max_chars=100, overlap_chars=30, min_chars=20)

    chunks = chunker.chunk_pages([page], source_name="test_source")

    assert len(chunks) == 2
    assert chunks[0].text == f"{p1}\n\n{p2}\n\n{p3}"
    assert chunks[1].text == f"{p3}\n\n{p4}"

@patch("alana_system.preprocessing.chunker.BinaryBridge")
def test_min_chars_logic(mock_bridge):
    """
    Testa se parágrafos ou chunks combinados que não atingem `min_chars`
    são descartados.
    """
    p1 = "a" * 15  # < min_chars
    p2 = "b" * 50
    text = f"{p1}\n\n{p2}"
    page = CleanedPageText(
        page_number=1,
        text=text,
        original_char_count=len(text),
        cleaned_char_count=len(text),
    )

    mock_bridge_instance = MagicMock()
    mock_bridge_instance.call.return_value = [
        {"content": "a" * 15}, # filtrado
        {"content": "b" * 50}  # mantido
    ]
    mock_bridge.return_value = mock_bridge_instance
    chunker = TextChunker(max_chars=100, overlap_chars=30, min_chars=20)

    chunks = chunker.chunk_pages([page], source_name="test_source")
    
    assert len(chunks) == 1
    assert chunks[0].text == p2

def test_chunk_id_is_deterministic(chunker):
    """
    Garante que o mesmo texto de entrada sempre gera o mesmo ID de chunk.
    """
    text = "Este é um texto de teste para verificar a estabilidade do hash."
    page1 = CleanedPageText(
        page_number=1,
        text=text,
        original_char_count=len(text),
        cleaned_char_count=len(text),
    )
    page2 = CleanedPageText(
        page_number=1,
        text=text,
        original_char_count=len(text),
        cleaned_char_count=len(text),
    )

    chunks1 = chunker.chunk_pages([page1], source_name="test_source")
    chunks2 = chunker.chunk_pages([page2], source_name="test_source")

    assert len(chunks1) == 1
    assert len(chunks2) == 1
    assert chunks1[0].chunk_id == chunks2[0].chunk_id
