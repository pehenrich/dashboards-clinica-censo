import { useState, useEffect } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from "recharts";

const API = import.meta.env.VITE_API_URL || (
  window.location.hostname === "localhost" || window.location.hostname.startsWith("192.168.")
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "https://breaking-sarah-gmc-drum.trycloudflare.com"
);

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
      height: h, borderRadius: 10, background: "linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%)",
      backgroundSize: "200% 100%", animation: "shimmer 1.4s infinite",
    }} />
  );
}

export default function Recepcao({ periodo = "30d" }) {
  const [setor, setSetor] = useState("");
  const [ranking, setRanking] = useState([]);
  const [evolucao, setEvolucao] = useState([]);
  const [loadingRank, setLoadingRank] = useState(true);
  const [loadingEvol, setLoadingEvol] = useState(true);
  const [recepSel, setRecepSel] = useState(null);

  useEffect(() => {
    setLoadingRank(true);
    fetch(`${API}/api/recepcao/ranking?periodo=${periodo}&setor=${setor}`)
      .then(r => r.json())
      .then(d => { setRanking(d || []); setLoadingRank(false); })
      .catch(() => setLoadingRank(false));
  }, [periodo, setor]);

  useEffect(() => {
    setLoadingEvol(true);
    const recepParam = recepSel ? `&recepcionista=${encodeURIComponent(recepSel)}` : "";
    fetch(`${API}/api/recepcao/evolucao?periodo=${periodo}&setor=${setor}${recepParam}`)
      .then(r => r.json())
      .then(d => { setEvolucao(d || []); setLoadingEvol(false); })
      .catch(() => setLoadingEvol(false));
  }, [periodo, setor, recepSel]);

  // KPIs agregados do ranking
  const totalPacientes = ranking.reduce((s, r) => s + (r.total_pacientes || 0), 0);
  const esperaMedia = ranking.length
    ? ranking.filter(r => r.espera_media_min != null).reduce((s, r, _, a) => s + r.espera_media_min / a.length, 0)
    : null;
  const producaoTotal = ranking.reduce((s, r) => s + (r.producao_financeira || 0), 0);

  // Dados para gráfico de evolução diária (agrupa por data + turno)
  const diasMap = {};
  for (const r of evolucao) {
    const key = r.data;
    if (!diasMap[key]) diasMap[key] = { data: key, Manhã: 0, Tarde: 0 };
    diasMap[key][r.turno] = (diasMap[key][r.turno] || 0) + (r.total_pacientes || 0);
  }
  const diasData = Object.values(diasMap).sort((a, b) => a.data.localeCompare(b.data));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <style>{`@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }`}</style>

      {/* Filtros */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: "#6B7280" }}>Recepção:</span>
        {RECEPCOES.map(r => (
          <button key={r.cod} onClick={() => setSetor(r.cod)} style={{
            padding: "5px 14px", borderRadius: 20, fontSize: 12, fontWeight: 600,
            cursor: "pointer", border: "none", transition: "all 0.12s",
            background: setor === r.cod ? "#8B1A1A" : "#ECECEC",
            color: setor === r.cod ? "#fff" : "#374151",
          }}>{r.nome}</button>
        ))}
      </div>

      {/* KPI Cards */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <KpiCard label="Total de pacientes" value={num(totalPacientes)} color="#8B1A1A" />
        <KpiCard label="Tempo médio de recepção" value={min(esperaMedia)} sub="Do registro até abertura da OS" color="#D97706" />
        <KpiCard label="Produção financeira" value={brl(producaoTotal)} sub="Valor das OS abertas" color="#10B981" />
        <KpiCard label="Recepcionistas" value={num(ranking.length)} color="#7C3AED" />
      </div>

      {/* Ranking */}
      <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#111827", marginBottom: 14 }}>
          Ranking por Recepcionista
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
                  {["#", "Recepcionista", "Recepção", "Pacientes", "Tempo Recepção", "Produção"].map(h => (
                    <th key={h} style={{ padding: "8px 12px", textAlign: h === "#" || h === "Pacientes" || h === "Tempo Recepção" || h === "Produção" ? "center" : "left", fontWeight: 700, color: "#6B7280", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.05em", borderBottom: "1px solid #E5E7EB" }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {ranking.map((r, i) => {
                  const maxPac = ranking[0]?.total_pacientes || 1;
                  const pct = ((r.total_pacientes || 0) / maxPac) * 100;
                  const isSel = recepSel === r.login_recep;
                  return (
                    <tr key={r.login_recep + r.setor_cod} onClick={() => setRecepSel(isSel ? null : r.login_recep)}
                      style={{
                        cursor: "pointer", borderBottom: "1px solid #F3F4F6",
                        background: isSel ? "#FEF2F2" : i % 2 === 0 ? "#fff" : "#FAFAFA",
                        transition: "background 0.1s",
                      }}>
                      <td style={{ padding: "10px 12px", textAlign: "center", fontWeight: 700, color: "#9CA3AF", width: 36 }}>{i + 1}</td>
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
                      <td style={{ padding: "10px 12px", textAlign: "center", color: r.espera_media_min > 30 ? "#EF4444" : r.espera_media_min > 15 ? "#D97706" : "#10B981", fontWeight: 700 }}>
                        {min(r.espera_media_min)}
                      </td>
                      <td style={{ padding: "10px 12px", textAlign: "center", fontWeight: 700, color: "#10B981" }}>
                        {brl(r.producao_financeira)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {recepSel && (
              <div style={{ fontSize: 11, color: "#8B1A1A", marginTop: 8, textAlign: "center" }}>
                Clique novamente na linha para desselecionar e ver todos no gráfico abaixo.
              </div>
            )}
          </div>
        )}
      </div>

      {/* Gráfico de Evolução Diária */}
      <div style={{ background: "#fff", borderRadius: 12, padding: 20, boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#111827" }}>
            Evolução Diária por Turno
            {recepSel && <span style={{ fontSize: 11, color: "#8B1A1A", marginLeft: 8 }}>
              — {ranking.find(r => r.login_recep === recepSel)?.nome_recep || recepSel}
            </span>}
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
