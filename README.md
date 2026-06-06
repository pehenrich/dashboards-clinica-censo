# Dashboard Clínica — Smart Pixeon

Stack: **Python (FastAPI)** + **React (Vite + Recharts)** + **SQL Server**

## Estrutura
```
dashboard_clinica/
├── backend/
│   ├── main.py          ← API FastAPI com todas as queries
│   ├── requirements.txt
│   └── .env.example     ← copie para .env e preencha
└── frontend/
    └── src/
        └── App.jsx      ← Dashboard React completo
```

## 1. Backend (Python)

### Pré-requisitos
- Python 3.10+
- ODBC Driver 17 for SQL Server instalado na máquina
  → https://learn.microsoft.com/pt-br/sql/connect/odbc/download-odbc-driver-for-sql-server

### Configurar e subir
```bash
cd backend
cp .env.example .env
# edite o .env com suas credenciais do SQL Server

pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

API disponível em: http://localhost:8000
Docs automáticas:  http://localhost:8000/docs

### Endpoints disponíveis
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | /api/financeiro/resumo | KPIs financeiros |
| GET | /api/financeiro/receita-mensal | Receita por mês |
| GET | /api/financeiro/por-convenio | Receita por convênio |
| GET | /api/atendimentos/resumo | KPIs de atendimento |
| GET | /api/atendimentos/por-especialidade | Por especialidade |
| GET | /api/atendimentos/por-dia | Volume diário |
| GET | /api/agendamentos/resumo | KPIs de agenda |
| GET | /api/agendamentos/proximos | Próximos agendamentos |
| GET | /api/agendamentos/por-semana | Status por semana |
| GET | /api/pacientes/resumo | KPIs de pacientes |
| GET | /api/pacientes/novos-por-semana | Novos cadastros |
| GET | /api/pacientes/faixa-etaria | Distribuição etária |
| GET | /api/health | Diagnóstico da conexão |

Todos aceitam `?periodo=7d | 30d | 90d`

## 2. Frontend (React)

### Pré-requisitos
- Node.js 18+

### Configurar e subir
```bash
cd frontend
npm create vite@latest . -- --template react
npm install recharts

# crie o arquivo .env.local:
echo "VITE_API_URL=http://localhost:8000" > .env.local

# copie o App.jsx para src/App.jsx (substitui o gerado pelo Vite)
npm run dev
```

Dashboard disponível em: http://localhost:5173

## 3. Mapeamento de tabelas (Smart Pixeon)

| Indicador | Tabelas principais |
|-----------|-------------------|
| Faturamento | `osm`, `smm`, `mns` |
| Contas a receber / inadimplência | `crp` |
| Atendimentos | `osm` (tip_atendimento) |
| Internações | `hsp` |
| Especialidades | `esp`, `psv` |
| Agendamentos | `agm` |
| Convênios | `cnv`, `pln` |
| Pacientes | `pac`, `cls_pac` |

## 4. Usuário readonly recomendado (SQL Server)
```sql
-- Execute no SQL Server como sysadmin
CREATE LOGIN dashboard_ro WITH PASSWORD = 'SenhaForte123!';
USE SMART;
CREATE USER dashboard_ro FOR LOGIN dashboard_ro;
EXEC sp_addrolemember 'db_datareader', 'dashboard_ro';
```

## 5. Notas importantes
- Os nomes de colunas (`dta_fechamento`, `vlr_total`, `cod_os`, etc.)
  seguem o padrão documentado do Smart Pixeon — valide na sua instância
  consultando o dicionário de dados ou fazendo `sp_columns 'osm'`
- Campos de status da agenda (`sit_agendamento`): R=Realizado, A=Agendado,
  C=Cancelado, F=Faltou — confirme os valores no seu ambiente
- Para produção, configure HTTPS e restrinja o CORS no `main.py`
