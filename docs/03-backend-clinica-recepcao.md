# Backend — Clínica, Agendamentos e Recepção

Este documento cobre os endpoints de `backend/main.py` relacionados aos módulos **Clínica** (Assistencial, Ocupacional, Serviços Especializados), **Agendamentos** e **Recepção**.

Tabelas centrais: `agm` (agendamentos), `osm` (ordens de serviço), `smm` (itens/produção de cada OS), `fle` (fila de espera/recepção), `cnv` (convênios), `esp` (especialidades), `psv` (pessoas: médicos/profissionais), `usr` (usuários do sistema), `GR_SES` (sessões de login), `smk`/`ctf` (catálogo de serviços e classificação).

## Convenção de status do agendamento (`agm_stat`)

- `A` = Aberto (agendado, ainda não ocorreu)
- `E` = Executado (paciente foi atendido)
- `C` = Cancelado
- `B` = Bloqueado (bloqueio de agenda do médico — **não é um agendamento real**)

**Regra consolidada:** todo endpoint que soma/conta agendamentos como produção ou volume real deve excluir `B` (bloqueio) e normalmente também `C` (cancelado), usando `agm.agm_stat NOT IN ('C','B')`. Essa exclusão está presente em `/api/modulo/agendamentos/resumo-hoje`, `/api/modulo/agendamentos/producao-hoje-convenio`, `/api/agenda/dia` (`agm_stat <> 'B'`) e outros pontos do arquivo — foi corrigida propositalmente em pontos que antes contavam bloqueios como agendamento real.

---

## Módulo Clínica

### `GET /api/modulo/assistencial/resumo`
Parâmetro: `periodo`.
Financeiro e operacional do setor Assistencial (`osm_atend IN ('ASS','EME','CRG','TAM')`, `smm.SMM_SFAT IN ('A','F','P')` — só itens Aberto/Faturado/Pago, nunca cancelado).

- **Valor líquido de cada item** (fórmula reaproveitada em quase todo o arquivo):
  `SMM_VLR - SMM_VLR_DESCONTO - SMM_VLR_COPARTIC + SMM_AJUSTE_VLR`
- Separa produção em 3 grandes grupos via `SMM_ESP`:
  - **Consultas médicas**: CLI, PED, ORT, CAR, DER, GIN, RUM, GAS, URO, PNE, END, OFT, CIR, VAR, PRO, ANE, HAM, INF, MAM, MAS
  - **Equipe multidisciplinar**: PSC, NUT, ENF, FIS, TER, FAR, ASS, SOC
  - **Exames e diagnóstico**: LAB, RAD, USG, ANC, CAR, ECG, EEG, EMG, EXO
- **Particular** = convênio de código `'PAR'` (paciente paga direto na recepção, sem convênio).
- Consultas médicas por especialidade são filtradas adicionalmente por `ctf.CTF_CATEG = 'C'` (join com `smk`/`ctf`), ou seja, só itens cuja classe de catálogo é realmente "Consulta".
- Também calcula variação percentual (`var_pct`) contra o período anterior equivalente (`periodo_anterior`).

### `GET /api/modulo/assistencial/medicos-por-especialidade`
Parâmetros: `periodo`, `especialidade` (código `SMM_ESP`), `atend` (default `"ASS"`, aceita lista separada por vírgula).
Ranking de médicos (via `osm.osm_mreq` → `psv.psv_cod`) por valor faturado numa especialidade específica, ordenado por valor desc, top 20.

### `GET /api/modulo/ocupacional/resumo`
Parâmetro: `periodo`.
Mesmo padrão financeiro do Assistencial, mas filtrando `osm_atend IN ('ADM','PER','DEM','RTB','MDF','MOC')` — os 6 tipos de exame ocupacional:
- `ADM` = Admissional, `PER` = Periódico, `DEM` = Demissional, `RTB` = Retorno ao Trabalho, `MDF` = Mudança de Função, `MOC` = Medicina Ocupacional (genérico)

Retorna: financeiro, variações, operacional (contagem por tipo), lista de empresas (via `cnv`, já que cada empresa contratante é cadastrada como um "convênio"), especialidades, por-convênio e por-dia (funções auxiliares compartilhadas `modulo_especialidades_smm`, `modulo_por_convenio`, `modulo_por_dia`).

### `GET /api/modulo/ocupacional/empresas`
Parâmetros: `modo` (`"mes"` ou `"todo"`), `ano`, `mes`.
Ranking de empresas (por `cnv_nome`) com contagem de ADM/PER/DEM e faturamento total.
- `modo="todo"` varre desde `2000-01-01` (todo o histórico) e usa um **cache em memória de processo** (`_CACHE_EMPRESAS_TODO`, TTL configurável em minutos) porque essa consulta sobre todo o histórico é pesada e o resultado não muda a cada request.
- `modo="mes"` aceita navegação por mês/ano específico.

### `GET /api/modulo/servicos/resumo`
Parâmetro: `periodo`.
"Serviços Especializados" = itens cujo `SMM_ESP` está em `SERVICOS_ESP_CODES` (PSC, NUT, FON, NEU, PED, GIN, ORT, DER, PSQ, ENF, ANC, RAD, USG, CAR). Retorna financeiro total, breakdown por tipo de especialidade e série diária. Mesmo cálculo de valor líquido e mesmo filtro `SMM_SFAT IN ('A','F','P')` do restante do sistema.

---

## Agendamentos

### `GET /api/agendamentos/resumo`
Parâmetro: `periodo`. Filtra por `agm_hini` no período.
- `taxa_comparecimento` = Executados / (Total − Bloqueados) × 100, ou seja, a taxa é calculada sobre agendamentos reais (exclui bloqueio do denominador, mas cancelamento continua contando como "não compareceu").
- `valor_total_agendado` = soma de `agm_valor` no período (valor da agenda, não necessariamente o valor faturado real).

### `GET /api/agendamentos/proximos`
Parâmetro: `limite` (default 20). Lista os próximos agendamentos (`agm_hini >= GETDATE()`, status `A` ou `E`), com nome do paciente, especialidade, médico, apelido, horário, status e local (`loc`).

### `GET /api/agendamentos/por-semana`
Parâmetro: `periodo`. Agrupa por `DATEPART(week, agm_hini)`: executados, abertos, cancelados, bloqueados e valor da semana.

### `GET /api/agendamentos/cancelamentos`
Parâmetro: `periodo`. Filtra `agm_stat = 'C'`, agrupado por `agm_canc_dthr` (data do cancelamento, não da consulta) — quantidade e valor perdido por dia.

### `GET /api/agenda/medicos`
Lista médicos com agendamento futuro (`agm_hini >= hoje`, status A/E), distintos, com especialidade (`psv.psv_esp_cod` → `esp`).

### `GET /api/agenda/dia`
Parâmetros: `cod_medico`, `data` (default hoje). Agenda completa do dia de um médico: horário início/fim, paciente, status, confirmação, especialidade, valor, local, convênio. Filtro `agm_stat <> 'B'` (bloqueio nunca aparece na agenda visível do médico).

### `GET /api/agenda/mensal`
Parâmetros: `cod_medico`, `ano`, `mes`. Agrupado por dia: total, executados, abertos, cancelados, valor total. Também filtra `agm_stat <> 'B'`.

### `GET /api/agenda/consultorios/valor-hora` e `GET /api/agenda/medicos/valor-hora`
Documentados em detalhe no arquivo de Financeiro/Produção (`02-backend-financeiro-producao.md`) — calculam quanto cada consultório/médico rende por hora ocupada, usando `agm_hini`/`agm_hfim`/`agm_valor` de agendamentos com status `E`, com atribuição por médico executor real via `smm.SMM_MED`.

### `GET /api/modulo/agendamentos/resumo-hoje`
Sem parâmetros (sempre "hoje"). O endpoint mais elaborado do grupo:
- `marcacoes` = agendamentos do dia com paciente vinculado, excluindo cancelado/bloqueado.
- `atendidos` = dentre as marcações, quantos têm `agm_stat='E'` OU têm uma OS vinculada (via `AGM_OSM_SERIE` ou correlação por paciente+data com tolerância de horário de −30 a +180 minutos).
- `faltantes` = marcados, não cancelados/bloqueados/executados e sem nenhuma OS correlacionada.
- `total_horarios` = vagas disponíveis (tabela `EX_HORARIOS` do dia) + marcações reais.
- `ticket_medio_30d` = ticket médio dos últimos 30 dias (usado para projetar quanto os pacientes que ainda não vieram devem gerar).
- `producao_hoje` = soma do valor líquido das OS de hoje, mas **somente de pacientes que tinham agendamento hoje** (correlação por paciente + tolerância de horário) — não é toda a produção do dia, é a fatia atribuível à agenda.
- Também retorna distribuição por hora (`por_hora`) e lista de médicos por turno (manhã/tarde, com corte de hora configurável na função interna `busca_medicos_turno`).

### `GET /api/modulo/agendamentos/resumo`
Parâmetro: `periodo`. Visão consolidada equivalente ao "resumo-hoje", mas para um período arbitrário.

### `GET /api/modulo/agendamentos/medico-detalhe`
Parâmetros: `psv_cod`, `periodo`. Produção por convênio dos pacientes que tinham agendamento com aquele médico no período — correlaciona `agm.agm_pac` (pacientes agendados com o médico) com as OS deles no mesmo dia do agendamento.

### `GET /api/modulo/agendamentos/producao-hoje-convenio`
Sem parâmetros. Produção de hoje agrupada por convênio, restrita a pacientes que tinham agendamento hoje (mesmo filtro `agm_stat NOT IN ('C','B')`).

---

## Recepção

Conceito central: **"atendimento" na recepção = `FLE_DTHR_CHEGADA`** (chegada/retirada de senha) e **"chamada"/atendimento real = `FLE_DTHR_ATENDIMENTO`**. Quase todo endpoint de recepção exclui:
- `FLE_PAC_REG <= 0` (linha sem paciente vinculado)
- login de usuário `LIKE 'TOTEM%'` (totem de autoatendimento não conta como recepcionista)
- login contendo `'ESTAGIARIO'`

### `GET /api/recepcao/media-por-horario`
Parâmetros: `periodo`, `setor` (ignorado de propósito — sempre mostra as 4 recepções lado a lado: RDI=Diagnóstico, ROC=Ocupacional, RCN=Consultórios, RCI=Censo Imagem). Volume de chegadas por hora do dia (janela fixa 06h–20h), incluindo totem (é volume real de pacientes, diferente da atribuição por recepcionista usada no ranking).

### `GET /api/recepcao/metas`
Parâmetros: `periodo`, `setor`. Metas calculadas automaticamente pela **média histórica dos 3 meses completos anteriores ao mês atual** (não é meta configurada manualmente):
- `producao_por_recepcao`: meta mensal de produção por recepção, comparada ao período atual selecionado.
- `meta_tempo_atendimento_min`: meta única de tempo médio de atendimento (chegada até chamada real, ou até abertura da 1ª OS quando não há chamada registrada), calculada como média histórica geral.
- Usa a mesma regra de "atribuição por primeiro contato" do ranking (ver abaixo) para não contar produção duplicada quando o mesmo paciente passa por 2+ recepções no mesmo dia.

### `GET /api/recepcao/ranking`
Parâmetros: `periodo`, `setor`. Ranking de recepcionistas — pacientes atendidos, tempo médio de espera, produção financeira. Pontos importantes:
- **Atribuição de produção por "primeiro contato"**: quando um paciente passa por mais de uma recepção no mesmo dia, a produção financeira é creditada só à recepção que o atendeu primeiro (`ROW_NUMBER() ... ORDER BY FLE_DTHR_CHEGADA ASC`), evitando contar a mesma produção duas vezes.
- **Tempo de espera** = da chegada (`FLE_DTHR_CHEGADA`) até a chamada real (`FLE_DTHR_ATENDIMENTO`), ou, se não há chamada registrada, até a abertura da primeira OS do paciente naquele dia (`osm_dthr`). Só entra na média se o tempo calculado ficar entre 0 e 120 minutos (fora disso é tratado como outlier/dado inconsistente e descartado da média).
- Nome do recepcionista vem de `usr.USR_NOME` (fallback pro próprio login se não achar).

### `GET /api/recepcao/evolucao`
Parâmetros: `periodo`, `setor`, `recepcionista` (opcional). Série diária de pacientes atendidos, separada por turno (Manhã = chegada antes das 13h, Tarde = 13h em diante).

### `GET /api/recepcao/por-convenio`
Parâmetros: `periodo`, `setor`. Mesma lógica de tempo de espera do ranking, mas agregada por convênio (não por recepcionista) — quantidade de pacientes e tempo médio de espera por convênio.

### `GET /api/recepcao/convenios`
Parâmetros: `periodo`, `setor`, `recepcionista`. Breakdown de convênios (quantidade de OS abertas) para um recepcionista específico — usado ao expandir uma linha no ranking.

### `GET /api/recepcao/usuarios`
Sem período — sempre olha os últimos 180 dias fixos. Lista (login, nome) de recepcionistas com atendimento recente, usada para popular o seletor da tela de Pontualidade.

### `GET /api/recepcao/pontualidade` e `GET /api/recepcao/pontualidade/pdf`
Parâmetros: `login`, `inicio`, `fim` (datas `YYYY-MM-DD`).

Relatório de pontualidade dia a dia, comparando:
- **Login** = horário mais cedo de abertura de sessão no sistema naquele dia, da tabela `GR_SES` (`GR_SES_DTHR_INI`, filtrado por `GR_USR_LOGIN`).
- **Início de atendimento** = horário da **primeira OS criada pelo usuário naquele dia** (`OSM_DTHR`, filtrado por `OSM_USR_LOGIN_CAD`, campo que registra quem cadastrou a OS).

Esse segundo ponto foi escolhido deliberadamente em vez de `FLE_DTHR_ATENDIMENTO` (chamada na fila): testes comparando os dois mostraram que a chamada na fila pode ser lançada fora de ordem/atrasada em relação ao trabalho real (foi observado um caso de "atraso" de 112 minutos pela fila que na verdade era de ~1 minuto quando medido pela criação da OS) — `OSM_DTHR` é um timestamp de transação de sistema, mais confiável que o registro manual de chamada de senha.

O "gap" (intervalo) é a diferença em minutos entre login e a primeira OS. `/pdf` gera o mesmo relatório como arquivo PDF (via `subprocess` chamando o Chrome headless com `--print-to-pdf`, template HTML embutido com a logo da clínica em base64), retornado como download (`FileResponse` com `BackgroundTasks` para apagar o arquivo temporário depois de enviado).

---

## Observação sobre `fat_sld` / faturas em aberto

Não coberto neste documento (ver `02-backend-financeiro-producao.md`), mas relevante para quem cruza dados de Agendamentos/Clínica com o financeiro: `fat_sld` acumula saldo em aberto desde 2017 e não deve ser somado sem filtro de data — já causou um bug de "a receber" de R$75 milhões antes de ser corrigido.
