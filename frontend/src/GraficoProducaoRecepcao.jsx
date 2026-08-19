import { useState, useEffect, useCallback } from "react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from "recharts";

const API = `${window.location.protocol}//${window.location.host}`;

const brl = v => v != null
  ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v)
  : "—";

const CORES = { RDI: "#7C3AED", ROC: "#D97706", RCN: "#8B1A1A", RCI: "#059669" };
const MESES = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];

function Skeleton({ h = 260 }) {
  return (
    <div style={{
      height: h, borderRadius: 10,
      background: "linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%)",
      backgroundSize: "200% 100%", animation: "shimmer 1.4s infinite",
    }} />
  );
}

export default function GraficoProducaoRecepcao({ titulo = "📊 Produção Diária por Recepção" }) {
  const hoje = new Date();
  const [ano, setAno] = useState(hoje.getFullYear());
  const [mes, setMes] = useState(hoje.getMonth() + 1);
  const [dados, setDados] = useState(null);
  const [loading, setLoading] = useState(true);

  const carregar = useCallback(() => {
    setLoading(true);
    fetch(`${API}/api/financeiro/producao-diaria-recepcao?ano=${ano}&mes=${mes}`)
      .then(r => r.json())
      .then(d => { setDados(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [ano, mes]);

  useEffect(() => { carregar(); }, [carregar]);

  const mudarMes = (delta) => {
    let m = mes + delta, a = ano;
    if (m > 12) { m = 1; a++; } else if (m < 1) { m = 12; a--; }
    setMes(m); setAno(a);
  };

  const ehMesAtual = ano === hoje.getFullYear() && mes === hoje.getMonth() + 1;
  const recepcoes = dados?.recepcoes || [];
  const totais = dados?.totais || {};

  return (
    <div style={{ background: "#fff", borderRadius: 14, padding: "20px 22px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#374151" }}>{titulo}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <button onClick={() => mudarMes(-1)} style={{
            width: 28, height: 28, borderRadius: 8, border: "1px solid #E5E7EB", background: "#fff",
            cursor: "pointer", fontSize: 13, color: "#6B7280",
          }}>‹</button>
          <div style={{
            fontSize: 12.5, fontWeight: 700, color: "#111827", minWidth: 118, textAlign: "center",
            padding: "5px 10px", borderRadius: 8, background: "#F8FAFC",
          }}>{MESES[mes - 1]} {ano}{ehMesAtual && <span style={{ color: "#8B1A1A" }}> ·</span>}</div>
          <button onClick={() => mudarMes(1)} disabled={ano === hoje.getFullYear() && mes === hoje.getMonth() + 1} style={{
            width: 28, height: 28, borderRadius: 8, border: "1px solid #E5E7EB",
            background: (ano === hoje.getFullYear() && mes === hoje.getMonth() + 1) ? "#F8FAFC" : "#fff",
            cursor: (ano === hoje.getFullYear() && mes === hoje.getMonth() + 1) ? "not-allowed" : "pointer",
            fontSize: 13, color: (ano === hoje.getFullYear() && mes === hoje.getMonth() + 1) ? "#D1D5DB" : "#6B7280",
          }}>›</button>
        </div>
      </div>

      {!loading && recepcoes.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 14 }}>
          {recepcoes.map(r => (
            <div key={r.cod} style={{
              display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 8,
              background: `${CORES[r.cod]}12`, border: `1px solid ${CORES[r.cod]}30`,
            }}>
              <span style={{ width: 8, height: 8, borderRadius: "50%", background: CORES[r.cod] }} />
              <span style={{ fontSize: 11, fontWeight: 700, color: "#374151" }}>{r.nome}</span>
              <span style={{ fontSize: 11, fontWeight: 800, color: CORES[r.cod] }}>{brl(totais[r.cod])}</span>
            </div>
          ))}
          <div style={{
            display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 8,
            background: "#F8FAFC", border: "1px solid #E5E7EB",
          }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: "#6B7280" }}>Total do mês</span>
            <span style={{ fontSize: 11, fontWeight: 800, color: "#111827" }}>{brl(totais.total)}</span>
          </div>
        </div>
      )}

      {loading ? <Skeleton /> : (dados?.dias?.length || 0) === 0 ? (
        <div style={{ textAlign: "center", padding: 40, color: "#9CA3AF", fontSize: 13 }}>Sem produção nesse mês.</div>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={dados.dias} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
            <XAxis dataKey="data" tick={{ fontSize: 10, fill: "#9CA3AF" }} tickFormatter={v => v?.slice(8)} />
            <YAxis tick={{ fontSize: 10, fill: "#9CA3AF" }} tickFormatter={v => `R$${(v / 1000).toFixed(0)}k`} width={52} />
            <Tooltip
              formatter={(v, nome) => [brl(v), recepcoes.find(r => r.cod === nome)?.nome || nome]}
              labelFormatter={l => `${l?.slice(8)}/${l?.slice(5, 7)}/${l?.slice(0, 4)}`}
              contentStyle={{ borderRadius: 10, border: "1px solid #E5E7EB", fontSize: 12 }}
            />
            <Legend
              formatter={v => recepcoes.find(r => r.cod === v)?.nome || v}
              wrapperStyle={{ fontSize: 11 }}
            />
            {recepcoes.map(r => (
              <Line key={r.cod} type="monotone" dataKey={r.cod} stroke={CORES[r.cod] || "#9CA3AF"}
                strokeWidth={2.5} dot={{ r: 3 }} activeDot={{ r: 5 }} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
