import logging
import base64
import asyncio
from typing import Optional, Dict, Any, List, Union
from litellm import acompletion
from alana_system.core.config import VISION_MODEL_CLOUD, VISION_MODEL_LOCAL, SOVEREIGN_MODE
from alana_system.core.resources import gatekeeper

logger = logging.getLogger("alana.iot.vision")

class VisionProcessor:
    """
    Processador de Imagem Industrial.
    Realiza analise multimodal assincrona para dispositivos IoT.
    """
    
    def __init__(self, model_name: Optional[str] = None):
        # Determina o modelo inicial baseado no Modo Soberano
        self.cloud_model = VISION_MODEL_CLOUD
        self.local_model = VISION_MODEL_LOCAL
        self.sovereign = SOVEREIGN_MODE
        
        self.model_name = model_name or (self.local_model if self.sovereign else self.cloud_model)
        logger.info(f"👁️ VisionProcessor Inicializado | Modo Soberano: {self.sovereign} | Modelo: {self.model_name}")

    async def analyze_image(self, image_input: Union[bytes, List[bytes]], prompt: str = "Descreva detalhadamente esta imagem.") -> str:
        """Analise multimodal assincrona com suporte a multiplas imagens (Elite Mode)."""
        try:
            images = [image_input] if isinstance(image_input, bytes) else image_input
            
            content_list = [{"type": "text", "text": prompt}]
            
            for img_bytes in images:
                mime_type = self._get_mime_type(img_bytes)
                
                # Codificacao Base64 em thread separada
                def _encode(b):
                    return base64.b64encode(b).decode("utf-8")
                
                base64_image = await asyncio.to_thread(_encode, img_bytes)
                
                content_list.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}
                })
            
            messages = [{"role": "user", "content": content_list}]
            
            logger.info(f"📡 [Vision] Analise Multi-Imagem ({len(images)} imagens) via {self.model_name}")
            
            try:
                async with gatekeeper.get_semaphore():
                    response = await acompletion(
                        model=self.model_name,
                        messages=messages,
                        temperature=0.1
                    )
                    res_text = response.choices[0].message.content.strip()
                    logger.info(f"--- Resposta da IA: {res_text[:100]}... ---")
                    return res_text
            except Exception as cloud_err:
                # Se falhar a nuvem e nao estivermos ja no local, tenta o local (Fallback)
                if not self.sovereign and self.model_name == self.cloud_model:
                    logger.warning(f"⚠️ Falha na Nuvem: {cloud_err}. Acionando Visao Local (Soberania)...")
                    response = await acompletion(
                        model=self.local_model,
                        messages=messages,
                        temperature=0.1
                    )
                    return response.choices[0].message.content.strip()
                raise cloud_err
            
        except Exception as e:
            logger.error(f"❌ Falha na analise de visao: {e}")
            return f"Nao consegui processar as imagens. Erro: {str(e)}"

    def _safe_json_extract(self, text: str) -> Dict[str, Any]:
        """Extrai JSON de forma robusta, lidando com Markdown e lixo de texto."""
        import json
        import re
        try:
            # Tenta encontrar bloco JSON
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(text)
        except Exception:
            logger.warning(f"Falha ao extrair JSON de: {text[:100]}...")
            return {"error": "invalid_format"}

    async def validate_compliance(self, image_bytes: bytes, condition_prompt: str) -> bool:
        """Valida se uma condicao tecnica e atendida na imagem."""
        prompt = f"""Analise a imagem e verifique se a seguinte condicao tecnica e verdadeira: "{condition_prompt}"
        Responda APENAS um JSON: {{"confirmed": true/false, "reason": "explicacao curta"}}"""
        
        try:
            resp = await self.analyze_image(image_bytes, prompt=prompt)
            data = self._safe_json_extract(resp)
            return data.get("confirmed", False)
        except Exception as e:
            logger.error(f"Erro na validacao de conformidade: {e}")
            return False

    async def extract_telemetry(self, image_bytes: bytes) -> Dict[str, Any]:
        """Extrai dados numericos e unidades de visores e instrumentos."""
        prompt = """Analise o visor ou instrumento na imagem e extraia a leitura atual.
        Seja preciso com numeros e unidades (V, A, Hz, kg, bar, etc).
        Responda APENAS um JSON: {"entity": "nome do equipamento", "value": 123.4, "unit": "unidade", "raw": "leitura completa"}"""
        
        try:
            resp = await self.analyze_image(image_bytes, prompt=prompt)
            return self._safe_json_extract(resp)
        except Exception as e:
            logger.error(f"Erro na extracao de telemetria: {e}")
            return {"error": str(e)}

    async def explain_concept(self, image_bytes: bytes, user_query: str = "O que diz aqui?") -> str:
        """Traduz e explica conceitos tecnicos ou manuais estrangeiros em linguagem simples."""
        prompt = f"""Analise o texto ou diagrama na imagem. 
        1. Traduza para o Portugues se estiver em outro idioma.
        2. Explique o significado de forma simples, usando analogias se o conceito for tecnico.
        3. Diga como isso pode ser util para quem gosta de criar coisas e inventar.
        Pergunta do usuario: {user_query}
        Responda de forma amigavel e didatica."""
        
        return await self.analyze_image(image_bytes, prompt=prompt)

    async def analyze_genius(self, image_bytes: bytes, mode: str, query: str = "") -> str:
        """
        Executa analises de alto nivel (Nivel Stark/Sanchez).
        Modos: first_principles, reverse_engineering, substitution, utility, math, prototyping
        """
        prompts = {
            "first_principles": "Analise este problema sob a ótica de Primeiros Princípios. 1. Identifique as verdades fundamentais (leis da física/lógica). 2. Desconstrua o objeto até estas verdades. 3. Proponha uma solução original do zero.",
            "reverse_engineering": "Inicie o protocolo de Engenharia Reversa. Identifique: 1. Componentes visíveis. 2. Provável fluxo de sinal/energia. 3. Protocolos de comunicação inferidos (ex: I2C, SPI, UART).",
            "substitution": f"Protocolo de Substituição Genial. Necessidade: {query}. Analise o que está disponível e sugira um substituto funcional usando o que há no ambiente.",
            "utility": "Visão Utilitária Ativada. Identifique componentes nesta imagem que podem ser reaproveitados como: Dissipadores, Suportes, Isolantes ou Conectores.",
            "math": "Extração e Resolução Matemática. Identifique fórmulas, medidas ou diagramas. Resolva o problema passo a passo (Chain-of-Thought).",
            "prototyping": "Geração de Protótipo Industrial. Baseado no circuito visualizado, gere o código C++/Python correspondente e forneça o diagrama de pinagem esperado."
        }
        
        selected_prompt = prompts.get(mode, "Analise este objeto de forma genial.")
        full_prompt = f"{selected_prompt}\nContexto adicional: {query}\nResponda como um engenheiro brilhante e inventivo."
        
        try:
            return await self.analyze_image(image_bytes, prompt=full_prompt)
        except Exception as e:
            logger.error(f"Erro no modo Genius ({mode}): {e}")
            return f"Minha analise de {mode} falhou. Verifique a iluminacao."

    def _get_mime_type(self, data: bytes) -> str:
        """Identifica o formato da imagem via assinaturas binarias."""
        if data.startswith(b'\xff\xd8\xff'):
            return "image/jpeg"
        elif data.startswith(b'\x89PNG\r\n\x1a\n'):
            return "image/png"
        elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
            return "image/webp"
        return "image/jpeg" # Fallback conservador
