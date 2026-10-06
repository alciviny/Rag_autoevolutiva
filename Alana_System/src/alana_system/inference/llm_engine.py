import os
import logging
import time
import json
import asyncio
from typing import Optional, List, Dict, Any, Generator
from litellm import Router, completion, acompletion
from alana_system.core.resources import gatekeeper

logger = logging.getLogger("alana.inference.engine")

class LLMEngine:
    """
    Engine de Inferência Unificada da Alana com Roteamento Híbrido.
    Prioriza APIs de Nuvem (Gemini/Groq) e faz fallback automático para Ollama Local.
    """

    def __init__(
        self,
        default_model: str = "ollama/llama3.1",
        context_window: int = 8192,
        base_url: Optional[str] = None
    ):
        self.local_model = os.getenv("DEFAULT_MODEL", default_model)
        self.context_window = context_window
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL") or os.getenv("OLLAMA_API_BASE") or "http://localhost:11434"
        self.sovereign_mode = os.getenv("SOVEREIGN_MODE", "true").lower() == "true"
        
        # Configuração do Roteador Inteligente (LiteLLM Router)
        # Ordem validada empiricamente por velocidade e disponibilidade.
        # Resultado do teste (25/07/2026): 6/11 provedores funcionando.
        model_list = []

        if not self.sovereign_mode:
            # --- TIER 1: Groq (mais rápido, ~0.89s, validado) ---
            groq_key = os.getenv("GROQ_API_KEY")
            if groq_key:
                model_list.append({
                    "model_name": "alana-core",
                    "litellm_params": {
                        "model": "groq/llama-3.3-70b-versatile",
                        "api_key": groq_key
                    }
                })
                model_list.append({
                    "model_name": "alana-core",
                    "litellm_params": {
                        "model": "groq/llama-3.1-8b-instant",
                        "api_key": groq_key
                    }
                })

            # --- TIER 2: GitHub Models (2s, validado) ---
            github_key = os.getenv("GITHUB_API_KEY")
            if github_key:
                # gpt-4o e Llama 3.3 validados. Phi-4 removido (42s inaceitável).
                for gh_model in ["gpt-4o", "Llama-3.3-70B-Instruct"]:
                    model_list.append({
                        "model_name": "alana-core",
                        "litellm_params": {
                            "model": f"github/{gh_model}",
                            "api_key": github_key
                        }
                    })

            # --- TIER 3: OpenRouter (1.9s, validado) ---
            openrouter_key = os.getenv("OPENROUTER_API_KEY")
            if openrouter_key:
                # Apenas gemma-4-26b-a4b-it:free validado. gemma-4-31b e llama-3.3:free removidos.
                model_list.append({
                    "model_name": "alana-core",
                    "litellm_params": {
                        "model": "openrouter/google/gemma-4-26b-a4b-it:free",
                        "api_key": openrouter_key
                    }
                })

            # --- TIER 4: Gemini (quota diária esgotada hoje, mantido pois reseta amanhã) ---
            gemini_key = os.getenv("GEMINI_API_KEY")
            if gemini_key:
                model_list.append({
                    "model_name": "alana-core",
                    "litellm_params": {
                        "model": "gemini/gemini-2.0-flash",
                        "api_key": gemini_key
                    }
                })

        # Em modo híbrido, o modelo local é o último destino de fallback.
        model_list.append({
            "model_name": "alana-core",
            "litellm_params": {
                "model": self.local_model,
                "api_base": self.base_url
            }
        })
        
        # latency-based: router aprende a preferir provedores mais rápidos automaticamente
        self.router = Router(model_list=model_list, num_retries=2, routing_strategy="latency-based-routing")
        
        mode_str = "SOBERANO (100% Local)" if self.sovereign_mode else "HÍBRIDO (Cloud -> Local)"
        logger.info(f"🤖 LLMEngine Ativa | Modo: {mode_str} | Modelos em cascata: {len(model_list)}")

    async def generate_answer(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        system_prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = "auto"
    ) -> Any:
        """
        Gera uma resposta assíncrona com suporte a retentativas e modo JSON.
        """
        if system_prompt:
            messages.insert(0, {"role": "system", "content": system_prompt})

        kwargs = {
            "model": "alana-core",
            "messages": messages,
            "temperature": temperature,
            # Modo profundo exige mais tokens para não truncar o JSON de 80+ entidades
            "max_tokens": 8192 if (metadata and metadata.get("deep_mode")) else 4096,
            "timeout": int(os.getenv("LLM_TIMEOUT", "300"))
        }

        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                kwargs["tool_choice"] = tool_choice

        # Modo JSON nativo
        if metadata and metadata.get("force_json"):
            kwargs["response_format"] = {"type": "json_object"}

        max_retries = 3
        for attempt in range(max_retries):
            try:
                start_time = time.perf_counter()
                
                if stream:
                    return self._generate_stream(kwargs)
                
                # Aguarda permissao da GPU (Inference Gatekeeper) - apenas se acabar caindo no Ollama, 
                # mas mantemos por segurança caso o tráfego da API seja pesado
                async with gatekeeper.get_semaphore():
                    response = await self.router.acompletion(**kwargs)
                    duration = time.perf_counter() - start_time
                    
                    modelo_usado = response.model if hasattr(response, "model") else "Desconhecido"
                    
                    # Se estivermos usando function calling nativo, retornamos o objeto completo
                    if tools:
                        logger.info(f"✅ LLM Sucesso (Function Calling) | Usou: {modelo_usado} | ⏱️ {duration:.2f}s")
                        return response

                    answer = response.choices[0].message.content
                    if answer:
                        answer = answer.strip()
                    else:
                        answer = ""
                    logger.info(f"✅ LLM Sucesso | Usou: {modelo_usado} | ⏱️ {duration:.2f}s")
                    return answer

            except Exception as e:
                logger.warning(f"⚠️ Falha na tentativa {attempt+1} do LLM: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt) # Backoff exponencial assíncrono
                else:
                    logger.error("❌ Erro crítico: Todas as tentativas de LLM em nuvem falharam.")
                    return "Desculpe, tive um problema de comunicação com o meu motor de pensamento. Todos os provedores de nuvem falharam neste momento."

    async def _generate_stream(self, kwargs: Dict[str, Any]):
        """Gerador assíncrono para respostas em tempo real (Streaming)."""
        try:
            kwargs["stream"] = True
            response = await self.router.acompletion(**kwargs)
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            logger.error(f"❌ Erro no streaming: {e}")
            yield " [Erro no processamento da resposta] "

    async def think(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Metodo de conveniencia para raciocinio rapido de um unico prompt."""
        messages = [{"role": "user", "content": prompt}]
        return await self.generate_answer(messages, system_prompt=system_prompt)

    def get_token_count(self, text: str) -> int:
        """
        Calcula a contagem real de tokens usando tiktoken (OpenAI/Gemini) 
        ou heurística precisa para Llama/Ollama.
        """
        try:
            import tiktoken
            # Usamos cl100k_base como padrão industrial (compatível com GPT-4 e Gemini)
            encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception as e:
            logger.warning(f"⚠️ Falha ao usar tiktoken: {e}. Usando heurística genérica.")
            return int(len(text) / 3.7) + 1
