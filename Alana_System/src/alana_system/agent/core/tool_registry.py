import logging
from typing import Dict, Any, List, Optional, Union, get_args, get_origin
import inspect
from types import UnionType
from ..tools.base_tool import BaseTool

logger = logging.getLogger("alana.agent.registry")


def _json_schema(annotation: Any) -> Dict[str, Any]:
    origin = get_origin(annotation)
    args = get_args(annotation)
    if origin in (Union, UnionType):
        variants = [_json_schema(arg) for arg in args if arg is not type(None)]
        return variants[0] if len(variants) == 1 else {"anyOf": variants}
    if origin is list or annotation is list or annotation is List:
        return {"type": "array", "items": _json_schema(args[0] if args else str)}
    if origin is dict or annotation is dict or annotation is Dict:
        return {"type": "object"}
    if annotation is int: return {"type": "integer"}
    if annotation is float: return {"type": "number"}
    if annotation is bool: return {"type": "boolean"}
    if annotation is str: return {"type": "string"}
    return {"type": "string"}

class ToolRegistry:
    """
    O 'Cinto de Utilidades' Dinamico da Alana.
    Permite registrar, buscar e gerenciar ferramentas de forma modular.
    """

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """Registra uma nova ferramenta no sistema."""
        if tool.name in self.tools:
            logger.warning(f"🔧 Ferramenta '{tool.name}' ja estava registrada. Sobrescrevendo.")
        
        self.tools[tool.name] = tool
        logger.info(f"🔌 Ferramenta plugada: {tool.name}")

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Busca uma ferramenta pelo nome."""
        return self.tools.get(name)

    def list_tools(self) -> List[str]:
        """Lista todos os nomes de ferramentas disponiveis."""
        return list(self.tools.keys())

    def get_all_descriptions(self) -> str:
        """Gera a documentacao de todas as ferramentas para o Prompt do Agente."""
        descriptions = []
        for name, tool in self.tools.items():
            descriptions.append(f"- `{name}`: {tool.description}")
        return "\n".join(descriptions)

    def get_openai_tools_schema(self) -> List[Dict[str, Any]]:
        """
        Converte as ferramentas registradas para o formato Nativo de Function Calling
        compativel com OpenAI, Groq e LiteLLM.
        """
        schema_list = []
        for name, tool in self.tools.items():
            # Extrai a assinatura do metodo execute
            sig = inspect.signature(tool.execute)
            properties = {}
            required = []
            
            for param_name, param in sig.parameters.items():
                if param.kind in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL):
                    continue
                    
                properties[param_name] = {**_json_schema(param.annotation), "description": f"Parametro {param_name}"}
                
                # Se nao tiver valor default, e obrigatorio
                if param.default == inspect.Parameter.empty:
                    required.append(param_name)
                    
            # Formato estrito da OpenAI
            function_def = {
                "name": name,
                "description": tool.description,
                "parameters": {
                    "type": "object",
                    "properties": properties
                }
            }
            if required:
                function_def["parameters"]["required"] = required
                
            schema_list.append({
                "type": "function",
                "function": function_def
            })
            
        # Tool nativa especial para encerrar a missao
        schema_list.append({
            "type": "function",
            "function": {
                "name": "final_answer",
                "description": "Retorna a resposta final da missao e encerra a operacao.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "A resposta final executiva."
                        }
                    },
                    "required": ["message"]
                }
            }
        })
        
        return schema_list
