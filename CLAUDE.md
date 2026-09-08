# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

Dashboard de gestão clínica para a ICDS (Instituto de Cooperação para o Desenvolvimento da Saúde), operando sobre o ERP **Smart Pixeon** (SQL Server, banco `SMART`, host `192.168.1.9`). O app não substitui o Pixeon — lê (e em alguns pontos escreve) direto nas mesmas tabelas do ERP, somando relatórios/indicadores e algumas funcionalidades que não existem nativamente nele (fluxo de caixa, lançamento de despesas, pontualidade, chat interno, bot de agenda via WhatsApp).

**Antes de mexer em qualquer módulo, leia a documentação técnica em `docs/`** — é gerada a partir do código-fonte e cobre em detalhe como cada cálculo é feito, quais tabelas/colunas são usadas e por quê (várias regras existem por causa de bugs reais já corrigidos). Comece por `docs/README.md`, que indexa os demais:
- `docs/01-visao-geral.md` — arquitetura, stack, convenções de código
- `docs/02-backend-financeiro-producao.md` — faturamento, fluxo de caixa, valor/hora, metas, projeção de produção mensal
- `docs/03-backend-clinica-recepcao.md` — Clínica (Assistencial/Ocupacional/Serviços), Agendamentos, Recepção
- `docs/04-backend-faturamento-estoque-whatsapp.md` — Guias pendentes, Estoque, Pacientes, WhatsApp, Painel de Senhas, Clinia
- `docs/05-frontend-arquitetura-modulos.md` — estrutura React, módulos e telas
- `docs/06-netmonitor.md` — plataforma irmã de monitoramento de infraestrutura (`C:\NetMonitor`, fora deste repo)

Os docs foram gerados em 24/07/2026 — módulos adicionados depois (chat interno, assistente de agenda via IA, portal público "Meus Resultados", consulta DB Diagnósticos, automação de e-mail — ver seção "Módulos recentes" abaixo) ainda não estão documentados lá; confira o código diretamente para esses.

## Comandos

### Backend (Python/FastAPI)
```powershell
cd backend
pip install -r requirements.txt
# dev (HTTP simples):
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# produção (HTTPS, como roda de fato — ver start_backend.ps1 na raiz):
powershell -File ..\start_backend.ps1
```
Não há venv de projeto — usa o Python global da máquina. Não há suíte de testes automatizados.

### Frontend (React/Vite)
```powershell
cd frontend
npm install
npm run dev      # dev server, porta 5177 (só para desenvolvimento local)
npm run build    # gera frontend/dist — OBRIGATÓRIO antes de considerar uma mudança de frontend "pronta"
npm run lint
```
**Não existe servidor Node/Vite em produção.** O backend FastAPI serve `frontend/dist` como arquivos estáticos na mesma porta (31000). Depois de qualquer alteração em `frontend/src`, rode `npm run build` — sem isso a mudança não aparece em produção. Reiniciar o backend não é necessário para mudanças só de frontend; é necessário para mudanças de backend (`main.py` e módulos importados por ele).

## Arquitetura

```
Navegador → HTTPS:31000 → FastAPI (backend/main.py, ~12 mil linhas, monolito único)
                              ├─ SQL Server SMART (Pixeon) — pyodbc, leitura + escrita pontual
                              ├─ SQLite locais (guias.db, chat_interno.db, agenda_bot.db, organograma.db)
                              ├─ WPPConnect (WhatsApp, localhost:21465) — via whatsapp_sender.py
                              └─ backend/scheduler.py — thread própria, envios diários agendados
```

- **Backend**: FastAPI + `pyodbc` (SQL Server) + `uvicorn` com SSL nativo (obrigatório — HTTP puro não responde). Acesso interno: `https://192.168.1.40:31000`. Acesso externo via Cloudflare Tunnel (`cloudflared`, URL efêmera).
- **Frontend**: SPA React + Vite, **sem client-side router** — navegação entre módulos troca um estado `activeModule` (`RENDER_MAP` em `App.jsx`), não a URL. Estilização quase toda via `style={{...}}` inline (Tailwind está instalado mas pouco usado no Dashboard principal). Gráficos: Recharts. Hook de dados: `useFetch(path, deps, intervalMs)` monta querystring a partir de `deps` e opcionalmente faz polling.
- **`get_conn()`/`query()`** em `main.py` é o helper central de leitura no SQL Server; `get_conn_hml()` conecta em homologação (`smart_hml`), usada para gravações clínicas ainda não validadas em produção.
- **`periodo_datas(periodo)`** converte strings de período (`"7d"`, `"30d"`, `"mes:YYYY-MM"`, `"custom:..."`, etc.) em intervalo de datas — reutilizado por quase todo endpoint financeiro/operacional.
- **Fórmula de valor líquido**, repetida em SQL em dezenas de queries (não extraída para função por estar embutida em cada query): `SMM_VLR - SMM_VLR_DESCONTO - SMM_VLR_COPARTIC + SMM_AJUSTE_VLR`.
- **Convenção de status de agenda (`agm_stat`)**: `A`=Aberto, `E`=Executado, `C`=Cancelado, `B`=Bloqueado. Bloqueio **nunca** é atendimento real — todo endpoint que soma/conta agendamento como produção deve excluir `B` (e normalmente `C`).
- **Configuração fora do banco Smart** (não pertence ao ERP): `metas_config.json`, `whatsapp_config.json` — persistidos como arquivos locais em `backend/`, não em tabela SQL.
- **Bancos SQLite locais por módulo**, independentes do SQL Server: `guias.db` (faturamento — guias pendentes), `chat_interno.db` (chat interno), `agenda_bot.db` (bot de disponibilidade de agenda), `organograma.db`.
- Comentários e nomes de variáveis majoritariamente em português.

### Regra de escrita em produção
Ao gravar diretamente nas tabelas do Smart (ex.: `POST /api/financeiro/despesas` em `CPG`/`IPG`), siga o padrão já usado no código: investigar o schema real antes de codar, testar com valor simbólico, confirmar visualmente, só então liberar de vez. Não usar `BEGIN TRANSACTION` explícito com pyodbc — o `autocommit=False` padrão já mantém transação implícita; um `BEGIN TRANSACTION` adicional aninha uma segunda transação que o `commit()` do pyodbc não fecha por completo (bug real já corrigido).

**DELETE/UPDATE manual (scripts de limpeza, debug, etc.) — nunca filtrar por uma coluna de negócio que pode se repetir** (ex.: `FLE_BIP`, número de senha — reinicia todo dia, então `WHERE FLE_BIP='OEP001'` casa com anos de histórico, não só o registro de hoje). Incidente real: uma limpeza de teste em `smart_hml` apagou 1.422 linhas históricas de `fle` por causa disso. Regra: 
1. Filtrar sempre pela chave primária real da tabela (ex.: `fle` = `FLE_DTHR_CHEGADA+FLE_PAC_REG+FLE_PSV_COD+FLE_STR_COD`) ou por um identificador único de verdade — nunca só por um código/valor de negócio.
2. Antes de qualquer `DELETE`/`UPDATE` manual, rodar o mesmo `WHERE` como `SELECT COUNT(*)` primeiro e conferir se o número bate com o esperado (1, 2, o que for) antes de decidir gravar.
3. Isso vale em qualquer ambiente (`smart_hml` incluído) — a diferença é só a gravidade do erro se acontecer.

## Módulos recentes (posteriores aos docs de 24/07/2026)

- **`backend/chat_interno.py`** + `frontend/src/Gestao.jsx` — chat interno (canais por setor + DM), SQLite local (`chat_interno.db`), frontend faz polling (sem WebSocket).
- **`backend/agenda_bot.py`** — bot de WhatsApp que responde disponibilidade de agenda por especialidade quando mencionado em um grupo; reaproveita a sessão WPPConnect e a `OPENAI_API_KEY` já usada no briefing por IA. Mesmo padrão mention-based + poll + dedup do bot de chamados do NetMonitor. Import de `main` sempre tardio dentro das funções (evita ciclo de import com `scheduler.py`).
- **`backend/db_diagnosticos_sender.py`** — consulta (nunca envia) status/laudo junto à DB Diagnósticos via SOAP (protocolo DBSync, `zeep`). O envio do pedido já é feito pelo Smart Pixeon direto.
- **`backend/email_sender.py`** — envio de e-mail via automação do Outlook Web com Playwright (não SMTP — SMTP AUTH está desabilitado no tenant M365 do ICDS e não há admin para habilitar). Sessão salva em `email_browser_profile/` (login manual único via `login_outlook_setup.py`). Erros são sempre capturados e devolvidos, nunca propagados (mesmo padrão de `whatsapp_sender.py`).
- **`frontend/src/MeusResultados.jsx`** — portal público "Meus Resultados" (busca de exames internos por CPF + data de nascimento, sem login).
- **`frontend/src/AssistenteAgenda.jsx`**, **`ResultadosFinanceiros.jsx`** — telas adicionais recentes, ainda não cobertas em `docs/05-frontend-arquitetura-modulos.md`.

## Aplicações relacionadas (fora deste repo/diretório)

- **NetMonitor** (`C:\NetMonitor`) — monitoramento de infraestrutura, reaproveita a sessão WhatsApp do Dashboard. Ver `docs/06-netmonitor.md`.
- **Painel de Senhas** (`C:\Users\administrator.CENSO\Desktop\painel_recepcao`) — build estático servido pelo Dashboard em `/painel-tv`.
- **`wppconnect-server/`** e **`evolution-api/`** neste repo são dependências vendorizadas de terceiros (ambas no `.gitignore`) — `wppconnect-server` mantém a sessão do WhatsApp Business em produção (porta 21465); `evolution-api` é um provedor alternativo mantido no código mas não confirmado como ativo em produção.
