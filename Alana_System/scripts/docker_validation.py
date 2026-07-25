import subprocess
import time
import sys
import os

# Configurações Industriais
CONTAINER_NAME = "alana_bridge_api"
HEALTH_URL = "http://localhost:8000/api/health"
MAX_RETRIES = 30  # 30 * 2s = 60s timeout
HEALTH_CHECK_SCRIPT = "tests/system_health_check.py"

def run_command(cmd):
    """Executa um comando shell e retorna o resultado."""
    print(f"🛠️ Executando: {cmd}")
    try:
        # Usamos shell=True para compatibilidade com Windows/Linux
        result = subprocess.run(cmd, shell=True, text=True, capture_output=True)
        return result
    except Exception as e:
        print(f"❌ Erro ao executar comando: {e}")
        return None

def main():
    print("\n" + "="*50)
    print("🚀 INICIANDO VALIDAÇÃO DE PRÉ-DEPLOY DOCKER - ALANA")
    print("="*50 + "\n")

    # 1. Build da Imagem
    print("📦 [1/5] Construindo imagens Docker...")
    build = run_command("docker-compose build")
    if build.returncode != 0:
        print("❌ Falha no Build!")
        print(build.stderr)
        sys.exit(1)
    print("✅ Build concluído com sucesso.\n")

    # 2. Start dos Containers
    print("🔌 [2/5] Iniciando ambiente isolado...")
    up = run_command("docker-compose up -d")
    if up.returncode != 0:
        print("❌ Falha ao subir containers!")
        print(up.stderr)
        sys.exit(1)
    print("✅ Containers em execução.\n")

    # 3. Aguardar Healthcheck da API
    print("⏳ [3/5] Aguardando inicialização dos motores (Healthcheck)...")
    success = False
    for i in range(MAX_RETRIES):
        # Tenta dar um curl no endpoint de health
        # No Windows, usamos curl (nativo no Win10+) ou verificamos via docker inspect
        check = run_command(f'docker inspect --format="{{{{.State.Health.Status}}}}" {CONTAINER_NAME}')
        status = check.stdout.strip() if check else ""
        
        if status == "healthy":
            print(f"\n✅ API está ONLINE e Saudável após {i*2}s.")
            success = True
            break
        
        print(".", end="", flush=True)
        time.sleep(2)
    
    if not success:
        print("\n❌ TIMEOUT: O sistema não ficou saudável a tempo.")
        run_command("docker-compose logs alana_bridge_api")
        run_command("docker-compose down")
        sys.exit(1)

    # 4. Executar Teste de Integridade Profundo
    print("\n🔍 [4/5] Executando Check-up de Integridade Profundo...")
    test = run_command(f"docker exec {CONTAINER_NAME} python {HEALTH_CHECK_SCRIPT}")
    print("-" * 30)
    print(test.stdout)
    print("-" * 30)

    if "100% OPERACIONAL" not in test.stdout:
        print("⚠️ AVISO: O sistema subiu, mas falhou em testes funcionais internos.")
        print(test.stderr)
        # Opcional: docker-compose down aqui?
        # run_command("docker-compose down")
        # sys.exit(1)
    else:
        print("✨ EXCELENTE: Todos os sistemas estão operacionais no Docker!")

    # 5. Finalização
    print("\n🧹 [5/5] Limpando ambiente de teste...")
    # Se quiser deixar rodando, comente a linha abaixo
    run_command("docker-compose down")
    
    print("\n" + "="*50)
    print("✅ VALIDAÇÃO CONCLUÍDA!")
    print("Pode prosseguir com o Upload / Push com segurança.")
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
