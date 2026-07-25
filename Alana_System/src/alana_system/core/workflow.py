import yaml
import logging
from typing import List, Optional, Dict
from pydantic import BaseModel

logger = logging.getLogger("alana.core.workflow")

class WorkflowStep(BaseModel):
    id: str
    instruction: str           # O que a Alana vai falar para o usuario
    validation_prompt: Optional[str] = None  # O que a IA deve procurar na camera para validar
    retry_message: Optional[str] = "Nao consegui confirmar a acao. Por favor, tente novamente e mostre bem para a camera."

class Workflow(BaseModel):
    name: str
    description: str
    steps: List[WorkflowStep]

class WorkflowSession:
    """Rastreia o progresso do usuario em um manual tecnico."""
    def __init__(self, workflow: Workflow):
        self.workflow = workflow
        self.current_step_index = 0
        self.is_completed = False

    def get_current_step(self) -> Optional[WorkflowStep]:
        if self.current_step_index < len(self.workflow.steps):
            return self.workflow.steps[self.current_step_index]
        return None

    def next_step(self):
        self.current_step_index += 1
        if self.current_step_index >= len(self.workflow.steps):
            self.is_completed = True
