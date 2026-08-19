import { useState, useEffect, Fragment } from "react";
import BriefingCard from "./BriefingCard";
import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Cell,
} from "recharts";

const API = `${window.location.protocol}//${window.location.host}`;

const brl = v => v != null
  ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v)
  : "—";
const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";
const min = v => v != null ? `${Math.round(v)} min` : "—";

const RECEPCOES = [
  { cod: "",    nome: "Todas" },
  { cod: "RCN", nome: "Consultórios" },
  { cod: "RDI", nome: "Diagnóstico" },
  { cod: "ROC", nome: "Ocupacional" },
  { cod: "RCI", nome: "Censo Imagem" },
];

const COR_MANHA = "#8B1A1A";
const COR_TARDE = "#D97706";

function fitFontSize(value, base, min) {
  const len = String(value ?? "").length;
  if (len <= 7) return base;
  if (len <= 10) return Math.round(base * 0.85);
  if (len <= 13) return Math.round(base * 0.7);
  return min;
}

function KpiCard({ label, value, sub, color = "#111827" }) {
  return (
    <div style={{
      background: `linear-gradient(135deg, ${color}3A 0%, ${color}14 100%)`,
      borderRadius: 16, padding: "18px 20px",
      border: `1.5px solid ${color}55`,
      boxShadow: `0 6px 18px ${color}22, 0 1px 4px rgba(0,0,0,0.05)`,
      display: "flex", flexDirection: "column", gap: 8, minWidth: 0,
      position: "relative", overflow: "hidden",
    }}>
      <div style={{ position:"absolute", right:-14, top:-14, width:80, height:80, borderRadius:"50%", background:`${color}20`, pointerEvents:"none" }}/>
      <div style={{ fontSize: 10, fontWeight: 800, color, textTransform: "uppercase", letterSpacing: "0.09em" }}>
        {label}
      </div>
      <div style={{ fontSize: fitFontSize(value,26,14), fontWeight: 900, color:"#111827", lineHeight: 1.15, letterSpacing:"-0.5px", overflowWrap:"anywhere" }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color:"#fff", fontWeight:700, background:color, borderRadius:6, padding:"2px 8px", display:"inline-block", alignSelf:"flex-start" }}>{sub}</div>}
    </div>
  );
}

function Skeleton({ h = 200 }) {
  return (
    <div style={{
      height: h, borderRadius: 10,
      background: "linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%)",
      backgroundSize: "200% 100%", animation: "shimmer 1.4s infinite",
    }} />
  );
}

function ThSort({ col, label, tip, sortCol, sortDir, onSort, align = "center" }) {
  const active = sortCol === col;
  return (
    <th onClick={() => onSort(col)} title={tip || label} style={{
      padding: "8px 12px", textAlign: align, fontWeight: 700,
      color: active ? "#8B1A1A" : "#6B7280", fontSize: 11,
      textTransform: "uppercase", letterSpacing: "0.05em",
      borderBottom: "1px solid #E5E7EB", cursor: "pointer",
      userSelect: "none", whiteSpace: "nowrap",
    }}>
      {label}{" "}
      <span style={{ opacity: active ? 1 : 0.35 }}>
        {active ? (sortDir === "asc" ? "↑" : "↓") : "↕"}
      </span>
    </th>
  );
}

const CORES_RECEP_HORARIO = { RDI: "#7C3AED", ROC: "#D97706", RCN: "#8B1A1A", RCI: "#059669" };

function GraficoMediaPorHorario({ periodo }) {
  const [dados, setDados] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/api/recepcao/media-por-horario?periodo=${periodo}`)
      .then(r => r.json())
      .then(d => { setDados(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [periodo]);

  const linha = dados?.dados || [];
  const recepcoes = dados?.recepcoes || [];

  // pico por recepção — pra destacar cada uma
  const picos = recepcoes.map(r => {
    const pico = linha.reduce((max, d) => (d[r.cod] || 0) > (max?.v || 0) ? { hora: d.hora, v: d[r.cod] } : max, null);
    return pico ? { ...r, ...pico } : null;
  }).filter(Boolean);

  return (
    <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
      <div style={{ marginBottom: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#111827" }}>Quantidade de Pacientes por Horário</div>
        <div style={{ fontSize: 11, color: "#9CA3AF" }}>
          Chegada (recepção), total no período, por ponto de recepção{dados ? ` · ${dados.dias_considerados} dias considerados` : ""}
        </div>
      </div>

      {!loading && picos.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          {picos.map(p => (
            <div key={p.cod} style={{
              display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 8,
              background: `${CORES_RECEP_HORARIO[p.cod]}12`, border: `1px solid ${CORES_RECEP_HORARIO[p.cod]}30`,
            }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: CORES_RECEP_HORARIO[p.cod] }} />
              <span style={{ fontSize: 11, fontWeight: 700, color: "#374151" }}>{p.nome}</span>
              <span style={{ fontSize: 11, fontWeight: 800, color: CORES_RECEP_HORARIO[p.cod] }}>🔥 {p.hora} · {p.v}</span>
            </div>
          ))}
        </div>
      )}

      {loading ? <Skeleton h={220} /> : linha.length === 0 ? (
        <div style={{ textAlign: "center", padding: 40, color: "#9CA3AF", fontSize: 13 }}>Sem dados</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={linha} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
            <XAxis dataKey="hora" tick={{ fontSize: 10 }} />
            <YAxis tick={{ fontSize: 10 }} allowDecimals={false} />
            <Tooltip
              formatter={(v, cod) => [`${v} pacientes`, recepcoes.find(r => r.cod === cod)?.nome || cod]}
              labelFormatter={l => `Horário: ${l}`}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
            <Legend formatter={v => recepcoes.find(r => r.cod === v)?.nome || v} wrapperStyle={{ fontSize: 11 }} />
            {recepcoes.map(r => (
              <Line key={r.cod} type="monotone" dataKey={r.cod} stroke={CORES_RECEP_HORARIO[r.cod] || "#9CA3AF"}
                strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 6 }} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

function PainelPontualidade() {
  const hoje = new Date();
  const primeiroDiaMes = new Date(hoje.getFullYear(), hoje.getMonth(), 1).toISOString().slice(0, 10);
  const hojeStr = hoje.toISOString().slice(0, 10);

  const [usuarios, setUsuarios] = useState([]);
  const [login, setLogin] = useState("");
  const [inicio, setInicio] = useState(primeiroDiaMes);
  const [fim, setFim] = useState(hojeStr);
  const [dados, setDados] = useState(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState(null);
  const [baixando, setBaixando] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/recepcao/usuarios`).then(r => r.json()).then(setUsuarios).catch(() => setUsuarios([]));
  }, []);

  const gerar = () => {
    if (!login) return;
    setLoading(true); setErro(null); setDados(null);
    fetch(`${API}/api/recepcao/pontualidade?login=${encodeURIComponent(login)}&inicio=${inicio}&fim=${fim}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setDados)
      .catch(e => setErro(e.message))
      .finally(() => setLoading(false));
  };

  const baixarPdf = () => {
    if (!login) return;
    setBaixando(true);
    const url = `${API}/api/recepcao/pontualidade/pdf?login=${encodeURIComponent(login)}&inicio=${inicio}&fim=${fim}`;
    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.blob(); })
      .then(blob => {
        const link = document.createElement("a");
        link.href = URL.createObjectURL(blob);
        link.download = `Pontualidade_${login}_${inicio}_a_${fim}.pdf`;
        link.click();
        URL.revokeObjectURL(link.href);
      })
      .catch(e => setErro(e.message))
      .finally(() => setBaixando(false));
  };

  const gapCor = (g) => g == null ? "#9CA3AF" : g >= 30 ? "#DC2626" : g >= 10 ? "#D97706" : "#059669";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div style={{ background: "#fff", borderRadius: 12, padding: 18, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 2 }}>Relatório de Pontualidade</div>
        <div style={{ fontSize: 11.5, color: "#9CA3AF", marginBottom: 14 }}>
          Compara o horário de login no sistema com a criação da primeira OS do dia (mais confiável que a chamada na fila, que às vezes é lançada fora de ordem)
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
          <div style={{ minWidth: 220 }}>
            <label style={{ fontSize: 11, color: "#64748B", fontWeight: 700, display: "block", marginBottom: 4 }}>Recepcionista</label>
            <select value={login} onChange={e => setLogin(e.target.value)} style={{
              width: "100%", padding: "9px 10px", borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 13, outline: "none",
            }}>
              <option value="">— Selecione —</option>
              {usuarios.map(u => <option key={u.login} value={u.login}>{u.nome}</option>)}
            </select>
          </div>
          <div>
            <label style={{ fontSize: 11, color: "#64748B", fontWeight: 700, display: "block", marginBottom: 4 }}>De</label>
            <input type="date" value={inicio} onChange={e => setInicio(e.target.value)} style={{
              padding: "9px 10px", borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 13, outline: "none",
            }}/>
          </div>
          <div>
            <label style={{ fontSize: 11, color: "#64748B", fontWeight: 700, display: "block", marginBottom: 4 }}>Até</label>
            <input type="date" value={fim} onChange={e => setFim(e.target.value)} style={{
              padding: "9px 10px", borderRadius: 8, border: "1px solid #E2E8F0", fontSize: 13, outline: "none",
            }}/>
          </div>
          <button onClick={gerar} disabled={!login || loading} style={{
            padding: "10px 20px", borderRadius: 8, border: "none",
            background: login && !loading ? "#8B1A1A" : "#E2E8F0",
            color: login && !loading ? "#fff" : "#9CA3AF",
            fontSize: 13, fontWeight: 700, cursor: login && !loading ? "pointer" : "not-allowed",
          }}>{loading ? "Gerando..." : "Gerar Relatório"}</button>
          {dados && (
            <button onClick={baixarPdf} disabled={baixando} style={{
              padding: "10px 20px", borderRadius: 8, border: "1.5px solid #8B1A1A",
              background: "#fff", color: "#8B1A1A", fontSize: 13, fontWeight: 700,
              cursor: baixando ? "wait" : "pointer",
            }}>{baixando ? "Baixando..." : "📄 Baixar PDF"}</button>
          )}
        </div>
        {erro && <div style={{ color: "#DC2626", fontSize: 12.5, marginTop: 10 }}>{erro}</div>}
      </div>

      {loading && <Skeleton h={300} />}

      {dados && !loading && (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 14 }}>
            <KpiCard label="Dias no período" value={num(dados.resumo.dias)} color="#8B1A1A" />
            <KpiCard label="Intervalo médio" value={min(dados.resumo.intervalo_medio_min)} sub="Login → atendimento" color="#D97706" />
            <KpiCard label="Total de atendimentos" value={num(dados.resumo.total_atendimentos)} color="#10B981" />
            <KpiCard label="Média/dia" value={num(dados.resumo.media_atendimentos_dia)} color="#7C3AED" />
          </div>

          <div style={{ background: "#fff", borderRadius: 12, padding: 18, boxShadow: "0 1px 4px rgba(0,0,0,0.07)", overflowX: "auto" }}>
            {dados.linhas.length === 0 ? (
              <div style={{ textAlign: "center", padding: 40, color: "#9CA3AF", fontSize: 13 }}>Sem dados no período</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ borderBottom: "2px solid #E2E8F0" }}>
                    <th style={{ textAlign: "left", padding: "8px 10px", color: "#64748B" }}>Data</th>
                    <th style={{ textAlign: "left", padding: "8px 10px", color: "#64748B" }}>Dia</th>
                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#64748B" }}>Login</th>
                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#64748B" }}>Início Atendimento</th>
                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#64748B" }}>Intervalo</th>
                    <th style={{ textAlign: "right", padding: "8px 10px", color: "#64748B" }}>Atendimentos</th>
                  </tr>
                </thead>
                <tbody>
                  {dados.linhas.map((l, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid #F1F5F9", background: (l.gap_min || 0) >= 30 ? "#FEF2F2" : "transparent" }}>
                      <td style={{ padding: "8px 10px", fontWeight: 700, color: "#334155" }}>{l.dia}</td>
                      <td style={{ padding: "8px 10px", color: "#64748B" }}>{l.dia_semana}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right", color: "#334155" }}>{l.login || "—"}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right", color: "#334155" }}>{l.atendimento || "—"}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 800, color: gapCor(l.gap_min) }}>
                        {l.gap_min != null ? `${l.gap_min} min` : "—"}
                      </td>
                      <td style={{ padding: "8px 10px", textAlign: "right", color: "#64748B" }}>{l.qtd}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function Recepcao({ periodo = "30d" }) {
  const [abaRecep, setAbaRecep] = useState("geral");
  const [setor, setSetor] = useState("");
  const [ranking, setRanking] = useState([]);
  const [evolucao, setEvolucao] = useState([]);
  const [loadingRank, setLoadingRank] = useState(true);
  const [loadingEvol, setLoadingEvol] = useState(true);
  const [recepSel, setRecepSel] = useState(null);
  const [expandKey, setExpandKey] = useState(null);
  const [convenios, setConvenios] = useState([]);
  const [loadingConv, setLoadingConv] = useState(false);
  const [sortCol, setSortCol] = useState("total_pacientes");
  const [sortDir, setSortDir] = useState("desc");
  const [porConvenio, setPorConvenio] = useState([]);
  const [loadingConvAgg, setLoadingConvAgg] = useState(true);
  const [metas, setMetas] = useState(null);
  const [loadingMetas, setLoadingMetas] = useState(true);
  const [filtroTempoRecep, setFiltroTempoRecep] = useState("");

  useEffect(() => {
    setLoadingMetas(true);
    fetch(`${API}/api/recepcao/metas?periodo=${periodo}&setor=${setor}`)
      .then(r => r.json())
      .then(d => { setMetas(d || null); setLoadingMetas(false); })
      .catch(() => setLoadingMetas(false));
  }, [periodo, setor]);

  useEffect(() => {
    setLoadingRank(true);
    fetch(`${API}/api/recepcao/ranking?periodo=${periodo}&setor=${setor}`)
      .then(r => r.json())
      .then(d => { setRanking(d || []); setLoadingRank(false); })
      .catch(() => setLoadingRank(false));
  }, [periodo, setor]);

  useEffect(() => {
    setLoadingConvAgg(true);
    fetch(`${API}/api/recepcao/por-convenio?periodo=${periodo}&setor=${setor}`)
      .then(r => r.json())
      .then(d => { setPorConvenio(d || []); setLoadingConvAgg(false); })
      .catch(() => setLoadingConvAgg(false));
  }, [periodo, setor]);

  useEffect(() => {
    setLoadingEvol(true);
    const p = recepSel ? `&recepcionista=${encodeURIComponent(recepSel)}` : "";
    fetch(`${API}/api/recepcao/evolucao?periodo=${periodo}&setor=${setor}${p}`)
      .then(r => r.json())
      .then(d => { setEvolucao(d || []); setLoadingEvol(false); })
      .catch(() => setLoadingEvol(false));
  }, [periodo, setor, recepSel]);

  const handleSort = (col) => {
    if (sortCol === col) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("desc"); }
  };

  const handleRowClick = (r) => {
    const key = `${r.login_recep}|${r.setor_cod}`;
    if (expandKey === key) {
      setExpandKey(null);
      setRecepSel(null);
      return;
    }
    setExpandKey(key);
    setRecepSel(r.login_recep);
    setLoadingConv(true);
    setConvenios([]);
    fetch(`${API}/api/recepcao/convenios?periodo=${periodo}&setor=${setor}&recepcionista=${encodeURIComponent(r.login_recep)}`)
      .then(res => res.json())
      .then(d => { setConvenios(d || []); setLoadingConv(false); })
      .catch(() => setLoadingConv(false));
  };

  const handleSetorChange = (cod) => {
    setSetor(cod);
    setExpandKey(null);
    setRecepSel(null);
  };

  const sortedRanking = [...ranking].sort((a, b) => {
    let va = a[sortCol], vb = b[sortCol];
    if (va == null) va = sortDir === "asc" ? Infinity : -Infinity;
    if (vb == null) vb = sortDir === "asc" ? Infinity : -Infinity;
    if (typeof va === "string") return sortDir === "asc" ? va.localeCompare(vb) : vb.localeCompare(va);
    return sortDir === "asc" ? va - vb : vb - va;
  });

  const maxPac = Math.max(...ranking.map(r => r.total_pacientes || 0), 1);

  const totalPacientes = ranking.reduce((s, r) => s + (r.total_pacientes || 0), 0);
  const validEsperas = ranking.filter(r => r.espera_media_min != null);
  const esperaMedia = validEsperas.length
    ? validEsperas.reduce((s, r) => s + r.espera_media_min, 0) / validEsperas.length
    : null;
  const producaoTotal = ranking.reduce((s, r) => s + (r.producao_financeira || 0), 0);

  const diasMap = {};
  for (const r of evolucao) {
    if (!diasMap[r.data]) diasMap[r.data] = { data: r.data, Manhã: 0, Tarde: 0 };
    diasMap[r.data][r.turno] = (diasMap[r.data][r.turno] || 0) + (r.total_pacientes || 0);
  }
  const diasData = Object.values(diasMap).sort((a, b) => a.data.localeCompare(b.data));

  const top3 = sortedRanking.slice(0, 3);
  const setorLabel = RECEPCOES.find(r => r.cod === setor)?.nome || "Todas";

  const convPorPacientes = [...porConvenio].sort((a,b)=>(b.total_pacientes||0)-(a.total_pacientes||0)).slice(0,10);
  const convPorEspera = [...porConvenio]
    .filter(c => c.espera_media_min != null && c.total_pacientes >= 2)
    .sort((a,b)=>(b.espera_media_min||0)-(a.espera_media_min||0)).slice(0,10);
  const recepPorTempo = [...ranking]
    .filter(r => r.espera_media_min != null)
    .sort((a,b)=>(a.espera_media_min||0)-(b.espera_media_min||0));

  const MESES_PT = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];
  const now = new Date();
  const periodoLabel = periodo === "hoje"
    ? `Hoje (${now.toLocaleDateString("pt-BR")})`
    : periodo === "30d"
      ? `${MESES_PT[now.getMonth()]} de ${now.getFullYear()}`
      : periodo === "ano"
        ? `Ano ${now.getFullYear()}`
        : periodo;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <style>{`@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}`}</style>

      {/* Abas do módulo Recepção */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {[{ id: "geral", label: "Visão Geral" }, { id: "pontualidade", label: "⏱️ Pontualidade" }].map(a => (
          <button key={a.id} onClick={() => setAbaRecep(a.id)} style={{
            padding: "9px 20px", borderRadius: 12, fontSize: 13, fontWeight: 700,
            cursor: "pointer", border: "none", transition: "all 0.15s",
            background: abaRecep === a.id ? "#8B1A1A" : "#fff",
            color: abaRecep === a.id ? "#fff" : "#64748B",
            boxShadow: abaRecep === a.id ? "0 4px 16px #8B1A1A40" : "0 1px 3px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.05)",
          }}>{a.label}</button>
        ))}
      </div>

      {abaRecep === "pontualidade" && <PainelPontualidade />}
      {abaRecep === "geral" && <>

      {/* Filtro de recepção — afeta todo o módulo (KPIs, gráficos e ranking) */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap",
        background: "#fff", borderRadius: 12, padding: "12px 16px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: "#374151" }}>📍 Filtrar por recepção:</span>
        {RECEPCOES.map(r => (
          <button key={r.cod} onClick={() => handleSetorChange(r.cod)} style={{
            padding: "6px 14px", borderRadius: 20, fontSize: 12, fontWeight: 700,
            cursor: "pointer", border: "none", transition: "all 0.12s",
            background: setor === r.cod ? "#8B1A1A" : "#F3F4F6",
            color: setor === r.cod ? "#fff" : "#374151",
          }}>{r.nome}</button>
        ))}
      </div>

      <BriefingCard
        cor="#D97706"
        cacheKey={`briefing_recepcao_${periodoLabel}_${setor}`}
        disabled={loadingRank}
        promptFn={() => {
          const t3 = top3.map((r, i) => `${i+1}. ${r.nome_recep||r.login_recep}: ${r.total_pacientes} pacientes, espera ${r.espera_media_min != null ? Math.round(r.espera_media_min)+"min" : "n/d"}`).join("; ");
          return `Você é um analista de gestão clínica. Gere um briefing executivo em no máximo 4 frases curtas, direto e profissional, sem markdown.

DADOS — Módulo Recepção (${setorLabel}, período: ${periodoLabel}):
- Total de pacientes recepcionados: ${totalPacientes}
- Tempo médio de espera na recepção: ${esperaMedia != null ? Math.round(esperaMedia)+"min" : "n/d"}
- Produção financeira total: R$ ${producaoTotal != null ? producaoTotal.toLocaleString("pt-BR",{minimumFractionDigits:0,maximumFractionDigits:0}) : "n/d"}
- Nº de recepcionistas ativos: ${ranking.length}
- Top 3 recepcionistas: ${t3.length ? t3 : "n/d"}

Destaque pontos positivos, alertas de espera e sugestões para melhorar o fluxo.`;
        }}
      />

      {/* KPI Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 16 }}>
        <KpiCard label="Total de pacientes" value={num(totalPacientes)} color="#8B1A1A" />
        <KpiCard label="Tempo médio de recepção" value={min(esperaMedia)} sub="Da senha até a chamada" color="#D97706" />
        <KpiCard label="Produção financeira" value={brl(producaoTotal)} sub="Valor das OS abertas" color="#10B981" />
        <KpiCard label="Recepcionistas" value={num(ranking.length)} color="#7C3AED" />
      </div>

      {/* Metas de Recepção — calculadas a partir do histórico dos últimos 3 meses */}
      <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 2 }}>Metas de Recepção</div>
        <div style={{ fontSize: 11, color: "#9CA3AF", marginBottom: 14 }}>
          Metas calculadas com base na média histórica dos últimos 3 meses
          {metas?.periodo_historico ? ` (${metas.periodo_historico.inicio} a ${metas.periodo_historico.fim})` : ""}
        </div>

        {loadingMetas ? <Skeleton h={160} /> : (
          <>
            <div style={{ fontSize: 11, fontWeight: 800, color: "#059669", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 10 }}>
              💰 Meta de Produção por Recepção
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(190px,1fr))", gap: 10, marginBottom: 20 }}>
              {(metas?.producao_por_recepcao || []).map(p => {
                const cor = p.pct == null ? "#9CA3AF" : p.pct >= 100 ? "#059669" : p.pct >= 60 ? "#D97706" : "#DC2626";
                return (
                  <div key={p.recepcao_cod} style={{
                    background: `linear-gradient(135deg, ${cor}18 0%, ${cor}08 100%)`,
                    borderRadius: 12, padding: "12px 14px", border: `1.5px solid ${cor}35`,
                  }}>
                    <div style={{ fontSize: 12, fontWeight: 800, color: "#111827", marginBottom: 8 }}>
                      {p.recepcao_nome.replace(/^Recepção /, "")}
                    </div>
                    <div style={{ fontSize: 16, fontWeight: 900, color: cor }}>{brl(p.atual)}</div>
                    <div style={{ fontSize: 10, color: "#6B7280", marginBottom: 6 }}>
                      de {p.meta_mensal ? brl(p.meta_mensal) : "—"} (meta mensal)
                    </div>
                    <div style={{ height: 6, background: "#F1F5F9", borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${Math.min(100, p.pct || 0)}%`, background: cor, borderRadius: 3, transition: "width 0.6s" }}/>
                    </div>
                    <div style={{ fontSize: 10, color: cor, fontWeight: 700, marginTop: 4 }}>
                      {p.pct != null ? `${p.pct}% da meta` : "sem histórico"}
                    </div>
                  </div>
                );
              })}
            </div>

            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 800, color: "#D97706", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                ⏱ Meta de Tempo Médio de Atendimento por Recepcionista
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {RECEPCOES.map(r => (
                  <button key={r.cod} onClick={() => setFiltroTempoRecep(r.cod)} style={{
                    padding: "4px 12px", borderRadius: 20, fontSize: 11, fontWeight: 700,
                    cursor: "pointer", border: "none", transition: "all 0.12s",
                    background: filtroTempoRecep === r.cod ? "#D97706" : "#F3F4F6",
                    color: filtroTempoRecep === r.cod ? "#fff" : "#6B7280",
                  }}>{r.nome}</button>
                ))}
              </div>
            </div>
            <div style={{ fontSize: 11, color: "#6B7280", marginBottom: 10 }}>
              Meta: até <b>{min(metas?.meta_tempo_atendimento_min)}</b> (média histórica geral) · senha até a chamada
            </div>
            {recepPorTempo.filter(r => !filtroTempoRecep || r.setor_cod === filtroTempoRecep).length === 0 ? (
              <div style={{ textAlign: "center", padding: 24, color: "#9CA3AF", fontSize: 12 }}>Sem dados de tempo no período</div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 8 }}>
                {recepPorTempo.filter(r => !filtroTempoRecep || r.setor_cod === filtroTempoRecep).map(r => {
                  const metaMin = metas?.meta_tempo_atendimento_min;
                  const dentro = metaMin != null && r.espera_media_min <= metaMin;
                  const cor = metaMin == null ? "#9CA3AF" : dentro ? "#059669" : "#DC2626";
                  return (
                    <div key={`${r.login_recep}|${r.setor_cod}`} style={{
                      display: "flex", justifyContent: "space-between", alignItems: "center",
                      padding: "8px 12px", borderRadius: 8, background: `${cor}10`, border: `1px solid ${cor}30`,
                    }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 12, fontWeight: 700, color: "#111827", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {r.nome_recep || r.login_recep}
                        </div>
                        <div style={{ fontSize: 10, color: "#9CA3AF" }}>{r.setor_nome}</div>
                      </div>
                      <div style={{ textAlign: "right", flexShrink: 0, marginLeft: 8 }}>
                        <div style={{ fontSize: 13, fontWeight: 800, color: cor }}>{min(r.espera_media_min)}</div>
                        <div style={{ fontSize: 9, fontWeight: 700, color: cor }}>{metaMin == null ? "" : dentro ? "✓ dentro" : "✕ acima"}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>

      {/* Ranking */}
      <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 14 }}>
          Ranking por Recepcionista {setor && <span style={{ fontSize: 11, color: "#8B1A1A", fontWeight: 600 }}>— {setorLabel}</span>}
        </div>

        {loadingRank ? <Skeleton h={180} /> : ranking.length === 0 ? (
          <div style={{ textAlign: "center", padding: 40, color: "#9CA3AF", fontSize: 13 }}>
            Nenhum dado encontrado para o período.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
              <thead>
                <tr style={{ background: "#F9FAFB" }}>
                  <th style={{ padding: "8px 12px", width: 36, borderBottom: "1px solid #E5E7EB" }}>#</th>
                  <ThSort col="nome_recep"          label="Recepcionista"   tip="Funcionário que fez o check-in/recepção do paciente"                                  sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="left" />
                  <ThSort col="setor_nome"          label="Recepção"        tip="Guichê/setor onde o paciente foi recepcionado (Consultórios, Diagnóstico, etc.)"      sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="left" />
                  <ThSort col="total_pacientes"     label="Pacientes"       tip="Quantidade de pacientes distintos recepcionados no período"                            sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <ThSort col="espera_media_min"    label="Tempo recepção"  tip="Tempo médio entre a chegada do paciente (senha) e a chamada real; usa a abertura da guia (OS) quando não há chamada registrada" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <ThSort col="producao_financeira" label="Produção"        tip="Valor líquido das guias abertas para os pacientes que passaram por essa recepção"      sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <th style={{ width: 28, borderBottom: "1px solid #E5E7EB" }} />
                </tr>
              </thead>
              <tbody>
                {sortedRanking.map((r, i) => {
                  const key = `${r.login_recep}|${r.setor_cod}`;
                  const isExp = expandKey === key;
                  const pct = ((r.total_pacientes || 0) / maxPac) * 100;
                  const espCor = r.espera_media_min > 30 ? "#EF4444" : r.espera_media_min > 15 ? "#D97706" : "#10B981";
                  return (
                    <Fragment key={key}>
                      <tr onClick={() => handleRowClick(r)} style={{
                        cursor: "pointer",
                        borderBottom: isExp ? "none" : "1px solid #F3F4F6",
                        background: isExp ? "#FEF2F2" : i % 2 === 0 ? "#fff" : "#FAFAFA",
                        transition: "background 0.1s",
                      }}>
                        <td style={{ padding: "10px 12px", textAlign: "center", fontWeight: 700, color: "#9CA3AF" }}>{i + 1}</td>
                        <td style={{ padding: "10px 12px" }}>
                          <div style={{ fontWeight: 700, color: "#111827" }}>{r.nome_recep || r.login_recep}</div>
                          <div style={{ fontSize: 10, color: "#9CA3AF" }}>{r.login_recep}</div>
                        </td>
                        <td style={{ padding: "10px 12px", color: "#6B7280" }}>{r.setor_nome}</td>
                        <td style={{ padding: "10px 12px", textAlign: "center" }}>
                          <div style={{ fontWeight: 800, color: "#8B1A1A", marginBottom: 3 }}>{num(r.total_pacientes)}</div>
                          <div style={{ height: 4, borderRadius: 2, background: "#F3F4F6", width: 80, margin: "0 auto" }}>
                            <div style={{ height: 4, borderRadius: 2, background: "#8B1A1A", width: `${pct}%` }} />
                          </div>
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "center", fontWeight: 700, color: espCor }}>
                          {min(r.espera_media_min)}
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "center", fontWeight: 700, color: "#10B981" }}>
                          {brl(r.producao_financeira)}
                        </td>
                        <td style={{ padding: "10px 12px", textAlign: "center", fontSize: 13, color: isExp ? "#8B1A1A" : "#9CA3AF" }}>
                          {isExp ? "▲" : "▼"}
                        </td>
                      </tr>

                      {isExp && (
                        <tr style={{ background: "#FEF9F9", borderBottom: "2px solid #F5C6C6" }}>
                          <td colSpan={7} style={{ padding: "14px 20px 18px 52px" }}>
                            <div style={{ fontSize: 12, fontWeight: 700, color: "#8B1A1A", marginBottom: 10 }}>
                              Convênios — {r.nome_recep || r.login_recep}
                            </div>
                            {loadingConv ? (
                              <div style={{ color: "#9CA3AF", fontSize: 12 }}>Carregando...</div>
                            ) : convenios.length === 0 ? (
                              <div style={{ color: "#9CA3AF", fontSize: 12 }}>Sem dados de convênio.</div>
                            ) : (
                              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                                {convenios.map(c => {
                                  const maxOs = convenios[0]?.total_os || 1;
                                  const pctC = ((c.total_os || 0) / maxOs) * 100;
                                  return (
                                    <div key={c.convenio} style={{
                                      background: "#fff", border: "1px solid #E5E7EB",
                                      borderRadius: 8, padding: "10px 14px", minWidth: 150,
                                    }}>
                                      <div style={{ fontSize: 11, color: "#6B7280", fontWeight: 600, marginBottom: 4 }}>
                                        {c.convenio}
                                      </div>
                                      <div style={{ fontSize: 20, fontWeight: 800, color: "#111827", lineHeight: 1 }}>
                                        {num(c.total_os)}
                                      </div>
                                      <div style={{ fontSize: 10, color: "#9CA3AF", marginBottom: 5 }}>OS</div>
                                      <div style={{ height: 3, borderRadius: 2, background: "#F3F4F6" }}>
                                        <div style={{ height: 3, borderRadius: 2, background: "#8B1A1A", width: `${pctC}%` }} />
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            )}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pacientes por Convênio + Tempo de Recepção por Convênio */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(320px,1fr))", gap: 16 }}>
        <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 2 }}>Pacientes Atendidos por Convênio</div>
          <div style={{ fontSize: 11, color: "#9CA3AF", marginBottom: 14 }}>Top 10 convênios · {setorLabel}</div>
          {loadingConvAgg ? <Skeleton h={260} /> : convPorPacientes.length === 0 ? (
            <div style={{ textAlign: "center", padding: 40, color: "#9CA3AF", fontSize: 13 }}>Sem dados</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={convPorPacientes} layout="vertical" margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10 }} allowDecimals={false} />
                <YAxis type="category" dataKey="convenio" width={110} tick={{ fontSize: 10 }}
                  tickFormatter={v => v?.length > 16 ? v.slice(0,16)+"…" : v} />
                <Tooltip formatter={v => [num(v), "Pacientes"]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="total_pacientes" fill="#8B1A1A" radius={[0,4,4,0]} barSize={16} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 2 }}>Tempo Médio de Recepção por Convênio</div>
          <div style={{ fontSize: 11, color: "#9CA3AF", marginBottom: 14 }}>Senha até a chamada · convênios com 2+ pacientes</div>
          {loadingConvAgg ? <Skeleton h={260} /> : convPorEspera.length === 0 ? (
            <div style={{ textAlign: "center", padding: 40, color: "#9CA3AF", fontSize: 13 }}>Sem dados suficientes</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={convPorEspera} layout="vertical" margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
                <XAxis type="number" tick={{ fontSize: 10 }} unit="min" />
                <YAxis type="category" dataKey="convenio" width={110} tick={{ fontSize: 10 }}
                  tickFormatter={v => v?.length > 16 ? v.slice(0,16)+"…" : v} />
                <Tooltip formatter={v => [`${Math.round(v)} min`, "Tempo médio"]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
                <Bar dataKey="espera_media_min" radius={[0,4,4,0]} barSize={16}>
                  {convPorEspera.map((c,i) => (
                    <Cell key={i} fill={c.espera_media_min > 30 ? "#EF4444" : c.espera_media_min > 15 ? "#D97706" : "#10B981"} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Tempo Médio de Recepção por Recepcionista */}
      <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 2 }}>Tempo Médio de Recepção por Recepcionista</div>
        <div style={{ fontSize: 11, color: "#9CA3AF", marginBottom: 14 }}>Da senha até a chamada real · {setorLabel}</div>
        {loadingRank ? <Skeleton h={Math.max(160, recepPorTempo.length*28)} /> : recepPorTempo.length === 0 ? (
          <div style={{ textAlign: "center", padding: 40, color: "#9CA3AF", fontSize: 13 }}>Sem dados</div>
        ) : (
          <ResponsiveContainer width="100%" height={Math.max(160, recepPorTempo.length*28)}>
            <BarChart data={recepPorTempo} layout="vertical" margin={{ top: 4, right: 30, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10 }} unit="min" />
              <YAxis type="category" dataKey="nome_recep" width={130} tick={{ fontSize: 10 }}
                tickFormatter={v => v?.length > 18 ? v.slice(0,18)+"…" : v} />
              <Tooltip formatter={v => [`${Math.round(v)} min`, "Tempo médio"]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Bar dataKey="espera_media_min" radius={[0,4,4,0]} barSize={14} label={{ position:"right", fontSize:10, formatter: v => `${Math.round(v)}min` }}>
                {recepPorTempo.map((r,i) => (
                  <Cell key={i} fill={r.espera_media_min > 30 ? "#EF4444" : r.espera_media_min > 15 ? "#D97706" : "#10B981"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Gráfico de Evolução Diária */}
      <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#111827" }}>
            Evolução Diária por Turno
            {recepSel && (
              <span style={{ fontSize: 11, color: "#8B1A1A", marginLeft: 8 }}>
                — {ranking.find(r => r.login_recep === recepSel)?.nome_recep || recepSel}
                <span
                  onClick={() => { setRecepSel(null); setExpandKey(null); }}
                  style={{ marginLeft: 6, cursor: "pointer", textDecoration: "underline" }}
                >
                  ✕ limpar
                </span>
              </span>
            )}
          </div>
          <div style={{ fontSize: 11, color: "#9CA3AF" }}>Manhã = até 13h · Tarde = 13h em diante</div>
        </div>
        {loadingEvol ? <Skeleton h={220} /> : diasData.length === 0 ? (
          <div style={{ textAlign: "center", padding: 40, color: "#9CA3AF", fontSize: 13 }}>Sem dados</div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={diasData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
              <XAxis dataKey="data" tick={{ fontSize: 10 }} tickFormatter={d => d.slice(5)} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip
                formatter={(v, name) => [num(v), name]}
                labelFormatter={l => `Dia ${l}`}
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="Manhã" fill={COR_MANHA} radius={[3, 3, 0, 0]} stackId="a" />
              <Bar dataKey="Tarde" fill={COR_TARDE} radius={[3, 3, 0, 0]} stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      <GraficoMediaPorHorario periodo={periodo} />
      </>}
    </div>
  );
}
