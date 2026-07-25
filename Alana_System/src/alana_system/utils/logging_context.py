import contextvars
import logging
import uuid
from typing import Optional

# Contexto global para o Trace ID (Thread-safe e Async-safe)
trace_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("trace_id", default="SYSTEM")

class TraceIDFilter(logging.Filter):
    """
    Filtro de log que injeta o trace_id atual em cada registro de log.
    """
    def filter(self, record):
        record.trace_id = trace_id_var.get()
        return True

def set_trace_id(new_id: Optional[str] = None) -> str:
    """
    Define um novo Trace ID para o contexto atual.
    Se nenhum for passado, gera um UUID curto.
    """
    if not new_id:
        new_id = str(uuid.uuid4())[:8]
    trace_id_var.set(new_id)
    return new_id

def get_trace_id() -> str:
    """Retorna o Trace ID atual."""
    return trace_id_var.get() or "SYSTEM"
