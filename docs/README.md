# Documentação da Plataforma Dashboard (ICDS)

Documentação técnica completa da plataforma de gestão clínica — como os cálculos são feitos, tecnologias utilizadas e funções organizadas por módulo. Gerada em 24/07/2026 a partir da leitura direta do código-fonte (não é um documento estático — se o código mudar, esta documentação pode ficar desatualizada e deve ser revisada).

## Como navegar

| Arquivo | Conteúdo |
|---|---|
| **[01-visao-geral.md](01-visao-geral.md)** | O que é a plataforma, arquitetura geral, stack de tecnologias (backend, frontend, infraestrutura), bancos de dados, aplicações irmãs (NetMonitor, Painel de Senhas), convenções de código |
| **[02-backend-financeiro-producao.md](02-backend-financeiro-producao.md)** | Helpers compartilhados (`periodo_datas`, fórmula de valor líquido), faturamento/recebimentos, Fluxo de Caixa completo (incl. lançamento de despesas), Valor por Hora (médico/consultório), Metas, motor de projeção da Produção Mensal (feriados, peso de sábado, recordes) |
| **[03-backend-clinica-recepcao.md](03-backend-clinica-recepcao.md)** | Convenção de status de agendamento, módulo Clínica (Assistencial/Ocupacional/Serviços Especializados), Agendamentos, Recepção (ranking, evolução, pontualidade) |
| **[04-backend-faturamento-estoque-whatsapp.md](04-backend-faturamento-estoque-whatsapp.md)** | Guias pendentes (banco SQLite próprio), Estoque, Pacientes, integração WhatsApp (WPPConnect + agendamento de mensagens), Painel de Senhas, integração Clinia |
| **[05-frontend-arquitetura-modulos.md](05-frontend-arquitetura-modulos.md)** | Stack React/Vite, autenticação, navegação, componentes reutilizáveis, detalhamento de cada módulo do frontend |
| **[06-netmonitor.md](06-netmonitor.md)** | Plataforma irmã de monitoramento de infraestrutura — arquitetura, tipos de monitor, alertas WhatsApp, baseline de latência, feature de Incidentes |

## Resumo rápido — o que é cada módulo do menu principal

| Módulo | Uma linha |
|---|---|
| Home | Resumo geral + briefing executivo gerado por IA |
| Contratos | Link para app externo (Netlify) de gestão de contratos |
| Faturamento | Controle de guias pendentes (banco próprio, SQLite) |
| Clínica | Assistencial, Ocupacional, Serviços, Agendamentos, Agenda do Médico, Valor/Hora |
| Atendimento | Fila do médico / prontuário (grava em homologação, não produção) |
| Laboratório | Exames, bancadas, recoleta, produção por profissional |
| Recepção | Ranking de recepcionistas + relatório de Pontualidade (login x 1ª OS) |
| Produção Mensal | Meta/projeção do mês + Fluxo de Caixa + lançamento de despesas |
| Pacientes | Base de pacientes, bairros, faixa etária, aniversariantes |
| Estoque | Posição, giro, curva ABC, lotes a vencer |
| Painel TV | Modo telão em tempo real, com som progressivo por marco de meta |
| Permissões | Gestão de acesso por usuário/módulo |

## Metodologias de cálculo mais importantes (referência rápida)

- **Valor líquido de um serviço**: `SMM_VLR - SMM_VLR_DESCONTO - SMM_VLR_COPARTIC + SMM_AJUSTE_VLR` — usado em quase todo endpoint financeiro.
- **Saldo de caixa**: `entradas (mte) - saídas (IPG pago)`; saldo projetado soma a receber em 30d e subtrai a pagar em 30d.
- **Valor por hora (médico)**: atribuído ao executor real (`SMM_MED`), não a quem só estava na agenda — corrige ~3% dos casos onde outro profissional executou o procedimento.
- **Pontualidade**: compara horário de login (`GR_SES`) com a criação da primeira OS do dia (`OSM_DTHR`) — não a chamada de fila (FLE), que mostrou ser lançada fora de ordem em alguns dias.
- **Projeção de produção mensal**: projeção linear (`total_até_agora + média_diária × dias_restantes`), ponderando sábado como dia parcial e excluindo domingos/feriados de Parauapebas/PA.
- **Bloqueios de agenda (`agm_stat='B'`) nunca contam como atendimento real** — regra corrigida em vários pontos do código após bug identificado.

## Limitações conhecidas / dívidas técnicas registradas no código

- O Fluxo de Caixa via `CPG`/`IPG` tem uso histórico concentrado em 2018-2020 — a clínica controla despesa majoritariamente fora do sistema hoje; dados recentes só existem a partir do lançamento manual pelo próprio Dashboard.
- Valor por Hora por **consultório** hoje mostra praticamente uma linha só — a agenda usa um registro de sala genérico único na prática, não reflete salas físicas distintas.
- `/api/financeiro/recordes` usa cache de 1h em memória (não persistente — reinício do backend limpa o cache).
- O frontend não tem testes automatizados nem TypeScript — build via `npm run build` deve ser refeito manualmente a cada alteração e reiniciado o backend não é necessário para mudanças só de frontend (servido como arquivo estático), mas é necessário para mudanças de backend.
