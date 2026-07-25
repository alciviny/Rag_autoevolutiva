# -*- coding: utf-8 -*-
"""
Script de Validacao de Provedores LLM.
Testa cada modelo configurado individualmente com uma chamada real e reporta o resultado.
"""
import os
import sys
import asyncio
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# Carrega variáveis de ambiente do .env
from dotenv import load_dotenv
load_dotenv()

import litellm
litellm.suppress_debug_info = True

PROMPT = [{"role": "user", "content": "Responda APENAS com: OK"}]

# --- Configuração dos provedores a testar ---
def build_candidates():
    candidates = []

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        candidates += [
            ("gemini/gemini-2.0-flash",  {"api_key": gemini_key}),
            ("gemini/gemini-1.5-flash",  {"api_key": gemini_key}),
        ]

    github_key = os.getenv("GITHUB_API_KEY")
    if github_key:
        candidates += [
            ("github/gpt-4o",                   {"api_key": github_key}),
            ("github/Llama-3.3-70B-Instruct",   {"api_key": github_key}),
            ("github/Phi-4",                    {"api_key": github_key}),
        ]

    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_key:
        candidates += [
            ("deepseek/deepseek-chat", {"api_key": deepseek_key}),
        ]

    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        candidates += [
            ("groq/llama-3.3-70b-versatile", {"api_key": groq_key}),
            ("groq/llama-3.1-8b-instant",    {"api_key": groq_key}),
        ]

    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        candidates += [
            ("openrouter/meta-llama/llama-3.3-70b-instruct:free", {"api_key": openrouter_key}),
            ("openrouter/google/gemma-4-31b-it:free",              {"api_key": openrouter_key}),
            ("openrouter/google/gemma-4-26b-a4b-it:free",          {"api_key": openrouter_key}),
        ]

    return candidates


async def test_model(model: str, extra_params: dict) -> tuple[str, bool, str]:
    start = time.perf_counter()
    try:
        response = await litellm.acompletion(
            model=model,
            messages=PROMPT,
            max_tokens=10,
            timeout=20,
            **extra_params
        )
        answer = response.choices[0].message.content.strip()
        duration = time.perf_counter() - start
        return model, True, f"{answer!r}  ({duration:.2f}s)"
    except Exception as e:
        duration = time.perf_counter() - start
        short = str(e)[:120].replace("\n", " ")
        return model, False, f"FALHOU ({duration:.2f}s): {short}"


async def main():
    candidates = build_candidates()
    if not candidates:
        print("Nenhuma chave de API encontrada nas variáveis de ambiente (.env).")
        return

    print(f"\n{'='*65}")
    print(f"  Validação de Provedores LLM — {len(candidates)} modelos")
    print(f"{'='*65}\n")

    tasks = [test_model(m, p) for m, p in candidates]
    results = await asyncio.gather(*tasks)

    ok_count = 0
    for model, success, detail in results:
        icon = "[OK]    " if success else "[FALHOU]"
        if success:
            ok_count += 1
        print(f"  {icon} {model}")
        print(f"     > {detail}\n")

    print("=" * 65)
    print(f"  Resultado: {ok_count}/{len(candidates)} provedores funcionando\n")


if __name__ == "__main__":
    asyncio.run(main())
