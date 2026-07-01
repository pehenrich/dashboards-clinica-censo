import { useState, useEffect, Fragment } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
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
  { cod: "RPS", nome: "Pro Saúde" },
  { cod: "RCI", nome: "Censo Imagem" },
];

const COR_MANHA = "#8B1A1A";
const COR_TARDE = "#D97706";

function KpiCard({ label, value, sub, color = "#111827" }) {
  return (
    <div style={{
      background: "#fff", borderRadius: 12, padding: "18px 20px",
      boxShadow: "0 1px 4px rgba(0,0,0,0.07)", flex: 1, minWidth: 140,
      borderLeft: `4px solid ${color}`,
    }}>
      <div style={{ fontSize: 11, fontWeight: 700, color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 24, fontWeight: 800, color, lineHeight: 1.1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 4 }}>{sub}</div>}
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

function ThSort({ col, label, sortCol, sortDir, onSort, align = "center" }) {
  const active = sortCol === col;
  return (
    <th onClick={() => onSort(col)} style={{
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

export default function Recepcao({ periodo = "30d" }) {
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

  useEffect(() => {
    setLoadingRank(true);
    fetch(`${API}/api/recepcao/ranking?periodo=${periodo}&setor=${setor}`)
      .then(r => r.json())
      .then(d => { setRanking(d || []); setLoadingRank(false); })
      .catch(() => setLoadingRank(false));
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <style>{`@keyframes shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}`}</style>

      {/* KPI Cards */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <KpiCard label="Total de pacientes" value={num(totalPacientes)} color="#8B1A1A" />
        <KpiCard label="Tempo médio de recepção" value={min(esperaMedia)} sub="Do registro até abertura da OS" color="#D97706" />
        <KpiCard label="Produção financeira" value={brl(producaoTotal)} sub="Valor das OS abertas" color="#10B981" />
        <KpiCard label="Recepcionistas" value={num(ranking.length)} color="#7C3AED" />
      </div>

      {/* Ranking */}
      <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        {/* Header + filtro de recepção */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10, marginBottom: 14 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#111827" }}>Ranking por Recepcionista</div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "#9CA3AF", marginRight: 2 }}>Recepção:</span>
            {RECEPCOES.map(r => (
              <button key={r.cod} onClick={() => handleSetorChange(r.cod)} style={{
                padding: "4px 12px", borderRadius: 20, fontSize: 11, fontWeight: 600,
                cursor: "pointer", border: "none", transition: "all 0.12s",
                background: setor === r.cod ? "#8B1A1A" : "#F3F4F6",
                color: setor === r.cod ? "#fff" : "#374151",
              }}>{r.nome}</button>
            ))}
          </div>
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
                  <ThSort col="nome_recep"          label="Recepcionista"   sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="left" />
                  <ThSort col="setor_nome"          label="Recepção"        sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="left" />
                  <ThSort col="total_pacientes"     label="Pacientes"       sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <ThSort col="espera_media_min"    label="Tempo recepção"  sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <ThSort col="producao_financeira" label="Produção"        sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
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
    </div>
  );
}
