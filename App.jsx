import { useState, useEffect } from "react";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from "recharts";

// ─── Configuração ──────────────────────────────────────────────────────────
const API = import.meta.env.VITE_API_URL || "http://localhost:8000";

const STATUS_MAP = {
  R: { label: "Realizado",  cor: "#1D9E75" },
  A: { label: "Agendado",   cor: "#185FA5" },
  C: { label: "Cancelado",  cor: "#E24B4A" },
  F: { label: "Faltou",     cor: "#EF9F27" },
};

const CORES_ESP = ["#185FA5","#1D9E75","#EF9F27","#D85A30","#534AB7","#888780"];

// ─── Utilitários ────────────────────────────────────────────────────────────
const brl = (v) =>
  v != null
    ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v)
    : "—";

const num = (v) => (v != null ? Number(v).toLocaleString("pt-BR") : "—");
const pct = (v) => (v != null ? `${Number(v).toFixed(1)}%` : "—");

function useFetch(path, periodo) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetch(`${API}${path}?periodo=${periodo}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }, [path, periodo]);

  return { data, loading, error };
}

// ─── Componentes base ────────────────────────────────────────────────────────
function Card({ children, className = "" }) {
  return (
    <div className={`bg-white rounded-xl border border-gray-100 p-5 shadow-sm ${className}`}>
      {children}
    </div>
  );
}

function KPI({ label, value, delta, deltaUp, loading }) {
  return (
    <div className="bg-gray-50 rounded-lg p-4">
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      {loading ? (
        <div className="h-7 w-24 bg-gray-200 animate-pulse rounded" />
      ) : (
        <p className="text-2xl font-medium text-gray-900">{value}</p>
      )}
      {delta && (
        <p className={`text-xs mt-1 ${deltaUp ? "text-emerald-600" : "text-red-500"}`}>
          {delta}
        </p>
      )}
    </div>
  );
}

function SectionTitle({ children }) {
  return (
    <p className="text-[11px] font-medium text-gray-400 uppercase tracking-widest mt-6 mb-3">
      {children}
    </p>
  );
}

function ErrorMsg({ msg }) {
  return (
    <div className="text-red-500 text-sm p-3 bg-red-50 rounded-lg">
      Erro ao carregar: {msg}
    </div>
  );
}

// ─── Seção Financeiro ────────────────────────────────────────────────────────
function SecaoFinanceiro({ periodo }) {
  const { data: resumo, loading: lR, error: eR } = useFetch("/api/financeiro/resumo", periodo);
  const { data: mensal, loading: lM }             = useFetch("/api/financeiro/receita-mensal", periodo);
  const { data: conv,   loading: lC }             = useFetch("/api/financeiro/por-convenio", periodo);

  const inadimp = resumo?.faturamento
    ? ((resumo.inadimplencia / resumo.faturamento) * 100).toFixed(1)
    : null;

  return (
    <>
      {eR && <ErrorMsg msg={eR.message} />}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI label="Faturamento"    value={brl(resumo?.faturamento)}  loading={lR} />
        <KPI label="Ticket médio"   value={brl(resumo?.ticket_medio)} loading={lR} />
        <KPI label="Total de OSs"   value={num(resumo?.total_os)}     loading={lR} />
        <KPI
          label="Inadimplência"
          value={pct(inadimp)}
          loading={lR}
          deltaUp={false}
          delta={inadimp > 5 ? "↑ Atenção" : "✓ Controlada"}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <Card>
          <p className="text-sm font-medium mb-1">Receita mensal</p>
          <p className="text-xs text-gray-400 mb-3">Últimos 6 meses · R$</p>
          {lM ? (
            <div className="h-48 bg-gray-100 animate-pulse rounded" />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={mensal || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="mes" tick={{ fontSize: 11 }} />
                <YAxis tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v) => brl(v)} />
                <Bar dataKey="receita" fill="#185FA5" radius={[3, 3, 0, 0]} name="Receita" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card>
          <p className="text-sm font-medium mb-1">Por convênio</p>
          <p className="text-xs text-gray-400 mb-3">Top convênios no período</p>
          {lC ? (
            <div className="h-48 bg-gray-100 animate-pulse rounded" />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={(conv || []).slice(0, 6)} layout="vertical">
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis type="number" tickFormatter={(v) => `R$${(v / 1000).toFixed(0)}k`} tick={{ fontSize: 10 }} />
                <YAxis dataKey="nom_convenio" type="category" width={90} tick={{ fontSize: 10 }} />
                <Tooltip formatter={(v) => brl(v)} />
                <Bar dataKey="receita" fill="#1D9E75" radius={[0, 3, 3, 0]} name="Receita" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>
    </>
  );
}

// ─── Seção Atendimentos ──────────────────────────────────────────────────────
function SecaoAtendimentos({ periodo }) {
  const { data: resumo, loading: lR, error: eR } = useFetch("/api/atendimentos/resumo", periodo);
  const { data: esp,    loading: lE }             = useFetch("/api/atendimentos/por-especialidade", periodo);
  const { data: dias,   loading: lD }             = useFetch("/api/atendimentos/por-dia", periodo);

  return (
    <>
      {eR && <ErrorMsg msg={eR.message} />}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI label="Total"        value={num(resumo?.total_atendimentos)} loading={lR} />
        <KPI label="Ambulatorial" value={num(resumo?.ambulatorial)}       loading={lR} />
        <KPI label="Internações"  value={num(resumo?.internacao)}         loading={lR} />
        <KPI label="Urgência"     value={num(resumo?.urgencia)}           loading={lR} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <Card>
          <p className="text-sm font-medium mb-1">Por especialidade</p>
          <p className="text-xs text-gray-400 mb-3">Distribuição no período</p>
          {lE ? (
            <div className="h-52 bg-gray-100 animate-pulse rounded" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={esp || []}
                  dataKey="qtd"
                  nameKey="especialidade"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  innerRadius={45}
                  label={({ especialidade, percent }) =>
                    `${especialidade.split(" ")[0]} ${(percent * 100).toFixed(0)}%`
                  }
                  labelLine={false}
                >
                  {(esp || []).map((_, i) => (
                    <Cell key={i} fill={CORES_ESP[i % CORES_ESP.length]} />
                  ))}
                </Pie>
                <Tooltip formatter={(v) => num(v)} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card>
          <p className="text-sm font-medium mb-1">Atendimentos por dia</p>
          <p className="text-xs text-gray-400 mb-3">Volume diário</p>
          {lD ? (
            <div className="h-52 bg-gray-100 animate-pulse rounded" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={dias || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="data" tick={{ fontSize: 10 }}
                  tickFormatter={(v) => v?.slice(5)} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="qtd" stroke="#534AB7"
                  strokeWidth={2} dot={false} name="Atendimentos" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>
    </>
  );
}

// ─── Seção Agendamentos ──────────────────────────────────────────────────────
function SecaoAgendamentos({ periodo }) {
  const { data: resumo, loading: lR, error: eR } = useFetch("/api/agendamentos/resumo", periodo);
  const { data: semana, loading: lS }             = useFetch("/api/agendamentos/por-semana", periodo);
  const [proximos, setProximos]                   = useState(null);
  const [loadingP, setLoadingP]                   = useState(true);

  useEffect(() => {
    fetch(`${API}/api/agendamentos/proximos?limite=8`)
      .then((r) => r.json())
      .then(setProximos)
      .finally(() => setLoadingP(false));
  }, []);

  return (
    <>
      {eR && <ErrorMsg msg={eR.message} />}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI label="Total"              value={num(resumo?.total)}                loading={lR} />
        <KPI label="Realizados"         value={num(resumo?.realizados)}           loading={lR} deltaUp={true} />
        <KPI label="Cancelados"         value={num(resumo?.cancelados)}           loading={lR} deltaUp={false} />
        <KPI
          label="Taxa comparecimento"
          value={pct(resumo?.taxa_comparecimento)}
          loading={lR}
          deltaUp={resumo?.taxa_comparecimento >= 85}
          delta={resumo?.taxa_comparecimento >= 85 ? "↑ Acima de 85%" : "↓ Abaixo de 85%"}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <Card>
          <p className="text-sm font-medium mb-1">Status por semana</p>
          <p className="text-xs text-gray-400 mb-3">Realizado · Cancelado · Faltou</p>
          {lS ? (
            <div className="h-52 bg-gray-100 animate-pulse rounded" />
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={semana || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="semana" tickFormatter={(v) => `Sem ${v}`} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend iconSize={10} iconType="square" />
                <Bar dataKey="realizados" fill="#1D9E75" name="Realizado" stackId="a" radius={[0,0,0,0]} />
                <Bar dataKey="cancelados" fill="#E24B4A" name="Cancelado" stackId="a" />
                <Bar dataKey="faltou"     fill="#EF9F27" name="Faltou"    stackId="a" radius={[3,3,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card>
          <p className="text-sm font-medium mb-3">Próximos agendamentos</p>
          {loadingP ? (
            <div className="space-y-2">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="h-10 bg-gray-100 animate-pulse rounded" />
              ))}
            </div>
          ) : (
            <div className="overflow-auto max-h-56">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-100">
                    <th className="text-left pb-2">Paciente</th>
                    <th className="text-left pb-2">Especialidade</th>
                    <th className="text-left pb-2">Data/Hora</th>
                    <th className="text-left pb-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(proximos || []).map((row, i) => {
                    const st = STATUS_MAP[row.status] || { label: row.status, cor: "#888" };
                    return (
                      <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-2 font-medium">{row.nom_paciente}</td>
                        <td className="py-2 text-gray-500">{row.especialidade}</td>
                        <td className="py-2 text-gray-500">
                          {row.data_hora
                            ? new Date(row.data_hora).toLocaleString("pt-BR", {
                                day: "2-digit", month: "2-digit",
                                hour: "2-digit", minute: "2-digit",
                              })
                            : "—"}
                        </td>
                        <td className="py-2">
                          <span
                            className="px-2 py-0.5 rounded-full text-[10px] font-medium"
                            style={{ background: `${st.cor}20`, color: st.cor }}
                          >
                            {st.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </>
  );
}

// ─── Seção Pacientes ─────────────────────────────────────────────────────────
function SecaoPacientes({ periodo }) {
  const { data: resumo, loading: lR, error: eR } = useFetch("/api/pacientes/resumo", periodo);
  const { data: novos,  loading: lN }             = useFetch("/api/pacientes/novos-por-semana", periodo);
  const { data: faixa,  loading: lF }             = useFetch("/api/pacientes/faixa-etaria", periodo);

  return (
    <>
      {eR && <ErrorMsg msg={eR.message} />}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <KPI label="Atendidos no período"  value={num(resumo?.pacientes_atendidos)} loading={lR} />
        <KPI label="Novos cadastros"        value={num(resumo?.novos_cadastros)}     loading={lR} deltaUp={true} />
        <KPI label="Base total"             value={num(resumo?.total_base)}          loading={lR} />
        <KPI label="Retorno"               value={num(resumo?.retorno)}             loading={lR} deltaUp={true} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
        <Card>
          <p className="text-sm font-medium mb-1">Novos pacientes por semana</p>
          <p className="text-xs text-gray-400 mb-3">Cadastros realizados no período</p>
          {lN ? (
            <div className="h-48 bg-gray-100 animate-pulse rounded" />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={novos || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="semana" tickFormatter={(v) => `Sem ${v}`} tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line type="monotone" dataKey="novos" stroke="#D85A30"
                  strokeWidth={2} dot={{ r: 3 }} name="Novos pacientes" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card>
          <p className="text-sm font-medium mb-1">Faixa etária</p>
          <p className="text-xs text-gray-400 mb-3">Pacientes atendidos no período</p>
          {lF ? (
            <div className="h-48 bg-gray-100 animate-pulse rounded" />
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={faixa || []}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="faixa" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="qtd" fill="#534AB7" radius={[3, 3, 0, 0]} name="Pacientes" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>
    </>
  );
}

// ─── App principal ────────────────────────────────────────────────────────────
const ABAS = [
  { id: "financeiro",    label: "Financeiro" },
  { id: "atendimentos",  label: "Atendimentos" },
  { id: "agendamentos",  label: "Agendamentos" },
  { id: "pacientes",     label: "Pacientes" },
];

const PERIODOS_OPT = [
  { value: "7d",  label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "90d", label: "90 dias" },
];

export default function App() {
  const [aba,     setAba]     = useState("financeiro");
  const [periodo, setPeriodo] = useState("30d");
  const [dbOk,    setDbOk]    = useState(null);

  useEffect(() => {
    fetch(`${API}/api/health`)
      .then((r) => r.json())
      .then((d) => setDbOk(d.status === "ok"))
      .catch(() => setDbOk(false));
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 font-sans">
      {/* Header */}
      <header className="bg-white border-b border-gray-100 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-medium text-gray-900">Dashboard Clínica</h1>
          <p className="text-xs text-gray-400">Smart Pixeon · SQL Server</p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`text-xs px-2 py-1 rounded-full ${
              dbOk === null
                ? "bg-gray-100 text-gray-500"
                : dbOk
                ? "bg-emerald-50 text-emerald-600"
                : "bg-red-50 text-red-500"
            }`}
          >
            {dbOk === null ? "verificando…" : dbOk ? "● banco conectado" : "● sem conexão"}
          </span>
          <div className="flex gap-1">
            {PERIODOS_OPT.map((p) => (
              <button
                key={p.value}
                onClick={() => setPeriodo(p.value)}
                className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${
                  periodo === p.value
                    ? "bg-gray-900 text-white border-gray-900"
                    : "border-gray-200 text-gray-500 hover:bg-gray-50"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {/* Tabs */}
      <nav className="bg-white border-b border-gray-100 px-6">
        <div className="flex gap-1">
          {ABAS.map((a) => (
            <button
              key={a.id}
              onClick={() => setAba(a.id)}
              className={`px-4 py-3 text-sm border-b-2 transition-colors ${
                aba === a.id
                  ? "border-gray-900 text-gray-900 font-medium"
                  : "border-transparent text-gray-400 hover:text-gray-700"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
      </nav>

      {/* Conteúdo */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        {aba === "financeiro"   && <><SectionTitle>Indicadores financeiros</SectionTitle><SecaoFinanceiro   periodo={periodo} /></>}
        {aba === "atendimentos" && <><SectionTitle>Atendimentos</SectionTitle>          <SecaoAtendimentos periodo={periodo} /></>}
        {aba === "agendamentos" && <><SectionTitle>Agendamentos</SectionTitle>          <SecaoAgendamentos periodo={periodo} /></>}
        {aba === "pacientes"    && <><SectionTitle>Pacientes</SectionTitle>             <SecaoPacientes    periodo={periodo} /></>}
      </main>
    </div>
  );
}
