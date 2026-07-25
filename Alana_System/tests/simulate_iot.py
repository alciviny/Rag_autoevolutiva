import requests
import asyncio
import websockets
import json
import os
import sys

# Configuracoes do Servidor
BASE_URL = "http://localhost:8000/api/iot"
WS_URL = "ws://localhost:8000/iot/stream"

async def test_proactive_stream():
    """Simula um wearable conectado esperando alertas da Alana."""
    print("--- Conectando ao Stream Proativo (JARVIS Mode) ---")
    try:
        async with websockets.connect(WS_URL) as websocket:
            print("--- Conectado! Aguardando alertas da Alana ---")
            while True:
                msg = await websocket.recv()
                data = json.loads(msg)
                print(f"\nALERTA RECEBIDO: {data['content']}")
    except Exception as e:
        print(f"--- Erro no Stream: {e} ---")

def simulate_vision(image_path, prompt="Analise tecnicamente o que voce ve."):
    """Simula uma camera enviando um frame."""
    print(f"\n[SIMULACAO] Enviando imagem: {image_path}")
    if not os.path.exists(image_path):
        print(f"--- Erro: Arquivo {image_path} nao encontrado ---")
        return

    try:
        with open(image_path, 'rb') as img:
            files = {'image': img}
            data = {'namespace': 'lab_teste', 'prompt': prompt}
            
            response = requests.post(f"{BASE_URL}/vision", files=files, data=data)
            if response.status_code == 200:
                desc = response.json().get('description', '')
                print("--- Sucesso! Alana diz: ---")
                # Remove caracteres nao-ascii para o terminal windows
                print(desc.encode('ascii', 'ignore').decode('ascii'))
                print("---------------------------")
            else:
                print(f"--- Falha no servidor: {response.status_code} ---")
    except Exception as e:
        print(f"--- Erro na simulacao: {str(e)} ---")

def simulate_voice(audio_path):
    """Simula um microfone enviando comando."""
    print(f"\n[SIMULACAO] Enviando audio: {audio_path}")
    if not os.path.exists(audio_path):
        print(f"--- Erro: Arquivo {audio_path} nao encontrado ---")
        return

    try:
        with open(audio_path, 'rb') as audio:
            files = {'audio': audio}
            data = {'namespace': 'lab_teste'}
            
            response = requests.post(f"{BASE_URL}/voice", files=files, data=data)
            if response.status_code == 200:
                res_data = response.json()
                print(f"Transcricao: {res_data.get('transcription')}")
                print(f"Resposta: {res_data.get('answer')}")
            else:
                print(f"--- Falha no servidor: {response.status_code} ---")
    except Exception as e:
        print(f"--- Erro na simulacao: {str(e)} ---")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python simulate_iot.py [vision/voice/stream] [caminho_arquivo]")
        sys.exit(1)
        
    cmd = sys.argv[1]
    
    if cmd == "vision":
        simulate_vision(sys.argv[2])
    elif cmd == "voice":
        simulate_voice(sys.argv[2])
    elif cmd == "stream":
        asyncio.run(test_proactive_stream())
    else:
        print("Comando invalido.")
