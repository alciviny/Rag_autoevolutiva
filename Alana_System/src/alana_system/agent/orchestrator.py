import asyncio
import logging
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
        callback: Callable = None,
        approval_queue: asyncio.Queue = None
    ):
        """
        Executa o fluxo de trabalho industrial: Planejar -> Aprovar -> Pesquisar -> Resolver -> Auditar.
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

            state.plan = await self._plan_mission(mission, past_lessons)

            # 2. HUMAN-IN-THE-LOOP (H-4 Fix)
            if approval_queue:
                await self._emit_thought("Orchestrator", "Aguardando aprovação humana para o plano...", callback)
                if callback:
                    await callback("awaiting_approval", {"command": "Executar Plano de Missão"})
                
                # Aguarda resposta da fila
                try:
                    action = await asyncio.wait_for(approval_queue.get(), timeout=300) # 5 min timeout
                    if action == "abort":
                        await self._emit_thought("Orchestrator", "Missão abortada pelo usuário.", callback)
                        return {"status": "aborted"}
                    logger.info("✅ Missão aprovada pelo usuário.")
                except asyncio.TimeoutError:
                    await self._emit_thought("Orchestrator", "Tempo de espera esgotado. Abortando por segurança.", callback)
                    return {"status": "timeout"}

            # 3. CICLO DE EXECUÇÃO RECURSIVO (Stark Mode)
            max_retries = 3
            for attempt in range(1, max_retries + 1):
                await self._emit_thought("Orchestrator", f"Iniciando Ciclo de Engenharia {attempt}/{max_retries}...", callback)
                
                # Librarian: Especialista em RAG e Consolidação (Elite Mode)
                await self._emit_thought("Librarian", "Pesquisando e consolidando fichas técnicas...", callback)
                search_res = await self.query_engine.query(mission, namespace=namespace)
                state.internal_knowledge = search_res.get("context_text", "")
                state.technical_fact_sheet = await self._librarian_work(state.internal_knowledge, mission)
                
                # Engineer: Execução Técnica Focada
                await self._emit_thought("Engineer", "Iniciando implementação baseada na ficha técnica...", callback)
                state.proposed_solution = await self.engineer.run_mission(
                    f"OBJETIVO: {mission}\nPLANO: {state.plan}\nFICHA TÉCNICA: {state.technical_fact_sheet}\nHISTÓRICO DE AUDITORIA: {state.audit_report}",
                    namespace=namespace,
                    event_callback=self._wrap_engineer_callback(callback)
                )

                # 4. AUDITOR: Verificação de Qualidade Stark
                await self._emit_thought("Auditor", "Analisando rigorosamente a solução...", callback)
                audit_data = await self._audit_solution(state.proposed_solution, mission)
                state.audit_report = audit_data.get("reason", "Análise inconclusiva.")
                
                if audit_data.get("status") == "PASS":
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
            
            return {
                "solution": state.proposed_solution,
                "audit": state.audit_report,
                "plan": state.plan,
                "namespace": namespace
            }
        except Exception as e:
            logger.exception(f"💥 Falha CRÍTICA na missão [{namespace}]: {e}")
            await self._emit_thought("Orchestrator", f"❌ Falha crítica no sistema: {str(e)}", callback)
            return {"status": "error", "message": str(e)}

    async def _plan_mission(self, mission: str, past_lessons: str = "") -> str:
        messages = [
            {"role": "system", "content": f"""Você é o Gerente do Lab Alana. Crie um plano técnico de 3 passos para a missão.
            Seja pragmático e focado em engenharia industrial.
            {f'LIÇÕES DO PASSADO (APRENDA COM ISSO): {past_lessons}' if past_lessons else ''}"""},
            {"role": "user", "content": mission}
        ]
        return await self.llm.generate_answer(messages)

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

    async def _audit_solution(self, solution: str, original_mission: str) -> Dict[str, Any]:
        """Audita a solução usando um contrato JSON rigoroso."""
        import json
        messages = [
            {"role": "system", "content": """Você é o Auditor de Qualidade Sênior da Alana.
            Sua análise deve ser impiedosa. Procure por:
            - Falhas de lógica, bugs de segurança ou inconsistências.
            - Desvios do objetivo original ou do plano aprovado.
            
            RESPONDA APENAS UM JSON NO FORMATO:
            {
                "status": "PASS" ou "FAIL",
                "reason": "Sua análise técnica detalhada aqui."
            }"""},
            {"role": "user", "content": f"Missão: {original_mission}\nSolução Proposta: {solution}"}
        ]
        
        try:
            resp = await self.llm.generate_answer(messages, metadata={"force_json": True})
            # Limpeza básica caso o LLM injete markdown
            resp = resp.strip().strip("`").replace("json\n", "").strip()
            return json.loads(resp)
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
            else:
                await original_callback(event_type, data)
        return wrapped
