import logging
import json
import asyncio
import os
import re
import tempfile
import threading
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("alana.agent.blackboard")

class MissionBlackboard:
    """
    O 'Mapa Mental' da Missão. 
    Evita redundância, gerencia progresso e mantém a Alana focada no Alvo.
    """

    def __init__(self, namespace: str = "global"):
        if not isinstance(namespace, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", namespace):
            raise ValueError("Namespace inválido para o Blackboard.")
        self.namespace = namespace
        self.confirmed_facts: List[str] = []
        self.failed_attempts: List[str] = []
        self.current_strategy: str = "Exploração Inicial"
        self.technical_notes: Dict[str, Any] = {}
        root = Path("data/memory/blackboards").resolve()
        self.storage_path = (root / f"{namespace}.json").resolve()
        if not self.storage_path.is_relative_to(root):
            raise ValueError("Arquivo do Blackboard fora do diretório permitido.")
        self._save_lock = threading.Lock()
        self._save_revision = 0
        self._load()

    def update_strategy(self, strategy: str):
        self.current_strategy = strategy
        self._save()

    def add_fact(self, fact: str):
        if fact not in self.confirmed_facts:
            self.confirmed_facts.append(fact)
            self._save()

    def add_failure(self, failure: str):
        if failure not in self.failed_attempts:
            self.failed_attempts.append(failure)
            self._save()

    def add_note(self, key: str, value: Any):
        self.technical_notes[key] = value
        self._save()

    def _snapshot(self):
        return {
            "confirmed_facts": list(self.confirmed_facts),
            "failed_attempts": list(self.failed_attempts),
            "current_strategy": self.current_strategy,
            "technical_notes": dict(self.technical_notes),
        }

    def _save_sync(self, data=None, revision=None):
        """Persiste um snapshot completo com replace atômico."""
        temp_path = None
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            data = data or self._snapshot()
            with self._save_lock:
                if revision is not None and revision != self._save_revision:
                    return
                with tempfile.NamedTemporaryFile("w", delete=False, dir=self.storage_path.parent, suffix=".tmp", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    temp_path = Path(f.name)
                os.replace(temp_path, self.storage_path)
        except Exception as e:
            logger.error(f"Erro ao salvar Blackboard: {e}")
            if temp_path:
                temp_path.unlink(missing_ok=True)

    def _save(self):
        """Persiste o estado no disco sem bloquear o Event Loop principal."""
        try:
            loop = asyncio.get_running_loop()
            with self._save_lock:
                self._save_revision += 1
                revision = self._save_revision
            loop.run_in_executor(None, self._save_sync, self._snapshot(), revision)
        except RuntimeError:
            # Fallback se não houver event loop (ex: instanciado fora do fluxo async)
            self._save_sync()

    def _load(self):
        """Carrega o estado do disco se existir."""
        if self.storage_path.exists():
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.confirmed_facts = data.get("confirmed_facts", [])
                    self.failed_attempts = data.get("failed_attempts", [])
                    self.current_strategy = data.get("current_strategy", "Retomada de Missão")
                    self.technical_notes = data.get("technical_notes", {})
                logger.info(f"🧠 Blackboard '{self.namespace}' retomado do disco.")
            except Exception as e:
                logger.error(f"Erro ao carregar Blackboard: {e}")

    def render(self) -> str:
        """Gera uma visão técnica condensada para o Prompt da IA."""
        status = [
            "### QUADRO NEGRO DA MISSÃO (ESTADO ATUAL) ###",
            f"ESTRATÉGIA: {self.current_strategy}",
            f"FATOS CONFIRMADOS: {', '.join(self.confirmed_facts) if self.confirmed_facts else 'Nenhum'}",
            f"CAMINHOS FALHOS: {', '.join(self.failed_attempts) if self.failed_attempts else 'Nenhum'}",
            f"NOTAS TÉCNICAS: {json.dumps(self.technical_notes) if self.technical_notes else 'Nenhuma'}",
            "############################################"
        ]
        return "\n".join(status)
