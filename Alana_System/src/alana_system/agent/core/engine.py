import json
import logging
import asyncio
import re
from typing import List, Dict, Callable, Any, Optional

from ...inference.llm_engine import LLMEngine
from .tool_registry import ToolRegistry
from .blackboard import MissionBlackboard
from .dynamic_manager import DynamicToolManager
from ...iot.hal import hal

logger = logging.getLogger("alana.agent.engine")

class AgentEngine:
    """
    Motor de Execucao Autonoma da Alana.
    Garante raciocinio estruturado, uso de ferramentas e isolamento industrial (Namespaces).
    """
    def __init__(self, query_engine=None, deep_search_agent=None, graph_intelligence=None, llm=None, dynamic_manager=None, is_primary=True):
        # Imports Lazy para evitar circularidade
        from ..tools.file_system import WriteCodeTool, ReadFileTool, ListDirTool
        from ..tools.code_runners.python_runner import PythonRunnerTool
        from ..tools.code_runners.cpp_runner import CppRunnerTool
        from ..tools.code_runners.node_runner import NodeRunnerTool
        from ..tools.code_runners.rust_runner import RustRunnerTool
        from ..tools.simulators.terminal_sim import TerminalSimulatorTool
        from ..tools.research_tool import ResearchTool
        from ..tools.memory_tool import MemoryTool
        from ..tools.graph_navigation_tool import NavigateGraphTool
        from ..tools.store_fact_tool import StoreFactTool
        from ..tools.analyst_tool import AutonomousAnalystTool
        from ..tools.theory_tool import TheoryValidationTool
        from ..tools.calculator_tool import EngineeringCalculatorTool
        from ..tools.vision_tool import VisionAnalysisTool
        from ..tools.synthesizer_tool import SynthesizeTool
        from ..tools.delegation_tool import DelegateTaskTool
        from .dynamic_manager import DynamicToolManager
        from ...iot.vision import VisionProcessor

        self.llm = llm or LLMEngine()
        self.query_engine = query_engine
        self.deep_search_agent = deep_search_agent
        self.is_primary = is_primary
        self.max_loops = 30 # Protecao contra loops infinitos
        self.event_callbacks: List[Callable] = []
        self.registry = ToolRegistry()
        self._mission_lock = asyncio.Lock()
        self._dynamic_tool_names = set()
        self._core_tool_names = set()
        self.dynamic_manager = dynamic_manager or DynamicToolManager()
        self.blackboard = MissionBlackboard("global")
        
        # Registro de ferramentas industriais
        self.registry.register(WriteCodeTool())
        self.registry.register(ReadFileTool())
        self.registry.register(ListDirTool())
        self.registry.register(PythonRunnerTool())
        self.registry.register(CppRunnerTool())
        self.registry.register(NodeRunnerTool())
        self.registry.register(RustRunnerTool())
        self.registry.register(TerminalSimulatorTool())
        self.registry.register(EngineeringCalculatorTool())
        self.registry.register(TheoryValidationTool())
        self.registry.register(SynthesizeTool(self.dynamic_manager, self))
        
        # Apenas o Agente Primário pode delegar (previne recursão de sub-agentes criando sub-agentes infinitamente)
        if self.is_primary:
            self.registry.register(DelegateTaskTool(self))
        
        if query_engine:
            self.registry.register(MemoryTool(query_engine))
            if not graph_intelligence and hasattr(query_engine, 'intelligence'):
                graph_intelligence = query_engine.intelligence
            
        self.registry.register(ResearchTool(deep_search_agent))
            
        if graph_intelligence:
            self.registry.register(NavigateGraphTool(graph_intelligence))
            if hasattr(graph_intelligence, 'graph_store'):
                self.registry.register(StoreFactTool(graph_intelligence.graph_store, graph_intelligence))
            self.registry.register(AutonomousAnalystTool(graph_intelligence))
            
        # Olho de JARVIS
        self.registry.register(VisionAnalysisTool(VisionProcessor()))
        self._core_tool_names = set(self.registry.list_tools())

    async def run_mission(self, mission: str, namespace: str = "global", event_callback=None, approval_callback=None):
        # Tools and blackboard are shared mutable state; serialize missions per engine.
        async with self._mission_lock:
            return await self._run_mission(mission, namespace, event_callback, approval_callback)

    async def _run_mission(self, mission: str, namespace: str = "global", event_callback=None, approval_callback=None):
        """
        Executa uma missao autonoma com isolamento de projeto (Namespace).
        """
        async def emit(event_type: str, data: Any):
            if event_callback: await event_callback(event_type, data)

        logger.info(f"🚀 INICIANDO MISSÃO INDUSTRIAL [{namespace}]: {mission}")
        await emit("mission_start", {"description": mission, "namespace": namespace})
        
        # 1. Limpeza Industrial (GC)
        self.dynamic_manager.run_garbage_collection(namespace)
        
        # 2. Inicializa Blackboard com persistência baseada no namespace
        self.blackboard = MissionBlackboard(namespace)
        
        # 3. Verificação de Saúde de Hardware (Proatividade IoT)
        hw_status = hal.get_device_status()
        offline_devices = [d["id"] for d in hw_status if d["status"] == "OFFLINE"]
        if offline_devices:
            alert = f"⚠️ ALERTA DE HARDWARE: Os dispositivos {offline_devices} estão OFFLINE. Considere isso no seu plano."
            self.blackboard.add_note("hw_alert", alert)
            logger.warning(alert)

        # 4. Carrega ferramentas dinâmicas do namespace (Tool Maker)
        for tool_name in self._dynamic_tool_names:
            self.registry.tools.pop(tool_name, None)
        self._dynamic_tool_names.clear()
        dynamic_tools = self.dynamic_manager.load_tools_for_namespace(namespace)
        for d_tool in dynamic_tools:
            if d_tool.name in self._core_tool_names:
                logger.warning("Ferramenta dinâmica ignorada por conflito com ferramenta nativa: %s", d_tool.name)
                continue
            self.registry.register(d_tool)
            self._dynamic_tool_names.add(d_tool.name)
            
        # Injeta o namespace no sistema de ferramentas
        for tool_name in self.registry.list_tools():
            tool = self.registry.get_tool(tool_name)
            if hasattr(tool, 'set_context'):
                tool.set_context(namespace)

        messages = [
            {"role": "system", "content": self._build_system_prompt(namespace)},
            {"role": "user", "content": f"OBJETIVO: {mission}"}
        ]
        
        for attempt in range(1, self.max_loops + 1):
            tools_schema = self.registry.get_openai_tools_schema()
            messages = await self._manage_context(messages)
            await emit("cycle_start", {"attempt": attempt, "total": self.max_loops})
            
            try:
                # O motor industrial agora usa a LLMEngine singular com function calling
                resp_obj = await self.llm.generate_answer(messages=messages, tools=tools_schema)
                if not resp_obj:
                    raise ValueError("LLM retornou resposta vazia.")
                    
                message = resp_obj.choices[0].message
                
            except Exception as e:
                logger.error(f"Falha na API: {e}")
                messages.append({"role": "user", "content": "ERRO: Falha de comunicação com o LLM."})
                await asyncio.sleep(1) # Pequena pausa para evitar spam em caso de erro persistente
                continue

            pensamento = message.content or "Iniciando chamada de função..."
            await emit("thought", {"content": pensamento})
            
            # Anti-Hallucination: Modelos as vezes escrevem a function call no texto
            if "final_answer" in pensamento:
                # Tenta extrair o argumento message
                match = re.search(r'message\s*[=:]\s*["\'](.*?)["\']', pensamento, re.DOTALL | re.IGNORECASE)
                if match:
                    msg_final = match.group(1)
                    logger.warning(f"🔧 Anti-Hallucination ativado: Extraído message do texto.")
                    return msg_final
                elif "Resumo" in pensamento or "Concluíd" in pensamento or "message" in pensamento:
                    logger.warning(f"🔧 Anti-Hallucination fallback: Retornando pensamento inteiro.")
                    return pensamento
            
            # Adiciona a mensagem do assistente ao histórico de forma segura para não quebrar a API do Groq
            safe_message = {"role": "assistant", "content": pensamento}
            tool_calls = getattr(message, "tool_calls", None)
            if tool_calls:
                safe_tool_calls = []
                for tc in tool_calls:
                    safe_tc = {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    safe_tool_calls.append(safe_tc)
                safe_message["tool_calls"] = safe_tool_calls
            
            messages.append(safe_message)

            tool_calls = getattr(message, "tool_calls", None)
            if not tool_calls:
                messages.append({"role": "user", "content": "Você deve chamar uma ferramenta para avançar na missão, ou use `final_answer` se concluiu."})
                continue
                
            for tool_call in tool_calls:
                tool_call_id = tool_call.id
                ferramenta = tool_call.function.name
                try:
                    argumentos = json.loads(tool_call.function.arguments)
                except Exception:
                    argumentos = {}

                if ferramenta == "final_answer":
                    msg_final = argumentos.get("message", "Missão concluída.")
                    # REMOVIDO: O 'mission_complete' agora é emitido pelo Orquestrador, após a auditoria.
                    return msg_final

                # Execucao de Ferramentas
                if ferramenta in self.registry.list_tools():
                    tool_instance = self.registry.get_tool(ferramenta)
                    await emit("tool_start", {"name": ferramenta, "args": argumentos})
                    try:
                        # A ferramenta ja conhece o namespace via set_context
                        resultado = await tool_instance.execute(**argumentos)
                    except Exception as e:
                        resultado = f"[ERRO]: {str(e)}"
                    await emit("tool_result", {"name": ferramenta, "result": str(resultado)})
                else:
                    resultado = f"Erro: Ferramenta '{ferramenta}' nao encontrada."
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": ferramenta,
                    "content": str(resultado)
                })
            
        return "Limite de ciclos atingido."

    def _build_system_prompt(self, namespace: str) -> str:
        prompt = f"""Você é a ALANA, uma Inteligência Artificial de Engenharia nível Stark.
MISSÃO ATUAL: Operar no namespace industrial '{namespace}'.

PERSONALIDADE:
- Eficiente, autoritária e focada em resultados.
- Você não 'acha', você valida.
- Sua prioridade é a integridade do sistema e o sucesso da missão.

DIRETRIZES DE OPERAÇÃO:
1. METACOGNIÇÃO: Antes de escolher uma ferramenta, revise se seu plano é o caminho mais curto e seguro.
2. TOOL MAKER: Se você não tiver uma ferramenta para um problema matemático, de dados ou de hardware específico, USE 'synthesize_new_tool' para CRIAR uma solução permanente.
3. VISÃO: Se houver imagens anexadas ou diagramas, use 'analyze_visual_data' para 'olhar' o hardware.
4. PRECISÃO STARK: Use o blackboard para manter fatos isolados de suposições.
5. ERRO ZERO: Se uma ferramenta falhar, analise o motivo e mude a estratégia imediatamente.

USO DE FERRAMENTAS:
- Você DEVE usar as ferramentas (function calling) disponíveis para executar a missão.
- Use a ferramenta `final_answer` APENAS quando a missão estiver concluída. 
- ATENÇÃO: O argumento 'message' da ferramenta `final_answer` DEVE conter a RESPOSTA DETALHADA E COMPLETA para a missão. Se o usuário pediu um resumo, coloque o texto do resumo. Se pediu código, coloque o código final. NÃO escreva apenas 'Missão concluída com sucesso', entregue o produto real!
"""
        prompt += f"\n\nESTADO ATUAL DO BLACKBOARD:\n{self.blackboard.render()}\n"
        return prompt



    async def _manage_context(self, messages: List[Dict]) -> List[Dict]:
        """
        Gestão de Contexto Seguro para Function Calling.
        Garante que chamadas de ferramenta e seus resultados nunca sejam separados.
        """
        full_text = "".join([m.get("content", "") or "" for m in messages])
        total_tokens = self.llm.get_token_count(full_text)
        
        threshold = int(self.llm.context_window * 0.7)
        
        if total_tokens < threshold:
            return messages

        logger.info(f"🧠 Contexto saturado ({total_tokens} tokens): Compressão segura...")
        
        system_msg = messages[0]
        objective_msg = messages[1]
        
        # Agrupar mensagens em 'Turnos' seguros.
        # Um turno seguro é: [User/Assistant(com tool_calls)] + [Tool(resultados)]
        turns = []
        current_turn = []
        
        for msg in messages[2:]:
            role = msg.get("role")
            
            # Se for um novo assistente ou user, e já temos um turno, fechamos ele.
            if role in ["user", "assistant"] and current_turn:
                # Mas espera, se o ultimo for assistant com tool_calls, não podemos fechar o turno ainda.
                last_msg = current_turn[-1]
                if last_msg.get("role") == "assistant" and last_msg.get("tool_calls"):
                    pass # O turno continua esperando as respostas 'tool'
                else:
                    turns.append(current_turn)
                    current_turn = []
            
            current_turn.append(msg)
            
        if current_turn:
            turns.append(current_turn)
            
        # Manter os últimos 2 turnos intactos
        if len(turns) <= 2:
            return messages # Não tem o que comprimir com segurança
            
        recent_turns = turns[-2:]
        turns_to_compress = turns[:-2]
        
        summary_payload = ""
        for turn in turns_to_compress:
            for m in turn:
                content = m.get("content") or "chamada de ferramenta"
                summary_payload += f"[{m.get('role').upper()}]: {str(content)[:300]}...\n"
                
        summary_prompt = (
            "Você é o Módulo de Memória da Alana. Resuma tecnicamente o progresso desta missão até agora. "
            "Foque em fatos descobertos, sucessos de ferramentas e o estado atual do problema."
        )
        
        try:
            summary = await self.llm.generate_answer( 
                messages=[
                    {"role": "system", "content": summary_prompt},
                    {"role": "user", "content": f"HISTÓRICO PARA COMPRESSÃO:\n{summary_payload}"}
                ]
            )
            
            summary_msg = {
                "role": "system", 
                "content": f"RESUMO DO PROGRESSO (COMPRESSÃO): {summary}"
            }
            
            compressed_messages = [system_msg, objective_msg, summary_msg]
            for t in recent_turns:
                compressed_messages.extend(t)
                
            return compressed_messages
        except Exception as e:
            logger.error(f"Falha ao sumarizar contexto: {e}. Usando corte de segurança.")
            # Fallback seguro: apenas recarrega os últimos turnos
            safe_messages = [system_msg, objective_msg]
            for t in turns[-3:]:
                safe_messages.extend(t)
            return safe_messages
    async def think(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Delega o raciocínio para o motor de LLM interno do agente."""
        return await self.llm.think(prompt, system_prompt=system_prompt)
