import asyncio
import logging
import json
from datetime import datetime
import uuid
import os
from typing import Any, Optional, Callable, Dict, List, Tuple
from dataclasses import dataclass

from .core.engine import AgentEngine
from ..inference.llm_engine import LLMEngine

logger = logging.getLogger("alana.agent.orchestrator")

@dataclass
class MissionState:
    """O 'Quadro Negro' (Blackboard) onde os agentes compartilham informações."""
    objective: str
    namespace: str = "global"
    plan: str = ""
    technical_fact_sheet: str = ""
    internal_knowledge: str = ""
    proposed_solution: str = ""
    audit_report: str = ""
    is_complete: bool = False

class MultiAgentOrchestrator:
    """
    Controlador do 'Expert Lab'. 
    Coordena a colaboração entre especialistas garantindo isolamento por namespace.
    """

    def __init__(self, llm_engine: LLMEngine, query_engine: Any, deep_search_agent: Any, experience_store: Any = None):
        self.llm = llm_engine
        self.query_engine = query_engine
        self.experience_store = experience_store
        self.engineer = AgentEngine(
            query_engine=query_engine, 
            deep_search_agent=deep_search_agent,
            llm=llm_engine
        )

    async def run_complex_mission(
        self, 
        mission: str, 
        namespace: str = "global", 
        callback: Callable = None
    ):
        """
        Executa o fluxo de trabalho industrial autonômo: Planejar -> Pesquisar -> Resolver -> Auditar.
        """
        try:
            state = MissionState(objective=mission, namespace=namespace)
            
            # 1. ORCHESTRATOR: Recall e Planejamento
            await self._emit_thought("Orchestrator", f"Iniciando missão industrial no namespace '{namespace}'...", callback)
            
            past_lessons = ""
            if self.experience_store:
                await self._emit_thought("Orchestrator", "Consultando memória episódica para lições aprendidas...", callback)
                experiences = self.experience_store.recall_experiences(mission, namespace=namespace)
                if experiences:
                    past_lessons = "\n".join([f"- {e['mission_name']}: {e['winning_strategy']}" for e in experiences])
                    await self._emit_thought("Orchestrator", f"Encontrei {len(experiences)} lições relevantes do passado.", callback)

            plan_result = await self._plan_mission(mission, past_lessons)
            state.plan = plan_result.get("plan", "1. Executar missão.")
            requires_research = plan_result.get("requires_internal_research", True)

            # 2. CICLO DE EXECUÇÃO RECURSIVO (Stark Mode)
            max_retries = 3
            audit_passed = False
            for attempt in range(1, max_retries + 1):
                await self._emit_thought("Orchestrator", f"Iniciando Ciclo de Engenharia {attempt}/{max_retries}...", callback)
                
                # Librarian: Só pesquisa se necessário
                if requires_research:
                    await self._emit_thought("Librarian", "Pesquisando e consolidando fichas técnicas...", callback)
                    search_res = await self.query_engine.query(mission, namespace=namespace)
                    state.internal_knowledge = search_res.get("context_text", "")
                    state.technical_fact_sheet = await self._librarian_work(state.internal_knowledge, mission)
                else:
                    await self._emit_thought("Librarian", "Pesquisa interna ignorada por não ser necessária.", callback)
                    state.technical_fact_sheet = "Nenhuma ficha técnica necessária para esta missão."
                
                # Engineer: Execução Técnica Focada
                await self._emit_thought("Engineer", "Iniciando implementação baseada na ficha técnica...", callback)
                state.proposed_solution = await self.engineer.run_mission(
                    f"OBJETIVO: {mission}\nPLANO: {state.plan}\nFICHA TÉCNICA: {state.technical_fact_sheet}\nHISTÓRICO DE AUDITORIA: {state.audit_report}",
                    namespace=namespace,
                    event_callback=self._wrap_engineer_callback(callback)
                )

                # 4. AUDITOR: Verificação de Qualidade Stark
                await self._emit_thought("Auditor", "Analisando rigorosamente a solução...", callback)
                audit_data = await self._audit_solution(
                    solution=state.proposed_solution, 
                    original_mission=mission,
                    plan=state.plan,
                    technical_fact_sheet=state.technical_fact_sheet
                )
                state.audit_report = audit_data.get("reason", "Análise inconclusiva.")
                
                if audit_data.get("status") == "PASS":
                    audit_passed = True
                    await self._emit_thought("Orchestrator", "✅ Solução aprovada pelo Auditor de Qualidade.", callback)
                    # 5. IMORTALIZAÇÃO: Salva a lição aprendida (Elite Mode)
                    if self.experience_store:
                        await self._persist_success_lesson(state, mission, namespace, callback)
                    break
                else:
                    await self._emit_thought("Orchestrator", f"⚠️ Auditor reprovou (Tentativa {attempt}). Corrigindo curso...", callback)
                    if attempt == max_retries:
                        await self._emit_thought("Orchestrator", "❌ Limite de correções atingido. Entregando melhor esforço.", callback)

            await self._emit_thought("Orchestrator", "Missão Industrial Finalizada.", callback)
            
            # Persist the mission report
            mission_id = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{uuid.uuid4().hex[:6]}"
            mission_dir = f"data/missions/{namespace}"
            os.makedirs(mission_dir, exist_ok=True)
            report_data = {
                "id": mission_id,
                "mission": mission,
                "solution": state.proposed_solution,
                "audit": state.audit_report,
                "plan": state.plan,
                "namespace": namespace,
                "timestamp": datetime.now().isoformat(),
                "status": "completed" if audit_passed else "failed",
                "audit_status": "PASS" if audit_passed else "FAIL",
            }
            with open(os.path.join(mission_dir, f"{mission_id}.json"), "w", encoding="utf-8") as f:
                json.dump(report_data, f, ensure_ascii=False, indent=2)

            if callback:
                await callback(
                    "mission_complete" if audit_passed else "mission_failed",
                    {"message": "Missão aprovada na auditoria." if audit_passed else "Missão reprovada na auditoria após três tentativas.", "audit_status": report_data["audit_status"]},
                )

            return report_data
        except Exception as e:
            logger.exception(f"💥 Falha CRÍTICA na missão [{namespace}]: {e}")
            await self._emit_thought("Orchestrator", f"❌ Falha crítica no sistema: {str(e)}", callback)
            return {"status": "error", "message": str(e)}

    async def _plan_mission(self, mission: str, past_lessons: str = "") -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": f"""Você é o Gerente do Lab Alana. Analise a missão e decida se precisamos pesquisar o banco de dados interno (RAG) para encontrar manuais ou código da empresa, ou se é apenas uma missão matemática/geral.
            {f'LIÇÕES DO PASSADO (APRENDA COM ISSO): {past_lessons}' if past_lessons else ''}"""},
            {"role": "user", "content": mission}
        ]
        
        tools = [{
            "type": "function",
            "function": {
                "name": "submit_plan",
                "description": "Submete o plano estratégico da missão.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "plan": {
                            "type": "string",
                            "description": "O plano técnico de 3 passos."
                        },
                        "requires_internal_research": {
                            "type": "boolean",
                            "description": "True se a missão precisar consultar dados específicos do projeto atual/banco de dados."
                        }
                    },
                    "required": ["plan", "requires_internal_research"]
                }
            }
        }]
        
        try:
            resp = await self.llm.generate_answer(messages, tools=tools, tool_choice={"type": "function", "function": {"name": "submit_plan"}})
            msg = resp.choices[0].message
            if getattr(msg, "tool_calls", None):
                args = json.loads(msg.tool_calls[0].function.arguments)
                return args
            return {"plan": "1. Executar missão", "requires_internal_research": True}
        except Exception as e:
            logger.error(f"Erro no planejamento: {e}")
            return {"plan": "Plano padrão", "requires_internal_research": True}

    async def _librarian_work(self, raw_knowledge: str, mission: str) -> str:
        """O Bibliotecário destila o RAG em uma Ficha Técnica estruturada."""
        if not raw_knowledge:
            return "Nenhuma documentação interna encontrada. Proceder com conhecimento base e pesquisa externa."
            
        prompt = f"""Você é o Bibliotecário Técnico da Alana. Seu trabalho é extrair os FATOS CRÍTICOS e ESPECIFICAÇÕES da documentação para o Engenheiro.
        MISSÃO: {mission}
        DOCUMENTAÇÃO BRUTA: {raw_knowledge}
        
        GERE UMA FICHA TÉCNICA CONTENDO:
        1. Constantes e Configurações identificadas.
        2. Restrições e Avisos de Segurança.
        3. APIs ou Métodos relevantes.
        (Seja conciso e estritamente técnico)"""
        
        return await self.llm.think(prompt)

    async def _persist_success_lesson(self, state: MissionState, mission: str, namespace: str, callback: Optional[Callable]):
        """Gera um resumo da estratégia vencedora e salva na Memória Episódica."""
        await self._emit_thought("Orchestrator", "Imortalizando estratégia vencedora na memória episódica...", callback)
        
        prompt = f"""Resuma a estratégia vencedora para esta missão em uma única frase técnica e direta.
        MISSÃO: {mission}
        SOLUÇÃO: {state.proposed_solution}
        RESUMO (Max 30 palavras):"""
        
        strategy_summary = await self.llm.think(prompt)
        
        self.experience_store.save_experience(
            mission_name=mission[:50],
            description=mission,
            strategy=strategy_summary,
            namespace=namespace
        )

    async def _audit_solution(self, solution: str, original_mission: str, plan: str = "", technical_fact_sheet: str = "") -> Dict[str, Any]:
        """Audita a solução usando Function Calling rigoroso."""
        messages = [
            {"role": "system", "content": f"""Você é o Auditor de Qualidade Sênior da Alana.
            Sua análise deve ser impiedosa. Procure por:
            - Falhas de lógica, bugs de segurança ou inconsistências.
            - Desvios do objetivo original ou do plano aprovado.
            - Violação das regras estipuladas na Ficha Técnica.
            
            PLANO DE AÇÃO DEFINIDO:
            {plan}
            
            RESTRIÇÕES (FICHA TÉCNICA):
            {technical_fact_sheet}"""},
            {"role": "user", "content": f"Missão: {original_mission}\nSolução Proposta: {solution}"}
        ]
        
        tools = [{
            "type": "function",
            "function": {
                "name": "submit_audit",
                "description": "Submete o veredito final da auditoria.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "enum": ["PASS", "FAIL"],
                            "description": "PASS se aprovado, FAIL se reprovado."
                        },
                        "reason": {
                            "type": "string",
                            "description": "Justificativa detalhada."
                        }
                    },
                    "required": ["status", "reason"]
                }
            }
        }]
        
        try:
            resp = await self.llm.generate_answer(messages, tools=tools, tool_choice={"type": "function", "function": {"name": "submit_audit"}})
            msg = resp.choices[0].message
            if getattr(msg, "tool_calls", None):
                args = json.loads(msg.tool_calls[0].function.arguments)
                return args
            return {"status": "FAIL", "reason": "LLM não respeitou o contrato de tool calling."}
        except Exception as e:
            logger.error(f"Falha ao processar resposta do Auditor: {e}")
            return {"status": "FAIL", "reason": f"Erro interno no motor de auditoria: {str(e)}"}

    async def _emit_thought(self, agent: str, thought: str, callback: Optional[Callable]):
        if callback:
            await callback("thought", {"agent": agent, "content": thought})
        logger.info(f"[{agent}] {thought}")

    def _wrap_engineer_callback(self, original_callback: Optional[Callable]):
        if not original_callback: return None
        async def wrapped(event_type: str, data: Any):
            if event_type == "thought":
                await original_callback("thought", {"agent": "Engineer", "content": data["content"]})
            elif event_type == "mission_complete":
                # O Orquestrador bloqueia o mission_complete do engenheiro para não encerrar o frontend cedo
                pass
            else:
                await original_callback(event_type, data)
        return wrapped
