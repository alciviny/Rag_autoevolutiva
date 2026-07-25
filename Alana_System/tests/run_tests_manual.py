import sys
import os
from fastapi.testclient import TestClient

# Adiciona a raiz do projeto ao path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from bridge import app

def run_tests():
    with TestClient(app) as client:
        print("\n--- Teste 1: Health Check ---")
        response = client.get("/api/health")
        assert response.status_code == 200, f"Erro: {response.text}"
        print("[OK] Health Check passou.")

        print("\n--- Teste 2: Embed Endpoint ---")
        response = client.post("/api/embed", params={"text": "Teste de IA"})
        assert response.status_code == 200, f"Erro: {response.text}"
        assert "vector" in response.json()
        print("[OK] Endpoint /embed passou.")

        print("\n--- Teste 3: Generate Endpoint (Bypass Context) ---")
        payload = {
            "query": "Qual é a cor da maçã citada?",
            "context_override": "A maçã era verde.",
            "stream": False
        }
        response = client.post("/api/generate", json=payload)
        assert "answer" in response.json(), f"Sem resposta: {response.text}"
        print(f"Resposta Gerada: {response.json()['answer']}")
        print("[OK] Endpoint /generate passou.")

        print("\nTodos os testes passaram com sucesso! O sistema está integrado e responsivo.")

if __name__ == "__main__":
    run_tests()
