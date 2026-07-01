// ServicosPorSexo.jsx — Dashboard de serviços por sexo
// Adicione ao App.jsx:
//   import ServicosPorSexo from "./ServicosPorSexo";
//   NAV: { id:"servicossexo", label:"Serviços por Sexo", icon:"activity", color:"#7C3AED", desc:"Top exames · M vs F" }
//   RENDER_MAP: servicossexo: (p) => <ServicosPorSexo periodo={p}/>
// OU use direto dentro do PacientesDB.jsx como seção extra.

import { useState, useEffect } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend, Cell,
} from "recharts";

const API = import.meta.env.VITE_API_URL || (
  window.location.hostname === "localhost" || window.location.hostname.startsWith("192.168.")
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "https://breaking-sarah-gmc-drum.trycloudflare.com"
);

const C = {
  masc:   "#0891B2",
  fem:    "#DB2777",
  text:   "#111827",
  sub:    "#6B7280",
  faint:  "#9CA3AF",
  border: "#F3F4F6",
};

const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";

function useFetch(path, deps = {}) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!path) return;
    setLoading(true);
    const p = new URLSearchParams(
      Object.fromEntries(Object.entries(deps).filter(([,v]) => v != null && v !== ""))
    );
    fetch(`${API}${path}?${p}`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [path, JSON.stringify(deps)]);
  return { data, loading };
}

const Skel = ({ h = 200 }) => (
  <div style={{ height: h, background: "#F3F4F6", borderRadius: 10,
    animation: "spulse 1.5s infinite" }} />
);

function Card({ children, title, subtitle, action, accent }) {
  return (
    <div style={{ background: "#fff", borderRadius: 16, overflow: "hidden",
      boxShadow: "0 1px 4px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.04)",
      borderTop: accent ? `3px solid ${accent}` : undefined }}>
      {(title || action) && (
        <div style={{ padding: "16px 20px 10px", display: "flex",
          alignItems: "flex-start", justifyContent: "space-between", gap: 8 }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, color: C.text }}>{title}</div>
            {subtitle && <div style={{ fontSize: 11, color: C.faint, marginTop: 2 }}>{subtitle}</div>}
          </div>
          {action && <div style={{ flexShrink: 0 }}>{action}</div>}
        </div>
      )}
      <div style={{ padding: title ? "0 20px 18px" : "18px 20px" }}>{children}</div>
    </div>
  );
}

function CTip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "#fff", border: "1px solid #E5E7EB", borderRadius: 10,
      padding: "10px 14px", fontSize: 12, boxShadow: "0 8px 24px rgba(0,0,0,0.12)",
      maxWidth: 260 }}>
      <div style={{ color: C.text, marginBottom: 6, fontWeight: 700, fontSize: 12,
        wordBreak: "break-word", whiteSpace: "normal" }}>{label}</div>
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color, fontWeight: 600, marginBottom: 2 }}>
          {p.name}: {Number(p.value).toLocaleString("pt-BR")}
        </div>
      ))}
    </div>
  );
}

function abrev(nome, max = 28) {
  if (!nome) return "";
  const s = nome.trim();
  if (s.length <= max) return s;
  return s.slice(0, max - 1) + "…";
}

// ── TOP POR SEXO ──────────────────────────────────────────────────────────────
// FIX: agora recebe `setor` e passa para a API
function TopPorSexo({ periodo, limite, setor }) {
  const { data: dataM, loading: lM } = useFetch("/api/pacientes/servicos-por-sexo",
    { periodo, limite, sexo: "M", setor });
  const { data: dataF, loading: lF } = useFetch("/api/pacientes/servicos-por-sexo",
    { periodo, limite, sexo: "F", setor });

  const renderLista = (lista, cor) => (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {(lista || []).map((r, i) => {
        const pct = Math.min((r.qtd / ((lista[0]?.qtd) || 1)) * 100, 100);
        return (
          <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 22, flexShrink: 0, fontSize: 11, fontWeight: 700,
              color: i < 3 ? cor : C.faint, textAlign: "right" }}>
              {i < 3 ? ["🥇","🥈","🥉"][i] : `#${i+1}`}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: C.text,
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                marginBottom: 3 }}>
                {r.nome_exame}
              </div>
              <div style={{ height: 5, background: "#F3F4F6", borderRadius: 3 }}>
                <div style={{ height: "100%", borderRadius: 3, background: cor,
                  width: `${pct}%`, transition: "width 0.4s" }} />
              </div>
            </div>
            <div style={{ fontSize: 13, fontWeight: 800, color: cor,
              minWidth: 40, textAlign: "right", flexShrink: 0 }}>
              {num(r.qtd)}
            </div>
          </div>
        );
      })}
    </div>
  );

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
      <Card title={`♂ Top ${limite} — Masculino`}
        subtitle="Exames mais realizados por homens" accent={C.masc}>
        {lM ? <Skel h={300} /> : renderLista(dataM, C.masc)}
      </Card>
      <Card title={`♀ Top ${limite} — Feminino`}
        subtitle="Exames mais realizados por mulheres" accent={C.fem}>
        {lF ? <Skel h={300} /> : renderLista(dataF, C.fem)}
      </Card>
    </div>
  );
}

// ── COMPARATIVO M vs F ────────────────────────────────────────────────────────
// FIX: agora recebe `setor` e passa para a API
function ComparativoMxF({ periodo, limite, setor }) {
  const { data, loading } = useFetch("/api/pacientes/servicos-comparativo",
    { periodo, limite, setor });

  const chartData = (data || [])
    .map(r => ({ ...r, label: abrev(r.nome_exame, 32) }))
    .sort((a, b) => b.total - a.total);

  const totalM = (data || []).reduce((s, r) => s + (r.masculino || 0), 0);
  const totalF = (data || []).reduce((s, r) => s + (r.feminino  || 0), 0);

  return (
    <Card title="Comparativo M vs F — Top Exames"
      subtitle={`${num(totalM)} realizados por homens · ${num(totalF)} por mulheres no período`}>
      {loading ? <Skel h={420} /> : (
        <ResponsiveContainer width="100%" height={Math.max(360, chartData.length * 28)}>
          <BarChart data={chartData} layout="vertical"
            margin={{ top: 4, right: 20, left: 8, bottom: 4 }} barSize={10} barGap={2}>
            <CartesianGrid strokeDasharray="2 4" stroke="#F3F4F6" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 10, fill: C.faint }}
              axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="label" width={200}
              tick={{ fontSize: 10, fill: C.text }} axisLine={false} tickLine={false} />
            <Tooltip content={<CTip />} />
            <Legend iconSize={8} iconType="circle"
              wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
            <Bar dataKey="masculino" fill={C.masc} radius={[0,4,4,0]} name="Masculino" />
            <Bar dataKey="feminino"  fill={C.fem}  radius={[0,4,4,0]} name="Feminino" />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

// ── DISPARIDADE M vs F ────────────────────────────────────────────────────────
function ExclusividadeCard({ data }) {
  if (!data || data.length === 0) return null;

  const comRatio = data
    .filter(r => r.masculino > 0 && r.feminino > 0)
    .map(r => ({
      ...r,
      ratio: r.masculino / (r.feminino || 1),
      dominio: r.masculino > r.feminino ? "M" : "F",
    }))
    .sort((a, b) => Math.abs(b.ratio - 1) - Math.abs(a.ratio - 1))
    .slice(0, 8);

  return (
    <Card title="Maior Diferença M vs F"
      subtitle="Exames com maior disparidade entre sexos">
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {comRatio.map((r, i) => {
          const total = r.masculino + r.feminino;
          const pctM  = Math.round((r.masculino / total) * 100);
          const pctF  = 100 - pctM;
          return (
            <div key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: C.text,
                  maxWidth: "60%", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.nome_exame}
                </span>
                <div style={{ display: "flex", gap: 10, fontSize: 11 }}>
                  <span style={{ color: C.masc, fontWeight: 700 }}>♂ {pctM}%</span>
                  <span style={{ color: C.fem,  fontWeight: 700 }}>♀ {pctF}%</span>
                </div>
              </div>
              <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden" }}>
                <div style={{ width: `${pctM}%`, background: C.masc, transition: "width 0.4s" }} />
                <div style={{ width: `${pctF}%`, background: C.fem,  transition: "width 0.4s" }} />
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ── MAIN ─────────────────────────────────────────────────────────────────────
// FIX: agora recebe `setor` como prop e passa para todos os sub-componentes
export default function ServicosPorSexo({ periodo = "30d", setor = "" }) {
  const [limite,     setLimite]     = useState(10);
  const [limiteComp, setLimiteComp] = useState(15);

  // FIX: `setor` agora é passado para o endpoint do comparativo
  const { data: comparativo } = useFetch("/api/pacientes/servicos-comparativo",
    { periodo, limite: limiteComp, setor });

  const totalM = (comparativo || []).reduce((s, r) => s + (r.masculino || 0), 0);
  const totalF = (comparativo || []).reduce((s, r) => s + (r.feminino  || 0), 0);
  const total  = totalM + totalF;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <style>{`@keyframes spulse {0%,100%{opacity:1}50%{opacity:.45}}`}</style>

      {/* ── KPIs ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
        {[
          { label: "Total de Exames",       value: num(total),             accent: "#7C3AED", icon: "🔬" },
          { label: "Realizados por Homens", value: num(totalM),            accent: C.masc,    icon: "♂",
            sub: total > 0 ? `${((totalM/total)*100).toFixed(0)}% do total` : "" },
          { label: "Realizados por Mulheres", value: num(totalF),          accent: C.fem,     icon: "♀",
            sub: total > 0 ? `${((totalF/total)*100).toFixed(0)}% do total` : "" },
          { label: "Exames Distintos",      value: num(comparativo?.length), accent: "#D97706", icon: "📋" },
        ].map(({ label, value, accent, icon, sub }) => (
          <div key={label} style={{ background: "#fff", borderRadius: 16,
            padding: "16px 18px", borderLeft: `4px solid ${accent}`,
            boxShadow: "0 1px 4px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.04)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 10, color: C.faint, fontWeight: 700,
                textTransform: "uppercase", letterSpacing: "0.09em" }}>{label}</span>
              <span style={{ fontSize: 18, opacity: 0.6 }}>{icon}</span>
            </div>
            <div style={{ fontSize: 24, fontWeight: 900, color: C.text,
              lineHeight: 1.1, marginTop: 6, letterSpacing: "-0.5px" }}>{value}</div>
            {sub && <div style={{ fontSize: 11, color: C.faint, marginTop: 4 }}>{sub}</div>}
          </div>
        ))}
      </div>

      {/* ── Controles ── */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, color: C.faint, fontWeight: 700 }}>Top ranking:</span>
        {[5, 10, 15, 20].map(n => (
          <button key={n} onClick={() => setLimite(n)} style={{
            padding: "5px 13px", borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: "pointer",
            border: `1.5px solid ${limite === n ? "#7C3AED" : "#E5E7EB"}`,
            background: limite === n ? "#7C3AED" : "#fff",
            color: limite === n ? "#fff" : C.faint,
          }}>{n}</button>
        ))}
        <span style={{ fontSize: 11, color: C.faint, fontWeight: 700, marginLeft: 12 }}>Comparativo:</span>
        {[10, 15, 20].map(n => (
          <button key={n} onClick={() => setLimiteComp(n)} style={{
            padding: "5px 13px", borderRadius: 8, fontSize: 11, fontWeight: 700, cursor: "pointer",
            border: `1.5px solid ${limiteComp === n ? "#7C3AED" : "#E5E7EB"}`,
            background: limiteComp === n ? "#7C3AED" : "#fff",
            color: limiteComp === n ? "#fff" : C.faint,
          }}>{n}</button>
        ))}
      </div>

      {/* ── Rankings separados ── */}
      {/* FIX: `setor` agora é passado adiante */}
      <TopPorSexo periodo={periodo} limite={limite} setor={setor} />

      {/* ── Comparativo barras ── */}
      {/* FIX: `setor` agora é passado adiante */}
      <ComparativoMxF periodo={periodo} limite={limiteComp} setor={setor} />

      {/* ── Disparidade ── */}
      <ExclusividadeCard data={comparativo} />
    </div>
  );
}
