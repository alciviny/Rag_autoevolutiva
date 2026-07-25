import json
import logging
import re
from typing import List, Dict, Any, Literal, Optional, get_args
from pydantic import BaseModel, Field, ValidationError

from ..inference.llm_engine import LLMEngine

logger = logging.getLogger(__name__)

# Modelos de Esquema (Contratos Técnicos Profissionais)
EntityType = str # Flexibilidade total para não perder dados
PREFERRED_TYPES = [
    "Conceito", "Sistema", "Equação", "Teorema", 
    "Algoritmo", "Variável", "Parâmetro", "Componente",
    "Atributo", "Processo", "Evento", "Pessoa", "Organização",
    "Sintaxe", "Diretiva", "Biblioteca", "Framework", "Paradigma",
    "Declaração", "Código", "Exemplo", "Hardware", "Software"
]

# Mapa de Normalização de Tipos (Robustez Empresarial)
TYPE_MAPPING = {
    "Variável/Parâmetro": "Variável",
    "Variável Elétrica": "Variável",
    "Tecnologia/Ferramenta": "Tecnologia",
    "Pessoas": "Pessoa",
    "Organizações": "Organização",
    "Software": "Tecnologia",
    "Hardware": "Componente",
    "Método": "Algoritmo",
    "Lei": "Teorema",
    "Princípio": "Teorema",
    "Equação Matemática": "Equação",
    "Declaração de variável": "Variável",
    "Declaração de Função": "Algoritmo",
    "Snippet": "Código"
}

class EntitySchema(BaseModel):
    name: str = Field(..., min_length=1)
    type: EntityType
    description: str = Field(default="")

class RelationSchema(BaseModel):
    subject: str
    predicate: str
    object: str

class KnowledgeGraphSchema(BaseModel):
    entities: List[EntitySchema]
    relations: List[RelationSchema]

class EntityExtractor:
    def __init__(self, llm: LLMEngine, use_spacy: bool = False):
        self.llm = llm
        # O suporte ao spaCy foi descontinuado em favor da extração puramente via LLM-First
        self.use_spacy = False
        self.nlp = None

    async def extract_graph(self, text: str, mode: str = "fast", domain: str = "Tecnologia") -> KnowledgeGraphSchema:
        """
        Extração Profunda de Grafos de Conhecimento.
        Migrado de spaCy-First para LLM-First com suporte a modos Híbridos (fast | deep).
        """
        if not text.strip():
            return KnowledgeGraphSchema(entities=[], relations=[])

        # O Cérebro: Extração Técnica via LLM (Zero-Shot Technical NER)
        prompt = self._build_deep_prompt(domain) if mode == "deep" else self._build_fast_prompt(domain)
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"TEXTO PARA EXTRAÇÃO TÉCNICA:\n{text}"}
        ]

        try:
            resposta_bruta = await self.llm.generate_answer(
                messages=messages, 
                metadata={"force_json": True}
            )
            
            data = self._safe_json_load(resposta_bruta)
            
            # 1. Processamento de Entidades (Validação de Esquema)
            valid_entities = []
            seen_entities = set()
            
            entities_list = data.get("entities", [])
            if not isinstance(entities_list, list):
                entities_list = []
                
            for ent_data in entities_list:
                try:
                    # BLINDAGEM: Se a IA mandar uma string pura em vez de objeto
                    if isinstance(ent_data, str):
                        ent_data = {"name": ent_data, "type": "Conceito", "description": ""}
                    
                    if not isinstance(ent_data, dict):
                        continue
                        
                    # Normalização de Tipo Inteligente (Auto-Correção Empresarial)
                    raw_type = ent_data.get("type", "Conceito")
                    if not isinstance(raw_type, str):
                        raw_type = "Conceito"
                    
                    # 1. Resolve tipos compostos (ex: "Função/Algoritmo")
                    if "/" in raw_type:
                        parts = [p.strip() for p in raw_type.split("/")]
                        for part in parts:
                            if part in PREFERRED_TYPES or part in TYPE_MAPPING:
                                raw_type = part
                                break
                    
                    # 2. Aplica Mapeamento Estático (Case-Insensitive)
                    raw_type_lower = str(raw_type).lower()
                    mapped_type = None
                    for k, v in TYPE_MAPPING.items():
                        if raw_type_lower == k.lower():
                            mapped_type = v
                            break
                            
                    if mapped_type:
                        ent_data["type"] = mapped_type
                    else:
                        # Se não for preferencial, aceitamos mas garantimos capitalização
                        ent_data["type"] = str(raw_type).capitalize()
                    
                    # Validação de dados básicos (Pydantic agora aceita qualquer string em type)
                    ent = EntitySchema(**ent_data)
                    
                    # Limpeza de nome (Remove pontuação ou fragmentos de OCR no início/fim)
                    ent.name = self._clean_entity_name(ent.name)
                    
                    # FILTRO DE RELEVÂNCIA (Qualidade Industrial)
                    if not ent.name or self._is_trash(ent.name): 
                        continue
                    
                    # Filtra entidades vazias, mas preserva Siglas Técnicas vitais (ex: CPU, API, RAM)
                    if not ent.description.strip():
                        # Se não tem descrição e tem menos de 4 letras e NÃO está em maiúsculo, descarta.
                        # Caso contrário (é uma sigla ou um termo mais longo), mantemos.
                        if len(ent.name) < 4 and not ent.name.isupper():
                            continue
                    
                    if ent.name.lower() not in seen_entities:
                        valid_entities.append(ent)
                        seen_entities.add(ent.name.lower())
                except Exception as e:
                    logger.warning(f"⚠️ Erro ao processar entidade individual: {e} | Dados: {ent_data}")

            # 2. Processamento de Relações
            valid_relations = []
            valid_entity_names = {e.name.lower() for e in valid_entities}
            
            relations_list = data.get("relations", [])
            if not isinstance(relations_list, list):
                relations_list = []
                
            for rel_data in relations_list:
                try:
                    if not isinstance(rel_data, dict):
                        continue
                        
                    rel = RelationSchema(**rel_data)
                    
                    # Normalização de Nomes nas Relações
                    rel.subject = self._clean_entity_name(rel.subject)
                    rel.object = self._clean_entity_name(rel.object)
                    
                    # FILTRO ANTI-NÓS ÓRFÃOS (Integridade do Grafo)
                    if not rel.subject or not rel.object:
                        continue
                        
                    if rel.subject.lower() not in valid_entity_names or rel.object.lower() not in valid_entity_names:
                        # Se a entidade foi deletada (por ser lixo ou ter sido filtrada), a relação também cai.
                        continue
                        
                    valid_relations.append(rel)
                except ValidationError as ve:
                    logger.warning(f"⚠️ Relação inválida ignorada: {rel_data} | Erro: {ve}")
                except Exception as e:
                    logger.warning(f"⚠️ Erro inesperado ao processar relação: {e}")

            if not valid_entities and not valid_relations:
                logger.warning(f"⚠️ EXTRAÇÃO ZERADA! Verifique o prompt ou a resposta do LLM.")
                logger.debug(f"Resposta Bruta da IA:\n{resposta_bruta}")

            logger.info(f"📊 Grafo Extraído: {len(valid_entities)} entidades, {len(valid_relations)} relações.")
            return KnowledgeGraphSchema(entities=valid_entities, relations=valid_relations)

        except Exception as e:
            logger.error(f"❌ Falha crítica na extração de grafo: {e}")
            raise

    def _build_fast_prompt(self, domain: str) -> str:
        return f"""Você é um Engenheiro de Grafos de Conhecimento de ELITE.
Sua missão é extrair conhecimento técnico de alta densidade e relevância de forma veloz e precisa.
O DOMÍNIO DESTE DOCUMENTO É: {domain}. Adapte o seu foco e as entidades extraídas para maximizar o valor neste domínio específico.

ONTOLOGIA DE REFERÊNCIA (Use estes ou sugira novos pertinentes ao domínio '{domain}'):
{", ".join(PREFERRED_TYPES)}

CRITÉRIOS DE EXTRAÇÃO (Qualidade sobre Quantidade):
1. Extraia APENAS conceitos centrais, sistemas, regras de negócio, tecnologias e variáveis.
2. Ignore jargões genéricos, exemplos secundários, conectivos ou termos que não agregam valor arquitetural.
3. Não force um número fixo de entidades; a densidade deve refletir a complexidade real do texto lido.
4. Conecte as entidades extraídas com relações precisas e verbos fortes (ex: 'define', 'implementa', 'calcula', 'depende_de').

REGRAS DE OURO:
- NOMES CURTOS: O 'name' deve ser o termo técnico exato (ex: "API REST" em vez de "A API REST do sistema").
- DESCRIÇÕES RICAS: A 'description' deve focar na função do conceito dentro do contexto lido.

FORMATO DE SAÍDA (Apenas JSON puro, sem marcações markdown):
{{
  "entities": [{{ "name": "...", "type": "...", "description": "..." }}],
  "relations": [{{ "subject": "...", "predicate": "...", "object": "..." }}]
}}
"""

    def _build_deep_prompt(self, domain: str) -> str:
        return f"""Você é um Pesquisador de Grafos de Conhecimento Forense e Especialista em Ontologias.
Sua missão é realizar uma EXTRAÇÃO GULOSA (GREEDY), EXAUSTIVA e ALTAMENTE INTERCONECTADA de todo e qualquer conhecimento.
ATENÇÃO: O DOMÍNIO DESTE DOCUMENTO É: {domain}. Você DEVE adaptar o seu foco, tipos de entidades e as relações extraídas para maximizar a utilidade de análise neste domínio específico.

ONTOLOGIA DE REFERÊNCIA (Use estes ou sugira novos pertinentes ao domínio '{domain}'):
{", ".join(PREFERRED_TYPES)}

INSTRUÇÕES DE PENSAMENTO (Chain-of-Thought):
1. Identifique TODOS os substantivos técnicos, ferramentas, frameworks, habilidades (soft e hard skills), experiências, pessoas, locais e conceitos sem exceção.
2. Não ignore nada por parecer 'detalhe'. Detalhes microscópicos são fundamentais na documentação (ex: bibliotecas usadas, metodologias, anos).
3. Se um termo técnico, habilidade ou experiência existe, ele DEVE virar uma entidade autônoma no JSON.
4. CONEXÃO MÁXIMA: É ESTRITAMENTE OBRIGATÓRIO que você gere dezenas de relações. Uma entidade solta não tem valor. Conecte ferramentas a projetos, pessoas a cargos, habilidades a experiências. Gere pelo menos 2 a 3 ligações para cada entidade extraída. Use predicados descritivos como 'domina', 'utilizou_em', 'trabalhou_como', 'graduou_se_em', 'requer', 'otimiza'.

REGRAS DE OURO:
- META DE DENSIDADE: Tente extrair entre 30 a 80 entidades por bloco de texto lido. Force o detalhamento extremo.
- META DE RELAÇÕES: Extraia entre 40 a 100 relações lógicas. O grafo DEVE ser denso e complexo.
- NOMES CURTOS: 'name' deve ser o termo exato, curto e capitalizado (ex: "Python", não "Linguagem Python").
- DESCRIÇÕES RICAS: Explique detalhadamente o contexto de como essa entidade apareceu no texto.

FORMATO DE SAÍDA (Apenas JSON puro):
{{
  "thought": "Breve cadeia de pensamento analisando como vou explodir esse texto em dezenas de conexões...",
  "entities": [{{ "name": "...", "type": "...", "description": "..." }}],
  "relations": [{{ "subject": "...", "predicate": "...", "object": "..." }}]
}}
"""

    def _clean_entity_name(self, name: str) -> str:
        """Limpa o nome de pontuações indesejadas no início e fim."""
        # Remove caracteres de lista ou pontuação solta (mas preserva parênteses se parecerem intencionais)
        name = name.strip().strip('.,;:-_*')
        
        # Se terminar com uma abreviação cortada como " (V", remove o fragmento
        name = re.sub(r'\s+\([a-z0-9]$', '', name, flags=re.IGNORECASE)
        
        # Se o nome começar com algo como "1.", "a)", remove
        name = re.sub(r'^(\d+\.|[a-z]\))\s*', '', name, flags=re.IGNORECASE)
        return name.strip()

    def _is_useful(self, ent: EntitySchema) -> bool:
        """Verifica se a entidade agregará valor ao conhecimento."""
        # Se a descrição for muito curta ou o nome for genérico demais, ignora
        if len(ent.name) < 2: return False
        if "O que é?" in ent.description or not ent.description.strip():
            return False
        return True

    def _is_trash(self, name: str) -> bool:
        """Filtro de hardware para remover ruído comum de PDFs."""
        name_upper = name.upper()
        blacklist = {
            "PAGINA", "PAGE", "CAPITULO", "CHAPTER", "COPYRIGHT", 
            "RESERVED", "ALL RIGHTS", "FIGURA", "FIGURE", "TABELA", "TABLE",
            "EXEMPLO", "EXAMPLE", "INTRODUCAO", "INTRODUCTION", "CONCLUSAO",
            "EXERCICIO", "EXERCISE", "ISBN", "ISSN", "EDITORA", "PUBLISHER",
            "NOTAS", "AULA", "UNIVERSIDADE", "PROFESSOR", "DEPARTAMENTO"
        }
        
        # 1. Verifica se o nome é EXATAMENTE uma palavra da lista negra
        if name_upper in blacklist: return True
        
        # 2. Ignora se for apenas "Figura X" ou "Tabela Y" (Regex mais específico)
        if re.match(r"^(FIGURA|TABELA|PAGE|PAGINA|EXEMPLO|CHAPTER|CAPITULO)\s+\d+", name_upper):
            return True
            
        # 3. Ignora lixo puramente simbólico ou apenas números soltos,
        # MAS permite padrões técnicos (ex: 802.11, 27001)
        if re.match(r"^[\W_]+$", name): return True
        if re.match(r"^\d+$", name): return True
        
        # 3. Ignora nomes excessivamente longos (provavelmente uma frase inteira errada)
        if len(name) > 100: return True
        
        return False

    def _safe_json_load(self, text: str) -> Dict[str, Any]:
        """Extrai e valida JSON da resposta da IA."""
        try:
            # Localiza o bloco JSON
            start = text.find('{')
            end = text.rfind('}') + 1
            if start == -1 or end == -1:
                return {}
                
            json_str = text[start:end]
            
            # Reparo básico: Remove vírgulas extras antes de fechamento de chaves/colchetes
            json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
            
            return json.loads(json_str)
        except Exception as e:
            logger.warning(f"⚠️ Falha ao decodificar JSON da IA: {e}")
            return {}
        return {}