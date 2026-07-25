import unittest
from unittest.mock import patch, MagicMock
import sys
import os

# Ajusta path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from alana_system.inference.llm_engine import LLMEngine

class TestInferenceTurbo(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = LLMEngine(default_model="ollama/llama3.1")

    @patch("alana_system.inference.llm_engine.acompletion")
    async def test_generate_answer_success(self, mock_acompletion):
        """Testa resposta normal com sucesso."""
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Ola, eu sou a Alana."
        mock_response.model = "ollama/llama3.1"
        mock_acompletion.return_value = mock_response

        messages = [{"role": "user", "content": "Oi"}]
        answer = await self.engine.generate_answer(messages)
        
        self.assertEqual(answer, "Ola, eu sou a Alana.")
        mock_acompletion.assert_called_once()

    @patch("alana_system.inference.llm_engine.acompletion")
    async def test_generate_answer_retry(self, mock_acompletion):
        """Testa se o sistema tenta de novo em caso de erro temporario."""
        # Falha na primeira, acerta na segunda
        mock_response = MagicMock()
        mock_response.choices[0].message.content = "Recuperei!"
        mock_acompletion.side_effect = [Exception("Ollama busy"), mock_response]

        messages = [{"role": "user", "content": "Oi"}]
        answer = await self.engine.generate_answer(messages)
        
        self.assertEqual(answer, "Recuperei!")
        self.assertEqual(mock_acompletion.call_count, 2)

    @patch("alana_system.inference.llm_engine.acompletion")
    async def test_streaming_mode(self, mock_acompletion):
        """Testa o modo de streaming (palavra por palavra)."""
        # Simula gerador assíncrono do litellm
        mock_chunk1 = MagicMock()
        mock_chunk1.choices[0].delta.content = "Parte 1 "
        mock_chunk2 = MagicMock()
        mock_chunk2.choices[0].delta.content = "Parte 2"
        
        async def mock_stream():
            yield mock_chunk1
            yield mock_chunk2
            
        mock_acompletion.return_value = mock_stream()

        messages = [{"role": "user", "content": "Oi"}]
        stream = await self.engine.generate_answer(messages, stream=True)
        
        chunks = [chunk async for chunk in stream]
        self.assertEqual(chunks, ["Parte 1 ", "Parte 2"])

if __name__ == "__main__":
    unittest.main()
