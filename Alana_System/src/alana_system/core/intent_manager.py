import logging
import asyncio
import json
from typing import Dict, Any, Optional

logger = logging.getLogger("alana.core.intent_manager")

class IntentManager:
    """
    Orquestra o processamento de intencoes de voz.
    Desacopla o roteador da logica de negocio de cada funcionalidade.
    """
    def __init__(self, app_state):
        self.state = app_state

    async def process_intent(self, transcription: str, namespace: str) -> Optional[Dict[str, Any]]:
        """
        Analisa a transcricao e despacha para o handler correto.
        Inclui fallback para classificação semântica via LLM (P5 Auditoria).
        """
        text = transcription.lower()
        
        # 1. Handlers de Atalho (Keywords Rápidas)
        wf_res = await self._handle_workflow(text, namespace)
        if wf_res: return wf_res
        
        tel_res = await self._handle_telemetry(text, namespace)
        if tel_res: return tel_res
        
        gen_res = await self._handle_genius(text, namespace)
        if gen_res: return gen_res
        
        # 2. Fallback: Classificação Semântica Profunda (O Cérebro da Alana)
        return await self._classify_and_execute(transcription, namespace)

    async def _classify_and_execute(self, transcription: str, namespace: str) -> Optional[Dict[str, Any]]:
        """Usa LLM para classificar intenções complexas que escaparam dos atalhos."""
        llm = self.state.llm_engine
        
        prompt = f"""Você é o Cérebro de Intenções da Alana. Classifique a fala do usuário:
        CATEGORIAS:
        - MISSION: Iniciar uma tarefa complexa, projeto, conserto, análise profunda ou missão autônoma.
        - SEARCH: Pesquisa externa, preços, notícias.
        - SAVE: Memorizar instruções, dados técnicos.
        - QUERY: Pergunta técnica sobre documentos ou visão.
        - NONE: Conversa casual ou não identificada.

        USUÁRIO: "{transcription}"
        Responda APENAS o JSON: {{"intent": "CATEGORIA", "reason": "porque"}}"""

        try:
            resp = await llm.generate_answer(messages=[{"role": "system", "content": prompt}], metadata={"force_json": True})
            data = json.loads(resp.strip())
            intent = data.get("intent", "NONE")
            
            if intent == "MISSION":
                from alana_system.utils.background_tasks import task_manager
                # Dispara a missão complexa no orquestrador via TaskManager para resiliência
                task_id = task_manager.run_task(
                    self.state.orchestrator.run_complex_mission,
                    mission=transcription,
                    namespace=namespace,
                    name=f"voice_mission_{namespace}"
                )
                return {
                    "intent": "MISSION", 
                    "answer": f"Entendido. Iniciei uma missão autônoma para: {transcription}. Vou processar isso agora.",
                    "source": "orchestrator",
                    "task_id": task_id
                }
            
            if intent == "SEARCH":
                res = await self.state.deep_search_agent.perform_deep_search(transcription, namespace=namespace)
                return {"intent": "SEARCH", "answer": res.get("report"), "source": "web_research"}
            
            if intent == "SAVE":
                graph_schema = await self.state.query_engine.entity_extractor.extract_graph(transcription)
                if graph_schema.entities or graph_schema.relations:
                    intelligence = getattr(self.state.query_engine, "intelligence", None)
                    if intelligence and hasattr(intelligence, "reconcile_graph"):
                        await intelligence.reconcile_graph(graph_schema, namespace)
                    self.state.query_engine.graph_store.add_knowledge(graph_schema, source_doc="wearable_voice", page_number=1, namespace=namespace)
                    return {"intent": "SAVE", "answer": "Conhecimento técnico indexado no seu Grafo.", "source": "knowledge_graph"}
            
            if intent == "QUERY":
                # Fallback para o motor de busca técnica
                answer = await self.state.query_engine.answer_query(transcription, namespace=namespace)
                return {"intent": "QUERY", "answer": answer, "source": "local_brain"}

        except Exception as e:
            logger.error(f"Erro na classificação profunda: {e}")
        
        return None

    async def _handle_workflow(self, text: str, namespace: str):
        wf_manager = self.state.workflow_manager
        sensory = self.state.sensory_manager
        session = wf_manager.get_session(namespace)
        
        if "iniciar guia" in text or "iniciar manual" in text:
            # Extrai o nome ignorando preposicoes e saudacoes comuns
            raw_name = text.replace("iniciar guia", "").replace("iniciar manual", "").strip()
            wf_name = raw_name.replace("de", "").replace("do", "").replace("da", "").strip().replace(" ", "_")
            
            instruction = wf_manager.start_session(namespace, wf_name)
            if instruction:
                return {"intent": "WORKFLOW", "answer": f"Iniciando guia {wf_name}. {instruction}"}
            return {"intent": "WORKFLOW", "answer": f"Não encontrei o manual '{wf_name}'."}

        if session and any(kw in text for kw in ["próximo", "proximo", "concluí", "concluido", "feito"]):
            step = session.get_current_step()
            if step and step.validation_prompt:
                last_vision = sensory.get_last_vision(namespace)
                if last_vision and "raw_bytes" in last_vision:
                    is_valid = await self.state.vision_processor.validate_compliance(last_vision["raw_bytes"], step.validation_prompt)
                    if not is_valid:
                        return {"intent": "WORKFLOW", "answer": step.retry_message}
            
            session.next_step()
            wf_manager.save_progress(namespace)
            
            if session.is_completed:
                wf_manager.stop_session(namespace)
                return {"intent": "WORKFLOW", "answer": "Excelente! Procedimento concluído com sucesso."}
            
            return {"intent": "WORKFLOW", "answer": f"Validado. Próximo passo: {session.get_current_step().instruction}"}
        return None

    async def _handle_telemetry(self, text: str, namespace: str):
        if any(kw in text for kw in ["registre este valor", "registre o valor", "salve esta medição", "anota aí"]):
            last_vision = self.state.sensory_manager.get_last_vision(namespace)
            if last_vision and "raw_bytes" in last_vision:
                data = await self.state.vision_processor.extract_telemetry(last_vision["raw_bytes"])
                if "error" not in data:
                    self.state.query_engine.graph_store.add_telemetry_reading(
                        entity_name=data["entity"], value=data.get("value"),
                        unit=data.get("unit", ""), raw_reading=data.get("raw", ""), namespace=namespace
                    )
                    return {"intent": "LOGGING", "answer": f"Registrei {data.get('raw')} para {data['entity']}."}
        return None

    async def _handle_genius(self, text: str, namespace: str):
        # Explainer
        if any(kw in text for kw in ["o que diz aqui", "traduza isso", "explique isso"]):
            last_vision = self.state.sensory_manager.get_last_vision(namespace)
            if last_vision and "raw_bytes" in last_vision:
                explanation = await self.state.vision_processor.explain_concept(last_vision["raw_bytes"], text)
                return {"intent": "EXPLAINER", "answer": explanation}
        
        # Genius Modes
        genius_keywords = {
            "first_principles": ["desconstrua", "primeiros princípios"],
            "reverse_engineering": ["engenharia reversa", "como funciona"],
            "substitution": ["como eu substituo", "o que uso no lugar"],
            "utility": ["visão utilitária", "o que posso usar como"],
            "math": ["resolva esse cálculo", "calcule"],
            "prototyping": ["gere o código", "prototipagem"],
            "synapse": ["conecte isso", "sinapse", "o que eu já sei"]
        }
        
        for mode, keywords in genius_keywords.items():
            if any(kw in text for kw in keywords):
                last_vision = self.state.sensory_manager.get_last_vision(namespace)
                if last_vision:
                    if mode == "synapse":
                        query_engine = self.state.query_engine
                        rag_context = await query_engine.query(f"O que eu tenho documentado sobre: {last_vision['content']}", namespace=namespace)
                        prompt = f"O usuario ve: {last_vision['content']}. Contexto: {rag_context}. Faça a sinapse."
                        analysis = await self.state.llm_engine.think(prompt)
                    else:
                        analysis = await self.state.vision_processor.analyze_genius(last_vision["raw_bytes"], mode, text)
                    return {"intent": f"GENIUS_{mode.upper()}", "answer": analysis}
        return None
