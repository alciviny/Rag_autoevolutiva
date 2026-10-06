# Segurança e exposição

O backend continua sendo um aplicativo local, não um serviço SaaS pronto para internet.

- `python bridge.py` escuta em `127.0.0.1` por padrão; o Compose publica a porta somente em `127.0.0.1`. Alterar esse vínculo não adiciona autenticação.
- As rotas HTTP, WebSocket, namespaces e artefatos não têm identidade, autorização nem vínculo confiável entre usuário e tenant. Não exponha a API a clientes não confiáveis.
- Python, Node, C++ e Rust ficam desativados por padrão. `ALANA_ENABLE_UNSANDBOXED_CODE_EXECUTION=true` os libera no host da API e não é seguro para uso multiusuário. A análise AST de ferramentas dinâmicas também não substitui sandbox do sistema operacional.
- O crawler bloqueia endereços privados, redirects para outros hosts, portas não padrão, páginas grandes e páginas proibidas por robots.txt. A resolução DNS e a conexão HTTP ainda ocorrem em chamadas separadas; DNS rebinding exige uma camada de transporte que fixe o IP validado.
- IDs vetoriais agora incluem namespace e tipo. Reindexe dados antigos em janela controlada; o algoritmo novo não recupera pontos que tenham sido sobrescritos antes desta mudança.
