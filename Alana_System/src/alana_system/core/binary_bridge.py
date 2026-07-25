import json
import subprocess
import logging
import os
import tempfile
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger("alana.core.binary_bridge")

class BinaryBridge:
    """
    Gerenciador Universal de Motores de Alta Performance (Go/Rust).
    Unifica a comunicacao, tratamento de erros e performance.
    """

    def __init__(self, bin_name: str):
        # Localiza o binario na pasta 'bin' na raiz do projeto
        import platform
        
        # Normaliza o nome do binário para o SO atual
        if platform.system() != "Windows" and bin_name.endswith(".exe"):
            bin_name = bin_name[:-4]
        elif platform.system() == "Windows" and not bin_name.endswith(".exe"):
            bin_name += ".exe"

        base_dir = Path(__file__).resolve().parent.parent.parent.parent
        self.bin_path = base_dir / "bin" / bin_name
        
        if not self.bin_path.exists():
            # Fallback para raiz caso nao tenha sido movido (resiliencia)
            self.bin_path = base_dir / bin_name
            
        if not self.bin_path.exists():
            logger.error(f"❌ Motor nao encontrado: {self.bin_path}")

    def call(self, input_data: Dict[str, Any]) -> Any:
        """Executa o binario com suporte a File-Swap para grandes volumes."""
        if not self.bin_path.exists():
            raise FileNotFoundError(f"Binario {self.bin_path.name} ausente.")

        input_json = json.dumps(input_data)
        temp_file_path = None
        cmd = [str(self.bin_path)]

        # Protocolo Industrial: Se > 2MB, usa troca por arquivo (File-Swap)
        if len(input_json) > 2 * 1024 * 1024:
            with tempfile.NamedTemporaryFile('w', delete=False, suffix='.json', encoding='utf-8') as tf:
                tf.write(input_json)
                temp_file_path = tf.name
            cmd.extend(["--file", temp_file_path])
            logger.info(f"💾 Payload massivo detectado ({len(input_json)/1024/1024:.2f}MB). Usando File-Swap.")
            input_json = None # Libera RAM imediatamente

        try:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE if not temp_file_path else None,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                encoding='utf-8',
                errors='ignore'
            )
            
            # Se nao estiver usando arquivo, envia via stdin
            stdin_content = input_json if not temp_file_path else None
            stdout, stderr = process.communicate(input=stdin_content)
            
            if process.returncode != 0:
                logger.error(f"❌ Falha no motor {self.bin_path.name}: {stderr}")
                raise RuntimeError(f"Erro no motor binario: {stderr}")

            return json.loads(stdout)
            
        except Exception as e:
            logger.error(f"💥 Erro na ponte binaria ({self.bin_path.name}): {e}")
            raise
        finally:
            # Limpeza do arquivo temporario
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass
