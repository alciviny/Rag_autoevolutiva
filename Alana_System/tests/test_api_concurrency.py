import threading
import time
from unittest.mock import patch, MagicMock

BASE_URL = "http://localhost:8000"

@patch("requests.get")
def test_health(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "ready"}
    mock_get.return_value = mock_resp
    
    print("Testing /health...")
    response = mock_get(f"{BASE_URL}/health")
    print(f"Health Response: {response.json()}")
    assert response.status_code == 200

@patch("requests.post")
def test_chat_non_blocking(mock_post):
    print("Testing Chat Concurrency...")
    
    def call_generate():
        start = time.time()
        resp = mock_post(f"{BASE_URL}/generate", json={"query": "Quem é você?"})
        print(f"Chat finished in {time.time() - start:.2f}s")
        
    threads = []
    for i in range(3):
        t = threading.Thread(target=call_generate)
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
    
    assert mock_post.call_count == 3

@patch("requests.post")
def test_ingestion_background(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"status": "processing"}
    mock_post.return_value = mock_resp
    
    print("Testing Ingestion Background Task...")
    payload = {
        "path": "data/raw/test.pdf",
        "type": "PDF"
    }
    response = mock_post(f"{BASE_URL}/process_document", json=payload)
    print(f"Ingestion Response: {response.json()}")
    assert response.status_code == 200
