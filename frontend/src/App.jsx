import { useState, useEffect, useRef, createContext, useContext } from "react";
const MobileCtx = createContext(false);
const useMobile = () => useContext(MobileCtx);
import PainelTV from "./PainelTV";
import PacientesDB from "./PacientesDB";
import ModuloContratos from "./ModuloContratos";
import Recepcao from "./Recepcao";
import Login, { AuthProvider, useAuth, AdminPermissoes } from "./Login";
import {
  BarChart, Bar, LineChart, Line, PieChart, Pie, Cell,
  ComposedChart, Area, ReferenceLine,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend
} from "recharts";
import Home from "./Home";
import BriefingCard from "./BriefingCard";

const BACKEND_TUNNEL = "https://breaking-sarah-gmc-drum.trycloudflare.com";
const API = `${window.location.protocol}//${window.location.host}`;

const CORES_ANOS = ["#8B1A1A","#D97706","#7C3AED","#059669","#0891B2"];
const CORES_ESP  = ["#8B1A1A","#059669","#D97706","#7C3AED","#DC2626","#0891B2","#DB2777","#65A30D"];
const MESES_LABEL = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];

const GRUPOS = [
  { value: "",    label: "Todos"        },
  { value: "ASS", label: "Assistencial" },
];
const MOC_VALS = new Set(["ADM","PER","DEM","RTB","MDF","MOC"]);

// ── CORES / TEMA ───────────────────────────────────────────────────────────────
const T = {
  bg:      "#EEEEEE",   // cinza claro — fundo geral
  surface: "#FFFFFF",   // branco — cards
  border:  "#E2E8F0",   // borda sutil cinza
  text:    "#0F172A",   // quase preto
  muted:   "#64748B",   // cinza médio
  accent:  "#8B1A1A",   // azul
  green:   "#059669",   // verde
  amber:   "#D97706",   // âmbar
  red:     "#DC2626",   // vermelho
  violet:  "#7C3AED",   // roxo
  header:  "#1E293B",   // topbar escura
};

// ── HELPERS ───────────────────────────────────────────────────────────────────
const brl  = (v) => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";
const brlk = (v) => v != null ? `R$${(Number(v)/1000).toFixed(0)}k` : "—";
const num  = (v) => v != null ? Number(v).toLocaleString("pt-BR") : "—";
const pct  = (v) => v != null ? `${Number(v).toFixed(1)}%` : "—";

function useIsMobile() {
  const [mobile, setMobile] = useState(window.innerWidth < 768);
  useEffect(() => {
    const handler = () => setMobile(window.innerWidth < 768);
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);
  return mobile;
}

function useFetch(path, deps = {}, intervalMs = 0) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const load = () => {
    if (!path || deps?.skip) { setLoading(false); setData(null); return; }
    setLoading(true); setError(null);
    const params = new URLSearchParams(
      Object.fromEntries(Object.entries(deps).filter(([k,v]) => k !== "skip" && v != null && v !== ""))
    );
    fetch(`${API}${path}?${params}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(setData).catch(setError).finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    if (intervalMs > 0) {
      const id = setInterval(load, intervalMs);
      return () => clearInterval(id);
    }
  }, [path, JSON.stringify(deps)]);

  return { data, loading, error };
}

// Reduz a fonte do valor conforme o comprimento do texto, para nunca cortar (ex: valores em R$)
function fitFontSize(value, base, min) {
  const len = String(value ?? "").length;
  if (len <= 7) return base;
  if (len <= 10) return Math.round(base * 0.85);
  if (len <= 13) return Math.round(base * 0.7);
  return min;
}

// ── KPI CARD ──────────────────────────────────────────────────────────────────
function KPI({ label, value, sub, deltaUp, loading, accent }) {
  const ac = accent || "#8B1A1A";
  const isUp   = deltaUp === true;
  const isDown = deltaUp === false;
  return (
    <div style={{
      background: `linear-gradient(135deg, ${ac}38 0%, ${ac}12 100%)`,
      borderRadius: 16, padding: "20px 22px",
      border: `1.5px solid ${ac}55`,
      boxShadow: `0 6px 20px ${ac}20, 0 1px 3px rgba(0,0,0,0.05)`,
      display: "flex", flexDirection: "column", gap: 8, minWidth: 0,
      position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position:"absolute", right:-12, top:-12,
        width:72, height:72, borderRadius:"50%",
        background:`${ac}22`, pointerEvents:"none",
      }}/>
      <span style={{ fontSize:10, color: ac, fontWeight:800, textTransform:"uppercase", letterSpacing:"0.1em" }}>{label}</span>
      {loading
        ? <div style={{ height:34, width:"65%", background:`${ac}20`, borderRadius:8, animation:"pulse 1.5s infinite" }}/>
        : <div style={{ fontSize:fitFontSize(value,24,13), fontWeight:900, color:"#111827", lineHeight:1.15, letterSpacing:"-0.5px", overflowWrap:"anywhere" }}>{value}</div>
      }
      {sub && (
        <span style={{
          fontSize:11, fontWeight:700,
          color: isUp?"#059669" : isDown?"#EF4444" : "#64748B",
          background: isUp?"#D1FAE5" : isDown?"#FEE2E2" : "#F1F5F9",
          borderRadius:6, padding:"2px 8px", display:"inline-block", alignSelf:"flex-start",
        }}>
          {isUp?"↑ ": isDown?"↓ ":""}{sub}
        </span>
      )}
    </div>
  );
}

function Skeleton({ h = 200 }) {
  return <div style={{ height:h, background:"linear-gradient(90deg,#F1F5F9 25%,#E2E8F0 50%,#F1F5F9 75%)", backgroundSize:"200% 100%", borderRadius:12, animation:"shimmer 1.5s infinite" }}/>;
}

function Err({ msg }) {
  return (
    <div style={{ background:"#FEF2F2", border:"1.5px solid #FECACA", color:"#DC2626", borderRadius:12, padding:"12px 16px", fontSize:13, marginBottom:12, display:"flex", alignItems:"center", gap:10 }}>
      <span style={{ fontSize:18 }}>⚠</span> {msg}
    </div>
  );
}

function Card({ children, title, subtitle, action, accent, style: ex={} }) {
  return (
    <div style={{ background:"#fff", borderRadius:16, overflow:"hidden", boxShadow:"0 2px 8px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.04)", ...ex }}>
      {(title||action) && (
        <div style={{
          padding:"16px 22px 12px",
          display:"flex", alignItems:"flex-start", justifyContent:"space-between",
          borderBottom: "1px solid #F1F5F9",
        }}>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            {accent && <div style={{ width:4, height:20, borderRadius:3, background:accent, flexShrink:0 }}/>}
            <div>
              <div style={{ fontSize:14, fontWeight:800, color:"#111827" }}>{title}</div>
              {subtitle && <div style={{ fontSize:11, color:"#94A3B8", marginTop:1, fontWeight:500 }}>{subtitle}</div>}
            </div>
          </div>
          {action}
        </div>
      )}
      <div style={{ padding: title ? "16px 22px 20px" : "20px 22px" }}>{children}</div>
    </div>
  );
}

// Componente hero para cabeçalho de módulo com gradiente
function ModuleHero({ title, subtitle, cor, stats, loading }) {
  const mobile = useMobile();
  return (
    <div style={{
      background: `linear-gradient(135deg, ${cor} 0%, ${cor}CC 100%)`,
      borderRadius: 20, padding: mobile ? "20px 18px" : "28px 32px", marginBottom: 20,
      boxShadow: `0 8px 32px ${cor}40`,
      position:"relative", overflow:"hidden",
    }}>
      <div style={{ position:"absolute", right:-30, top:-30, width:200, height:200, borderRadius:"50%", background:"rgba(255,255,255,0.07)", pointerEvents:"none" }}/>
      <div style={{ position:"absolute", right:60, bottom:-60, width:160, height:160, borderRadius:"50%", background:"rgba(255,255,255,0.05)", pointerEvents:"none" }}/>
      <div style={{ position:"relative" }}>
        <div style={{ fontSize: mobile?17:20, fontWeight:900, color:"#fff", marginBottom:4, letterSpacing:"-0.3px" }}>{title}</div>
        {subtitle && <div style={{ fontSize:13, color:"rgba(255,255,255,0.75)", marginBottom: mobile?16:24, fontWeight:500 }}>{subtitle}</div>}
        {stats && (
          <div style={{ display:"grid", gridTemplateColumns:`repeat(auto-fit,minmax(${mobile?100:130}px,1fr))`, gap: mobile?10:16 }}>
            {stats.map((s,i) => (
              <div key={i} style={{ background:"rgba(255,255,255,0.15)", borderRadius:12, padding: mobile?"10px 12px":"12px 16px", backdropFilter:"blur(4px)", minWidth:0 }}>
                <div style={{ fontSize:10, color:"rgba(255,255,255,0.8)", fontWeight:700, textTransform:"uppercase", letterSpacing:"0.08em", marginBottom:4, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{s.label}</div>
                <div style={{ fontSize:fitFontSize(s.value,22,13), fontWeight:900, color:"#fff", lineHeight:1.15, overflowWrap:"anywhere" }}>
                  {loading ? <span style={{ opacity:0.4 }}>—</span> : s.value}
                </div>
                <div style={{ display:"flex", alignItems:"center", gap:6, flexWrap:"wrap", marginTop:3 }}>
                  {s.sub && <span style={{ fontSize:10, color:"rgba(255,255,255,0.7)" }}>{s.sub}</span>}
                  {!loading && s.trend != null && (
                    <span style={{
                      fontSize:10, fontWeight:800, padding:"1px 6px", borderRadius:99,
                      color: s.trend >= 0 ? "#065F46" : "#7F1D1D",
                      background: s.trend >= 0 ? "rgba(209,250,229,0.9)" : "rgba(254,226,226,0.9)",
                    }}>
                      {s.trend >= 0 ? "↑" : "↓"} {Math.abs(s.trend).toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {stats?.some(s => s.trend != null) && (
          <div style={{ fontSize:10, color:"rgba(255,255,255,0.55)", marginTop:10 }}>
            ↑↓ variação vs. período anterior equivalente
          </div>
        )}
      </div>
    </div>
  );
}

// Barra de progresso de meta mensal por módulo — persiste via /api/metas
function MetaModulo({ modulo, cor, atual, periodo }) {
  const [meta, setMeta] = useState(undefined); // undefined = carregando, null = sem meta definida
  const [editando, setEditando] = useState(false);
  const [tmp, setTmp] = useState("");
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    let cancelado = false;
    fetch(`${API}/api/metas`)
      .then(r => r.json())
      .then(d => { if (!cancelado) setMeta(d?.[modulo]?.meta_mensal ?? null); })
      .catch(() => { if (!cancelado) setMeta(null); });
    return () => { cancelado = true; };
  }, [modulo]);

  if (periodo !== "30d" || meta === undefined) return null; // meta é mensal — só faz sentido no mês atual

  const brl = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v) : "—";

  const salvar = async () => {
    const valor = Number(tmp);
    if (!valor || valor <= 0) return;
    setSalvando(true);
    try {
      await fetch(`${API}/api/metas/${modulo}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ meta_mensal: valor }),
      });
      setMeta(valor);
      setEditando(false);
    } catch (e) {}
    setSalvando(false);
  };

  if (!meta) {
    return editando ? (
      <div style={{ display:"flex", gap:8, alignItems:"center", flexWrap:"wrap", background:"#fff", borderRadius:12, padding:"10px 14px", border:`1.5px solid ${cor}30`, marginBottom:16 }}>
        <span style={{ fontSize:12, color:"#6B7280", fontWeight:700 }}>Meta mensal (R$):</span>
        <input type="number" value={tmp} onChange={e=>setTmp(e.target.value)} autoFocus
          style={{ padding:"6px 10px", borderRadius:8, border:"1px solid #E5E7EB", width:140, fontSize:13, fontWeight:700 }}/>
        <button onClick={salvar} disabled={salvando} style={{ background:cor, color:"#fff", border:"none", borderRadius:8, padding:"6px 14px", fontWeight:700, fontSize:12, cursor:"pointer" }}>Salvar</button>
        <button onClick={()=>setEditando(false)} style={{ background:"transparent", border:"none", color:"#9CA3AF", cursor:"pointer", fontSize:12 }}>Cancelar</button>
      </div>
    ) : (
      <button onClick={()=>{ setTmp(""); setEditando(true); }} style={{
        background:"transparent", border:`1.5px dashed ${cor}50`, borderRadius:10, padding:"8px 14px",
        color:cor, fontSize:12, fontWeight:700, cursor:"pointer", marginBottom:16,
      }}>+ Definir meta mensal</button>
    );
  }

  const pctMeta = Math.min(100, ((atual||0)/meta)*100);
  const corBarra = pctMeta >= 100 ? "#059669" : pctMeta >= 70 ? cor : pctMeta >= 40 ? "#D97706" : "#DC2626";

  return (
    <div style={{ background:"#fff", borderRadius:14, padding:"14px 18px", marginBottom:16,
      border:"1px solid #E5E7EB", boxShadow:"0 1px 3px rgba(0,0,0,0.06)" }}>
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:8, flexWrap:"wrap", gap:6 }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <span style={{ fontSize:11, fontWeight:800, color:"#6B7280", textTransform:"uppercase", letterSpacing:"0.06em" }}>🎯 Meta Mensal</span>
          <span style={{ fontSize:12, fontWeight:700, color:corBarra }}>{pctMeta.toFixed(0)}%</span>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
          {editando ? (
            <>
              <input type="number" value={tmp} onChange={e=>setTmp(e.target.value)} autoFocus
                style={{ padding:"4px 8px", borderRadius:6, border:"1px solid #E5E7EB", width:110, fontSize:12 }}/>
              <button onClick={salvar} disabled={salvando} style={{ background:cor, color:"#fff", border:"none", borderRadius:6, padding:"4px 10px", fontWeight:700, fontSize:11, cursor:"pointer" }}>Salvar</button>
              <button onClick={()=>setEditando(false)} style={{ background:"transparent", border:"none", color:"#9CA3AF", cursor:"pointer", fontSize:11 }}>Cancelar</button>
            </>
          ) : (
            <>
              <span style={{ fontSize:12, color:"#374151" }}>{brl(atual)} <span style={{color:"#9CA3AF"}}>de</span> {brl(meta)}</span>
              <button onClick={()=>{ setTmp(meta); setEditando(true); }} style={{ background:"transparent", border:"none", color:"#9CA3AF", cursor:"pointer", fontSize:14 }} title="Editar meta">⚙</button>
            </>
          )}
        </div>
      </div>
      <div style={{ height:8, background:"#F1F5F9", borderRadius:4, overflow:"hidden" }}>
        <div style={{ height:"100%", background:corBarra, borderRadius:4, width:`${pctMeta}%`, transition:"width 0.6s ease" }}/>
      </div>
    </div>
  );
}

function CTip({ active, payload, label, fmt }) {
  if (!active||!payload?.length) return null;
  return (
    <div style={{ background:"#fff", border:"1px solid #E5E7EB", borderRadius:10, padding:"10px 14px", fontSize:12, boxShadow:"0 8px 24px rgba(0,0,0,0.12)" }}>
      {label && <div style={{ color:"#111827", marginBottom:6, fontWeight:700, fontSize:13 }}>{label}</div>}
      {payload.map((p,i) => (
        <div key={i} style={{ color:p.color||"#6B7280", fontWeight:600, marginBottom:2 }}>{p.name}: {fmt?fmt(p.value):p.value}</div>
      ))}
    </div>
  );
}

function SeletorAnos({ value, onChange }) {
  return (
    <div style={{ display:"flex", alignItems:"center", gap:4 }}>
      <span style={{ fontSize:11, color:"#6B7280", fontWeight:600 }}>Anos:</span>
      {[1,2,3,4,5].map(n => (
        <button key={n} onClick={() => onChange(n)} style={{
          width: 28, height: 24, borderRadius: 6, border: "none", cursor: "pointer", fontSize: 11, fontWeight: 700,
          background: value === n ? "#8B1A1A" : "#334155",
          color: value === n ? "#0F172A" : "#6B7280",
          transition: "all 0.15s",
        }}>{n}a</button>
      ))}
    </div>
  );
}

// ── FILTRO TIPO ATENDIMENTO ───────────────────────────────────────────────────
function FiltroAtend({ value, onChange }) {
  const [popAberto, setPopAberto] = useState(false);
  const popRef = useRef(null);
  const isMoc = MOC_VALS.has(value);

  useEffect(() => {
    const h = (e) => { if (popRef.current && !popRef.current.contains(e.target)) setPopAberto(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const btnBase = (ativo) => ({
    padding: "6px 14px", borderRadius: 8, border: `1px solid ${ativo ? "#8B1A1A" : "#EAEDF2"}`,
    background: ativo ? "#8B1A1A" : "#fff", color: ativo ? "#0F172A" : "#6B7280",
    fontSize: 12, fontWeight: 600, cursor: "pointer", transition: "all 0.15s", whiteSpace: "nowrap",
  });

  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 10, color: "#6B7280", fontWeight: 700, textTransform:"uppercase", letterSpacing:"0.08em", marginBottom: 8 }}>
        Tipo de atendimento
      </div>
      <div style={{ display:"flex", flexWrap:"wrap", gap:6, alignItems:"center" }}>
        {GRUPOS.map(g => {
          if (g.filhos) {
            const ativo = isMoc;
            const label = isMoc ? (g.filhos.find(f => f.value === value)?.label || g.label) : g.label;
            return (
              <div key={g.value} style={{ position:"relative" }} ref={popRef}>
                <button onClick={() => setPopAberto(v => !v)} style={{
                  ...btnBase(ativo),
                  background: ativo ? "#8B5CF6" : "#fff",
                  borderColor: ativo ? "#8B5CF6" : "#EAEDF2",
                  color: ativo ? "#fff" : "#6B7280",
                  display:"flex", alignItems:"center", gap:5,
                }}>
                  {label}
                  <span style={{ fontSize:9, opacity:0.7, transform: popAberto ? "rotate(180deg)" : "none", display:"inline-block", transition:"transform 0.15s" }}>▼</span>
                </button>
                {popAberto && (
                  <div style={{
                    position:"absolute", top:"calc(100% + 6px)", left:0, zIndex:100,
                    background:"#fff", border:`1px solid ${"#EAEDF2"}`, borderRadius:10,
                    padding:6, minWidth:160, boxShadow:"0 8px 32px rgba(0,0,0,0.5)",
                  }}>
                    <div style={{ fontSize:10, color:"#6B7280", fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em", padding:"4px 8px 8px" }}>
                      Med. Ocupacional
                    </div>
                    {g.filhos.map(f => (
                      <button key={f.value} onClick={() => { onChange(f.value); setPopAberto(false); }} style={{
                        display:"block", width:"100%", textAlign:"left", padding:"8px 10px",
                        borderRadius:7, border:"none", cursor:"pointer", fontSize:12, fontWeight:600,
                        background: value === f.value ? "#334155" : "transparent",
                        color: value === f.value ? "#8B1A1A" : "#6B7280",
                        transition:"all 0.1s",
                      }}>
                        {f.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            );
          }
          return (
            <button key={g.value} onClick={() => { onChange(g.value); setPopAberto(false); }}
              style={btnBase(value === g.value)}>
              {g.label}
            </button>
          );
        })}
        {value && (
          <button onClick={() => { onChange(""); setPopAberto(false); }} style={{
            background:"transparent", border:"none", color:"#EF4444", fontSize:12, cursor:"pointer", padding:"6px 8px", fontWeight:600,
          }}>✕</button>
        )}
      </div>
    </div>
  );
}

// ── GRÁFICO COMPARATIVO ANUAL ─────────────────────────────────────────────────
function GraficoComparativoAnual({ titulo, subtitulo, endpoint, deps, dataKey, fmt, height = 200 }) {
  const [anos, setAnos] = useState(2);
  const { data, loading } = useFetch(endpoint, { ...deps, anos });

  const isMensal = endpoint.includes("receita-mensal");
  let chartData = [];
  if (data && isMensal) {
    chartData = MESES_LABEL.map((mes, idx) => {
      const row = { mes };
      data.forEach(d => {
        const m = d.meses?.find(r => parseInt(r.mes_num) === idx + 1);
        row[d.ano] = m ? m[dataKey] : null;
      });
      return row;
    }).filter(r => Object.values(r).some((v, i) => i > 0 && v != null));
  } else if (data && Array.isArray(data)) {
    chartData = data;
  }
  const anoKeys = data ? data.map(d => d.ano) : [];

  return (
    <Card title={titulo} subtitle={subtitulo} action={<SeletorAnos value={anos} onChange={setAnos} />}>
      {loading ? <Skeleton h={height} /> : (
        <ResponsiveContainer width="100%" height={height}>
          {isMensal ? (
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
              <XAxis dataKey="mes" tick={{ fontSize:14, fill:"#64748B", fontWeight:700 }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={brlk} tick={{ fontSize:13, fill:"#64748B", fontWeight:600 }} axisLine={false} tickLine={false} width={55} />
              <Tooltip content={<CTip fmt={fmt || brl} />} />
              <Legend iconSize={18} iconType="circle" wrapperStyle={{ fontSize:14, color:"#0F172A", fontWeight:700, paddingTop:8 }} />
              {anoKeys.map((ano, i) => (
                <Line key={ano} type="monotone" dataKey={ano} name={ano}
                  stroke={CORES_ANOS[i % CORES_ANOS.length]} strokeWidth={5}
                  dot={{ r:8, strokeWidth:3, fill: CORES_ANOS[i % CORES_ANOS.length], stroke:"#fff" }}
                  activeDot={{ r:9 }}
                  connectNulls={false} />
              ))}
            </LineChart>
          ) : (
            <BarChart data={chartData} barGap={4}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
              <XAxis dataKey="ano" tick={{ fontSize:12, fill:"#64748B" }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={fmt === num ? num : brlk} tick={{ fontSize:11, fill:"#64748B" }} axisLine={false} tickLine={false} />
              <Tooltip content={<CTip fmt={fmt || brl} />} />
              <Bar dataKey={dataKey} radius={[6,6,0,0]} name={titulo}>
                {chartData.map((_,i) => <Cell key={i} fill={CORES_ANOS[i % CORES_ANOS.length]} />)}
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      )}
    </Card>
  );
}


// ── COMPARATIVO FATURAMENTO ANUAL ────────────────────────────────────────────


function ProducaoProfissionais({ ano, mes, API, setAno, setMes }) {
  const [dados,     setDados]     = useState([]);
  const [loading,   setLoading]   = useState(false);
  const [busca,     setBusca]     = useState("");
  const [espFiltro, setEspFiltro] = useState("");
  const [ordenar,   setOrdenar]   = useState("total_gerado");
  const [classeFiltro, setClasseFiltro] = useState("");
  const [expandido, setExpandido] = useState(null);
  const [detalhe,   setDetalhe]   = useState({});
  const [loadDet,   setLoadDet]   = useState(false);

  const brl = v => v != null ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v) : "--";
  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "--";

  useEffect(() => {
    if (!ano || !mes) return;
    setLoading(true);
    fetch(API + "/api/financeiro/producao-mensal/profissionais?ano=" + ano + "&mes=" + mes)
      .then(r => r.json())
      .then(d => {
        const enriched = (d || []).map(p => ({
          ...p,
          total_gerado: (p.producao_total || 0) + (p.producao_solicitada || 0),
        }));
        setDados(enriched);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [ano, mes]);

  const handleExpandir = async (prof) => {
    if (expandido === prof) { setExpandido(null); return; }
    setExpandido(prof);
    if (detalhe[prof]) return;
    setLoadDet(true);
    try {
      const r = await fetch(API + "/api/financeiro/producao-mensal/profissional-servicos?profissional=" + encodeURIComponent(prof) + "&ano=" + ano + "&mes=" + mes);
      const d = await r.json();
      setDetalhe(prev => ({ ...prev, [prof]: d }));
    } catch {}
    setLoadDet(false);
  };

  const filtrados = dados
    .filter(p => !busca || (p.profissional||"").toLowerCase().includes(busca.toLowerCase()))
    .filter(p => !espFiltro || (p.especialidades||[]).includes(espFiltro))
    .sort((a, b) => (b[ordenar]||0) - (a[ordenar]||0))
    .filter(p => !classeFiltro || (p.classes_executadas||[]).includes(classeFiltro) || (p.classes_solicitadas||[]).includes(classeFiltro))

const COLUNAS = [
  { id: "producao_total",      label: "Executado" },
  { id: "producao_solicitada", label: "Solicitado" },
];

  const totalExec  = filtrados.reduce((s, p) => s + (p.producao_total || 0), 0);
  const totalSolic = filtrados.reduce((s, p) => s + (p.producao_solicitada || 0), 0);

  return (
    <div style={{ background:"#fff", borderRadius:16, padding:"20px 24px", boxShadow:"0 1px 4px rgba(0,0,0,0.07)" }}>
      {/* Header */}
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:16, flexWrap:"wrap", gap:10 }}>
        <div style={{ fontSize:14, fontWeight:800, color:"#111827" }}>Produção por Profissional</div>
        <div style={{ display:"flex", gap:8, flexWrap:"wrap", alignItems:"center" }}>
          {setMes && setAno && (
            <>
              <select value={mes} onChange={e=>setMes(Number(e.target.value))} title="Mês" style={{
                padding:"7px 12px", borderRadius:8, border:"1px solid #E5E7EB", fontSize:12,
                outline:"none", background:"#fff", cursor:"pointer", fontWeight:600, color:"#111827",
              }}>
                {MESES_PT.map((m,i) => <option key={i+1} value={i+1}>{m}</option>)}
              </select>
              <select value={ano} onChange={e=>setAno(Number(e.target.value))} title="Ano" style={{
                padding:"7px 12px", borderRadius:8, border:"1px solid #E5E7EB", fontSize:12,
                outline:"none", background:"#fff", cursor:"pointer", fontWeight:600, color:"#111827",
              }}>
                {[new Date().getFullYear()-2, new Date().getFullYear()-1, new Date().getFullYear()].map(a=>(
                  <option key={a} value={a}>{a}</option>
                ))}
              </select>
            </>
          )}
          <input placeholder="Buscar profissional..." value={busca} onChange={e=>setBusca(e.target.value)}
            style={{ padding:"7px 12px", borderRadius:8, border:"1px solid #E5E7EB", fontSize:12, outline:"none", width:170 }}/>
          <select value={espFiltro} onChange={e=>setEspFiltro(e.target.value)}
            style={{ padding:"7px 12px", borderRadius:8, border:"1px solid #E5E7EB", fontSize:12, outline:"none", background:"#fff", cursor:"pointer" }}>
            <option value="">Todas especialidades</option>
            {[...new Set(dados.flatMap(p=>p.especialidades||[]))].sort().map(e=>(<option key={e} value={e}>{e}</option>))}
          </select>
          <select value={classeFiltro} onChange={e=>setClasseFiltro(e.target.value)}
            style={{ padding:"7px 12px", borderRadius:8, border:"1px solid #E5E7EB", fontSize:12, outline:"none", background:"#fff", cursor:"pointer" }}>
            <option value="">Todas as classes</option>
            <option value="Consulta">Consulta</option>
            <option value="Exame">Exame</option>
            <option value="Imagem">Imagem</option>
            <option value="Procedimento">Procedimento</option>
          </select>
          <div style={{ display:"flex", gap:4 }}>
            {COLUNAS.map(c=>(
              <button key={c.id} onClick={()=>setOrdenar(c.id)} style={{
                padding:"6px 14px", borderRadius:8, fontSize:11, fontWeight:700, cursor:"pointer",
                border:"1px solid "+(ordenar===c.id?"#8B1A1A":"#E5E7EB"),
                background:ordenar===c.id?"#8B1A1A":"#fff",
                color:ordenar===c.id?"#fff":"#6B7280",
              }}>{c.label}</button>
            ))}
          </div>
        </div>
      </div>

      {/* Totais do filtro */}
      {filtrados.length > 0 && (
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:16 }}>
          <div style={{ background:"#F9FAFB", borderRadius:10, padding:"10px 14px", borderLeft:"3px solid #8B1A1A" }}>
            <div style={{ fontSize:10, fontWeight:700, color:"#6B7280", textTransform:"uppercase", marginBottom:2 }}>Executado</div>
            <div style={{ fontSize:16, fontWeight:800, color:"#8B1A1A" }}>{brl(totalExec)}</div>
            <div style={{ fontSize:10, color:"#9CA3AF" }}>{filtrados.reduce((s,p)=>s+(p.total_os||0),0).toLocaleString("pt-BR")} OSs</div>
          </div>
          <div style={{ background:"#F9FAFB", borderRadius:10, padding:"10px 14px", borderLeft:"3px solid #0891B2" }}>
            <div style={{ fontSize:10, fontWeight:700, color:"#6B7280", textTransform:"uppercase", marginBottom:2 }}>Solicitado</div>
            <div style={{ fontSize:16, fontWeight:800, color:"#0891B2" }}>{brl(totalSolic)}</div>
            <div style={{ fontSize:10, color:"#9CA3AF" }}>{filtrados.reduce((s,p)=>s+(p.os_solicitadas||0),0).toLocaleString("pt-BR")} OSs</div>
          </div>
        </div>
      )}

      {loading ? (
        <div style={{ textAlign:"center", padding:32, color:"#9CA3AF" }}>Carregando...</div>
      ) : filtrados.length === 0 ? (
        <div style={{ textAlign:"center", padding:32, color:"#9CA3AF" }}>Sem dados</div>
      ) : (
        <>
          <div style={{ overflowX:"auto", WebkitOverflowScrolling:"touch" }}>
          <div style={{ minWidth:380 }}>
          <div style={{ display:"grid", gridTemplateColumns:"28px 1fr 130px 130px", gap:8, padding:"6px 10px", fontSize:10, fontWeight:700, color:"#9CA3AF", textTransform:"uppercase", borderBottom:"1px solid #F3F4F6", marginBottom:4 }}>
            <span>#</span>
            <span>Profissional</span>
            <span style={{ textAlign:"right" }}>Executado</span>
            <span style={{ textAlign:"right" }}>Solicitado</span>
            <span style={{ textAlign:"right" }}>Total Gerado</span>
          </div>

          {filtrados.map((p, i) => (
            <div key={i} style={{
              display:"grid", gridTemplateColumns:"28px 1fr 130px 130px", gap:8,
              padding:"12px 10px", alignItems:"center",
              background:i%2===0?"#FAFAFA":"#fff", borderRadius:10, marginBottom:2,
            }}>
              <span style={{ fontSize:11, fontWeight:700, color:"#D1D5DB" }}>{i+1}</span>

              <div>
                <div style={{ fontSize:13, fontWeight:700, color:"#111827", cursor:"pointer" }}
                  onClick={() => handleExpandir(p.profissional)}>
                  {expandido === p.profissional ? "▼ " : "▶ "}{p.profissional}
                </div>
                <div style={{ fontSize:10, color:"#9CA3AF", marginTop:1 }}>
                  {(p.especialidades||[]).slice(0,3).join(" · ")}
                  {(p.especialidades||[]).length > 3 ? ` +${(p.especialidades||[]).length - 3}` : ""}
                </div>
                {p.total_gerado > 0 && (
                  <div style={{ display:"flex", height:3, background:"#F3F4F6", borderRadius:2, marginTop:4, overflow:"hidden" }}>
                    <div style={{ width:((p.producao_total/p.total_gerado)*100)+"%", background:"#8B1A1A", height:"100%" }}/>
                    <div style={{ width:((p.producao_solicitada/p.total_gerado)*100)+"%", background:"#0891B2", height:"100%" }}/>
                  </div>
                )}
              </div>

              <div style={{ textAlign:"right" }}>
                <div style={{ fontSize:13, fontWeight:700, color:"#8B1A1A" }}>{brl(p.producao_total)}</div>
                <div style={{ fontSize:10, color:"#9CA3AF" }}>{num(p.total_os)} OSs · {num(p.pacientes)} pac.</div>
              </div>

              <div style={{ textAlign:"right" }}>
                <div style={{ fontSize:13, fontWeight:700, color:"#0891B2" }}>{brl(p.producao_solicitada)}</div>
                <div style={{ fontSize:10, color:"#9CA3AF" }}>{num(p.os_solicitadas)} OSs</div>
              </div>

              {expandido === p.profissional && (
                <div style={{ gridColumn:"1/-1", marginTop:8, background:"#F9FAFB", borderRadius:10, padding:"12px 14px" }}>
                  {loadDet && !detalhe[p.profissional] ? (
                    <div style={{ color:"#9CA3AF", fontSize:12 }}>Carregando...</div>
                  ) : (
                    <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))", gap:16 }}>
                      <div>
                        <div style={{ fontSize:11, fontWeight:700, color:"#8B1A1A", marginBottom:8, textTransform:"uppercase" }}>Executado</div>
                        {(detalhe[p.profissional]?.executados || []).map((s, j) => (
                          <div key={j} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", padding:"4px 0", borderBottom:"1px solid #F3F4F6" }}>
                            <div>
                              <div style={{ fontSize:12, color:"#374151" }}>{s.servico}</div>
                              <div style={{ fontSize:10, color:"#9CA3AF" }}>{s.especialidade}</div>
                            </div>
                            <div style={{ textAlign:"right" }}>
                              <div style={{ fontSize:12, fontWeight:700, color:"#8B1A1A" }}>{brl(s.valor)}</div>
                              <div style={{ fontSize:10, color:"#9CA3AF" }}>{num(s.qtd_itens)}x</div>
                            </div>
                          </div>
                        ))}
                      </div>
                      <div>
                        <div style={{ fontSize:11, fontWeight:700, color:"#0891B2", marginBottom:8, textTransform:"uppercase" }}>Solicitado</div>
                        {(detalhe[p.profissional]?.solicitados || []).map((s, j) => (
                          <div key={j} style={{ display:"flex", justifyContent:"space-between", alignItems:"center", padding:"4px 0", borderBottom:"1px solid #F3F4F6" }}>
                            <div>
                              <div style={{ fontSize:12, color:"#374151" }}>{s.servico}</div>
                              <div style={{ fontSize:10, color:"#9CA3AF" }}>{s.especialidade}</div>
                            </div>
                            <div style={{ textAlign:"right" }}>
                              <div style={{ fontSize:12, fontWeight:700, color:"#0891B2" }}>{brl(s.valor)}</div>
                              <div style={{ fontSize:10, color:"#9CA3AF" }}>{num(s.qtd_itens)}x</div>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
          </div>
          </div>
        </>
      )}
    </div>
  );
}

// ── PRODUÇÃO MENSAL ───────────────────────────────────────────────────────────
const DIAS_SEMANA = ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"];

function useMetas() {
  const [metaDiaria, setMetaDiaria] = useState(45000);
  const [metaMensal, setMetaMensal] = useState(1200000);
  const [metaSabado, setMetaSabado] = useState(45000);

  useEffect(() => {
    fetch(`${API}/api/metas`)
      .then(r => r.json())
      .then(d => {
        const m = d?.producao;
        if (m?.meta_diaria != null) setMetaDiaria(m.meta_diaria);
        if (m?.meta_mensal != null) setMetaMensal(m.meta_mensal);
        if (m?.meta_sabado != null) setMetaSabado(m.meta_sabado);
      })
      .catch(() => {});
  }, []);

  const salvar = (diaria, mensal, sabado) => {
    setMetaDiaria(Number(diaria));
    setMetaMensal(Number(mensal));
    setMetaSabado(Number(sabado));
    fetch(`${API}/api/metas/producao`, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ meta_diaria: Number(diaria), meta_mensal: Number(mensal), meta_sabado: Number(sabado) }),
    }).catch(() => {});
  };
  return { metaDiaria, metaMensal, metaSabado, salvar };
}

function PainelMetas({ metaDiaria, metaMensal, metaSabado, onSalvar }) {
  const [aberto,   setAberto]   = useState(false);
  const [tmpD, setTmpD] = useState(metaDiaria);
  const [tmpM, setTmpM] = useState(metaMensal);
  const [tmpS, setTmpS] = useState(metaSabado);

  const inputStyle = {
    padding:"7px 10px", borderRadius:8, border:`1px solid ${"#EAEDF2"}`,
    background:"#EEEEEE", color:"#111827", fontSize:13, fontWeight:700,
    outline:"none", width:160, textAlign:"right",
  };
  const labelStyle = { fontSize:11, color:"#6B7280", fontWeight:700, textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:4, display:"block" };

  return (
    <div style={{ position:"relative" }}>
      <button onClick={() => { setTmpD(metaDiaria); setTmpM(metaMensal); setTmpS(metaSabado); setAberto(v=>!v); }} style={{
        padding:"6px 14px", borderRadius:8, border:`1px solid ${"#EAEDF2"}`,
        background: aberto ? "#F59E0B" : "#fff",
        color: aberto ? "#0F172A" : "#6B7280",
        fontSize:12, fontWeight:700, cursor:"pointer", transition:"all 0.15s",
        display:"flex", alignItems:"center", gap:6,
      }}>
        ⚙ Metas
      </button>

      {aberto && (
        <div style={{
          position:"absolute", top:"calc(100% + 8px)", right:0, zIndex:200,
          background:"#fff", border:`1px solid ${"#EAEDF2"}`, borderRadius:14,
          padding:20, minWidth:280, boxShadow:"0 12px 40px rgba(0,0,0,0.6)",
        }}>
          <div style={{ fontSize:13, fontWeight:800, color:"#111827", marginBottom:16 }}>Configurar Metas</div>

          <div style={{ marginBottom:14 }}>
            <label style={labelStyle}>Meta Diária (R$)</label>
            <input type="number" value={tmpD}
              onChange={e => setTmpD(Number(e.target.value))}
              style={inputStyle} step={1000} min={0} />
            <div style={{ fontSize:10, color:"#6B7280", marginTop:4 }}>
              Usado para indicar dias abaixo/acima da meta
            </div>
          </div>

          <div style={{ marginBottom:14 }}>
            <label style={labelStyle}>Meta Sábado (R$)</label>
            <input type="number" value={tmpS}
              onChange={e => setTmpS(Number(e.target.value))}
              style={inputStyle} step={1000} min={0} />
            <div style={{ fontSize:10, color:"#6B7280", marginTop:4 }}>
              Meta diária específica para sábados
            </div>
          </div>

          <div style={{ marginBottom:20 }}>
            <label style={labelStyle}>Meta Mensal (R$)</label>
            <input type="number" value={tmpM}
              onChange={e => setTmpM(Number(e.target.value))}
              style={inputStyle} step={10000} min={0} />
            <div style={{ fontSize:10, color:"#6B7280", marginTop:4 }}>
              Meta fixa do mês (ignora dias úteis × diária)
            </div>
          </div>

          <div style={{ display:"flex", gap:8 }}>
            <button onClick={() => { onSalvar(tmpD, tmpM, tmpS); setAberto(false); }} style={{
              flex:1, padding:"8px", borderRadius:8, border:"none", cursor:"pointer",
              background:"#10B981", color:"#0F172A", fontSize:12, fontWeight:800,
            }}>Salvar</button>
            <button onClick={() => setAberto(false)} style={{
              flex:1, padding:"8px", borderRadius:8, border:`1px solid ${"#EAEDF2"}`,
              background:"transparent", color:"#6B7280", fontSize:12, fontWeight:700, cursor:"pointer",
            }}>Cancelar</button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── OCUPACIONAL vs ASSISTENCIAL — quando uma ultrapassou a outra ────────────
function GraficoOcupVsAssist() {
  const [meses, setMeses] = useState(24);
  const { data, loading } = useFetch("/api/financeiro/ocupacional-vs-assistencial", { meses });
  const MESES_ABREV = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
  const brlFull = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v) : "—";
  const brlK = v => v != null ? `R$${(v/1000).toFixed(0)}k` : "—";

  const chartData = (data||[]).map(r => ({
    label: `${MESES_ABREV[r.mes-1]}/${String(r.ano).slice(2)}`,
    ocupacional: r.ocupacional,
    assistencial: r.assistencial,
  }));

  // Detecta o(s) mês(es) em que a liderança trocou de lado
  const cruzamentos = [];
  for (let i = 1; i < chartData.length; i++) {
    const antes = chartData[i-1].assistencial - chartData[i-1].ocupacional;
    const agora = chartData[i].assistencial - chartData[i].ocupacional;
    if (antes !== 0 && agora !== 0 && Math.sign(antes) !== Math.sign(agora)) {
      cruzamentos.push({
        label: chartData[i].label,
        quem: agora > 0 ? "Assistencial" : "Ocupacional",
      });
    }
  }
  const ultimoCruzamento = cruzamentos[cruzamentos.length - 1];

  return (
    <Card title="Ocupacional vs. Assistencial" subtitle="Produção mensal lado a lado — identifica quando uma ultrapassou a outra"
      style={{ marginBottom:16 }}
      action={
        <div style={{ display:"flex", gap:4 }}>
          {[12,24,36].map(n => (
            <button key={n} onClick={()=>setMeses(n)} style={{
              padding:"4px 10px", borderRadius:6, fontSize:12, fontWeight:700, cursor:"pointer",
              border:`1px solid ${meses===n?"#8B1A1A":"#E5E7EB"}`,
              background:meses===n?"#FDF2F2":"#fff",
              color:meses===n?"#8B1A1A":"#6B7280",
            }}>{n}m</button>
          ))}
        </div>
      }>
      {loading ? <Skeleton h={260}/> : (
        <div>
          {ultimoCruzamento && (
            <div style={{ background:"#FFFBEB", border:"1px solid #FDE68A", borderRadius:10, padding:"8px 14px", marginBottom:12, fontSize:12, color:"#92400E" }}>
              🔄 Última virada: <strong>{ultimoCruzamento.quem}</strong> passou a liderar em <strong>{ultimoCruzamento.label}</strong>
              {cruzamentos.length > 1 && ` (${cruzamentos.length} viradas no período exibido)`}
            </div>
          )}
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={chartData} margin={{top:4,right:16,bottom:0,left:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false}/>
              <XAxis dataKey="label" tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} interval="preserveStartEnd"/>
              <YAxis tickFormatter={brlK} tick={{fontSize:11,fill:"#9CA3AF"}} axisLine={false} tickLine={false} width={52}/>
              <Tooltip formatter={(v,name)=>[brlFull(v), name]}
                contentStyle={{ background:"#fff", border:"1px solid #E5E7EB", borderRadius:10,
                  boxShadow:"0 4px 16px rgba(0,0,0,0.12)", fontSize:12 }}/>
              <Legend iconSize={10} wrapperStyle={{fontSize:12,paddingTop:8}}/>
              {cruzamentos.map((c,i) => (
                <ReferenceLine key={i} x={c.label} stroke="#D97706" strokeDasharray="4 4" strokeWidth={1.5}/>
              ))}
              <Line type="monotone" dataKey="ocupacional"  name="Ocupacional"  stroke="#8B5CF6" strokeWidth={2.5} dot={{r:2}} activeDot={{r:5}}/>
              <Line type="monotone" dataKey="assistencial" name="Assistencial" stroke="#8B1A1A" strokeWidth={2.5} dot={{r:2}} activeDot={{r:5}}/>
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

// ── COMPARATIVO FATURAMENTO ANUAL ────────────────────────────────────────────
function GraficoProducaoAnual() {
  const [anos, setAnos] = useState(3);
  const { data, loading } = useFetch("/api/financeiro/faturamento-anual", { anos });
  const brl = v => v != null ? `R$${(v/1000).toFixed(0)}k` : "—";
  const brlFull = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v) : "—";
  const MESES = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
  const CORES_ANOS = ["#8B1A1A","#F59E0B","#10B981","#8B5CF6","#EF4444"];

  // Montar dados para recharts: [{mes:"Jan", 2026:xxx, 2025:xxx, ...}]
  const chartData = MESES.map((m, idx) => {
    const obj = { mes: m };
    Object.entries(data||{}).forEach(([ano, meses]) => {
      const v = meses[idx]?.valor;
      if (v != null) obj[ano] = v;
    });
    return obj;
  });

  const anosDisp = Object.keys(data||{}).sort((a,b)=>b-a);

  return (
    <Card title="Produção Mensal — Comparativo Anual"
      subtitle="Evolução mês a mês comparada com anos anteriores"
      style={{ marginBottom:16 }}
      action={
        <div style={{ display:"flex", gap:4 }}>
          {[2,3,4,5].map(n => (
            <button key={n} onClick={()=>setAnos(n)} style={{
              padding:"4px 10px", borderRadius:6, fontSize:12, fontWeight:700, cursor:"pointer",
              border:`1px solid ${anos===n?"#8B1A1A":"#E5E7EB"}`,
              background:anos===n?"#FDF2F2":"#fff",
              color:anos===n?"#8B1A1A":"#6B7280",
            }}>{n}a</button>
          ))}
        </div>
      }>
      {loading ? <Skeleton h={260}/> : (
        <div>
          {/* Legenda */}
          <div style={{ display:"flex", gap:16, marginBottom:12 }}>
            {anosDisp.map((ano,i) => {
              const total = (data[ano]||[]).reduce((s,m)=>s+(m.valor||0),0);
              return (
                <div key={ano} style={{ display:"flex", alignItems:"center", gap:6 }}>
                  <div style={{ width:12, height:12, borderRadius:3, background:CORES_ANOS[i%CORES_ANOS.length] }}/>
                  <span style={{ fontSize:12, fontWeight:700, color:"#111827" }}>{ano}</span>
                  <span style={{ fontSize:11, color:"#6B7280" }}>{brlFull(total)}</span>
                </div>
              );
            })}
          </div>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={chartData} margin={{top:4,right:16,bottom:0,left:0}}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false}/>
              <XAxis dataKey="mes" tick={{fontSize:11,fill:"#9CA3AF"}} axisLine={false} tickLine={false}/>
              <YAxis tickFormatter={brl} tick={{fontSize:11,fill:"#9CA3AF"}} axisLine={false} tickLine={false} width={52}/>
              <Tooltip
                formatter={(v,name)=>[brlFull(v), name]}
                contentStyle={{ background:"#fff", border:"1px solid #E5E7EB", borderRadius:10,
                  boxShadow:"0 4px 16px rgba(0,0,0,0.12)", fontSize:12 }}/>
              <Legend iconSize={10} wrapperStyle={{fontSize:12,paddingTop:8}}/>
              {anosDisp.map((ano,i) => (
                <Line key={ano} type="monotone" dataKey={ano}
                  stroke={CORES_ANOS[i%CORES_ANOS.length]}
                  strokeWidth={i===0?3:2}
                  strokeDasharray={i===0?"none":"6 3"}
                  dot={{r:i===0?4:3, fill:CORES_ANOS[i%CORES_ANOS.length], strokeWidth:0}}
                  connectNulls={false}/>
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}


// ── PRODUÇÃO MENSAL ───────────────────────────────────────────────────────────

function SecaoProducaoMensal({ modulo, periodoEfetivo }) {
  const hoje     = new Date();
  const hojeStr  = `${hoje.getFullYear()}-${String(hoje.getMonth()+1).padStart(2,"0")}-${String(hoje.getDate()).padStart(2,"0")}`;
  const [ano,    setAno]    = useState(hoje.getFullYear());
  const [mes,    setMes]    = useState(hoje.getMonth() + 1);
  const [hover,  setHover]  = useState(null); // { data, x, y }
  const { metaDiaria, metaMensal, metaSabado, salvar } = useMetas();
  const { data, loading } = useFetch("/api/financeiro/producao-mensal", {
    ano, mes, meta_diaria: metaDiaria, meta_mensal_fixa: metaMensal, meta_sabado: metaSabado,
  });

  // Sábados têm meta própria (metaSabado) — todos os outros dias usam metaDiaria.
  const ehSabado = (dataStr) => !!dataStr && new Date(dataStr + "T12:00:00").getDay() === 6;
  const metaDoDia = (dataStr) => ehSabado(dataStr) ? metaSabado : metaDiaria;
  // Meta média de uma semana, ponderada pelos dias com produção nela (mistura dias úteis e sábado)
  const metaSemanaCalc = (diasV) => diasV.length ? diasV.reduce((s,d)=>s+metaDoDia(d.data),0)/diasV.length : metaDiaria;

  const fmt = (v) => v != null
    ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",minimumFractionDigits:2}).format(v) : "—";

  // Semanas Seg–Sáb
  const semanas = (() => {
    if (!data?.dias) return [];
    const mapa = {};
    data.dias.forEach(d => { mapa[d.data] = d; });
    const ultimoDia = new Date(ano, mes, 0).getDate();
    const semanas = [];
    let semana = new Array(6).fill(null);
    for (let d = 1; d <= ultimoDia; d++) {
      const date   = new Date(ano, mes - 1, d);
      const jsDay  = date.getDay();
      if (jsDay === 0) continue;
      const col    = jsDay - 1;
      const ds     = `${ano}-${String(mes).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
      semana[col]  = { dia: d, data: ds, ...(mapa[ds] || {}) };
      if (jsDay === 6 || d === ultimoDia) { semanas.push([...semana]); semana = new Array(6).fill(null); }
    }
    return semanas;
  })();

  const pctMes = data ? Math.min(100, (data.total_geral / metaMensal) * 100) : 0;
  const projecao = data ? data.total_geral + (data.media_diaria * (data.dias_restantes||0)) : 0;
  const falta    = data ? metaMensal - data.total_geral : 0;
  const necessario = data?.dias_restantes > 0 ? falta / data.dias_restantes : 0;

  // Meta média do mês, ponderada por quantos dias úteis vs sábados existem (Seg–Sáb, sem domingo)
  const metaMediaMensal = (() => {
    const ultimoDia = new Date(ano, mes, 0).getDate();
    let uteis = 0, sabados = 0;
    for (let d = 1; d <= ultimoDia; d++) {
      const dow = new Date(ano, mes - 1, d).getDay();
      if (dow === 0) continue;
      if (dow === 6) sabados++; else uteis++;
    }
    const total = uteis + sabados;
    return total > 0 ? (uteis*metaDiaria + sabados*metaSabado) / total : metaDiaria;
  })();

  const DIAS_NOME = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado"];

  // Cor da célula baseada na performance vs meta (sábado usa metaSabado)
  const corCelula = (cel) => {
    if (!cel?.total) return null;
    const pct = cel.total / metaDoDia(cel.data);
    if (pct >= 1)    return { bg:"#F0FDF4", border:"#BBF7D0", dot:"#10B981" };
    if (pct >= 0.8)  return { bg:"#FFFBEB", border:"#FDE68A", dot:"#F59E0B" };
    return             { bg:"#FFF1F2", border:"#FECDD3", dot:"#F43F5E" };
  };

  const brlFmt = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v) : "n/d";

  // Anel SVG de progresso da meta
  const ringPct = Math.min(100, pctMes);
  const ringR = 54, ringC = 68, ringCirc = 2 * Math.PI * ringR;
  const ringStroke = ringCirc * (1 - ringPct / 100);
  const ringCor = ringPct >= 100 ? "#10B981" : ringPct >= 60 ? "#0891B2" : ringPct >= 30 ? "#F59E0B" : "#EF4444";

  return (
    <div style={{ position:"relative", animation:"fadeIn 0.35s ease" }}>

      {/* Hero da Produção Mensal com anel de progresso */}
      <div style={{
        background:"linear-gradient(135deg, #0891B2 0%, #0369A1 100%)",
        borderRadius:20, padding:"28px 32px", marginBottom:20,
        boxShadow:"0 8px 32px #0891B240",
        display:"flex", alignItems:"center", gap:32, flexWrap:"wrap",
        position:"relative", overflow:"hidden",
      }}>
        <div style={{ position:"absolute", right:-20, top:-20, width:180, height:180, borderRadius:"50%", background:"rgba(255,255,255,0.07)" }}/>
        <div style={{ position:"absolute", right:80, bottom:-60, width:140, height:140, borderRadius:"50%", background:"rgba(255,255,255,0.05)" }}/>

        {/* Anel de progresso */}
        <div style={{ flexShrink:0, position:"relative" }}>
          <svg width={ringC*2} height={ringC*2}>
            <circle cx={ringC} cy={ringC} r={ringR} fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth={10}/>
            <circle cx={ringC} cy={ringC} r={ringR} fill="none"
              stroke={ringCor} strokeWidth={10}
              strokeDasharray={ringCirc}
              strokeDashoffset={ringStroke}
              strokeLinecap="round"
              transform={`rotate(-90 ${ringC} ${ringC})`}
              style={{ transition:"stroke-dashoffset 1s ease, stroke 0.5s" }}
            />
            <text x={ringC} y={ringC-6} textAnchor="middle" fill="#fff" fontSize={18} fontWeight={900}>{ringPct.toFixed(0)}%</text>
            <text x={ringC} y={ringC+14} textAnchor="middle" fill="rgba(255,255,255,0.7)" fontSize={10} fontWeight={600}>da meta</text>
          </svg>
        </div>

        {/* Info principal */}
        <div style={{ flex:1, minWidth:200 }}>
          <div style={{ fontSize:20, fontWeight:900, color:"#fff", marginBottom:4 }}>Produção Mensal</div>
          <div style={{ fontSize:13, color:"rgba(255,255,255,0.7)", marginBottom:20 }}>{MESES_PT[mes-1]} de {ano}</div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(140px,1fr))", gap:12 }}>
            {[
              { l:"Realizado",   v:brlFmt(data?.total_geral),   s:null },
              { l:"Meta Mensal", v:brlFmt(metaMensal),           s:null },
              { l:"Projeção",    v:brlFmt(projecao),             s: projecao >= metaMensal ? "✓ atingirá" : "⚠ abaixo" },
              { l:"Falta",       v:brlFmt(Math.max(0,falta)),    s:`${data?.dias_restantes ?? "—"} dias úteis` },
            ].map((k,i) => (
              <div key={i} style={{ background:"rgba(255,255,255,0.12)", borderRadius:10, padding:"10px 14px", backdropFilter:"blur(4px)" }}>
                <div style={{ fontSize:9, color:"rgba(255,255,255,0.7)", fontWeight:800, textTransform:"uppercase", letterSpacing:"0.08em", marginBottom:3 }}>{k.l}</div>
                <div style={{ fontSize:16, fontWeight:900, color:"#fff" }}>{loading ? "…" : k.v}</div>
                {k.s && <div style={{ fontSize:10, color:"rgba(255,255,255,0.65)", marginTop:2 }}>{k.s}</div>}
              </div>
            ))}
          </div>
        </div>
      </div>

      <BriefingCard
        cor="#0891B2"
        cacheKey={`briefing_producao_${ano}_${mes}`}
        disabled={loading}
        promptFn={() => {
          const diasUteis    = data?.dias_uteis_mes ?? 0;
          const diasPassados = diasUteis - (data?.dias_restantes ?? 0);
          const esperado     = diasUteis > 0 ? metaMensal * (diasPassados / diasUteis) : 0;
          const status       = data?.total_geral >= esperado ? "DENTRO DO ESPERADO" : "ABAIXO DO ESPERADO";
          return `Você é um analista de gestão clínica. Gere um briefing executivo em no máximo 4 frases, direto e profissional, sem markdown. IMPORTANTE: considere sempre o dia atual do mês ao avaliar o desempenho — estar com baixo percentual nos primeiros dias é normal se o ritmo diário estiver adequado.

DADOS — Produção Mensal (${MESES_PT[mes-1]} ${ano}):
- Hoje é o dia ${new Date().getDate()} de ${MESES_PT[mes-1]} (${diasPassados} dias úteis transcorridos de ${diasUteis} no mês)
- Total produzido até agora: ${brlFmt(data?.total_geral)}
- Produção esperada para este ponto do mês: ${brlFmt(esperado)}
- Status em relação ao ritmo esperado: ${status}
- Meta mensal total: ${brlFmt(metaMensal)}
- Percentual da meta atingido: ${data ? Math.min(100,(data.total_geral/metaMensal)*100).toFixed(1) : "n/d"}%
- Média diária realizada: ${brlFmt(data?.media_diaria)}
- Projeção para fim do mês (ritmo atual): ${brlFmt(projecao)}
- Dias úteis restantes: ${data?.dias_restantes ?? "n/d"}
- Necessário por dia para bater a meta: ${brlFmt(necessario > 0 ? necessario : null)}

Avalie se o ritmo diário está adequado em relação ao ponto do mês, não apenas o percentual acumulado.`;
        }}
      />

      {/* ── HEADER CONTROLS ── */}
      <div style={{ display:"flex", alignItems:"center", gap:12, marginBottom:24, flexWrap:"wrap" }}>
        <div style={{ display:"flex", alignItems:"center", gap:8 }}>
          <select value={mes} onChange={e=>setMes(Number(e.target.value))} style={{
            padding:"7px 12px", borderRadius:8, border:`1px solid ${C.border}`,
            background:"#fff", color:C.text, fontSize:13, fontWeight:600, cursor:"pointer", outline:"none",
          }}>
            {MESES_PT.map((m,i) => <option key={i+1} value={i+1}>{m}</option>)}
          </select>
          <select value={ano} onChange={e=>setAno(Number(e.target.value))} style={{
            padding:"7px 12px", borderRadius:8, border:`1px solid ${C.border}`,
            background:"#fff", color:C.text, fontSize:13, fontWeight:600, cursor:"pointer", outline:"none",
          }}>
            {[hoje.getFullYear()-2, hoje.getFullYear()-1, hoje.getFullYear()].map(a=>(
              <option key={a} value={a}>{a}</option>
            ))}
          </select>
          <PainelMetas metaDiaria={metaDiaria} metaMensal={metaMensal} metaSabado={metaSabado} onSalvar={salvar} />
          
        </div>

        {/* Legenda */}
        <div style={{ display:"flex", gap:12, marginLeft:"auto", alignItems:"center" }}>
          {[
            { dot:"#10B981", label:"Acima da meta" },
            { dot:"#F59E0B", label:"80–100%" },
            { dot:"#F43F5E", label:"Abaixo de 80%" },
            { dot:"#94A3B8", label:"Sem produção" },
          ].map((l,i) => (
            <div key={i} style={{ display:"flex", alignItems:"center", gap:5, fontSize:12, color:C.sub }}>
              <span style={{ width:10, height:10, borderRadius:"50%", background:l.dot, display:"inline-block", flexShrink:0 }}/>
              {l.label}
            </div>
          ))}
        </div>
      </div>

      {/* ── KPIs ── */}
      {data && !loading && (
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(170px,1fr))", gap:12, marginBottom:20 }}>
          {[
            { label:"Ocupacional",   val:data.total_ocupacional,  color:"#8B5CF6", sub:null },
            { label:"Assistencial",  val:data.total_assistencial, color:"#8B1A1A", sub:null },
            { label:"Total Geral",   val:data.total_geral,        color:"#10B981", sub:`${data.dias_com_producao} dias com produção` },
            { label:"Média Diária",  val:data.media_diaria,       color: data.media_diaria>=metaMediaMensal?"#10B981":"#F59E0B",
              sub: data.media_diaria>=metaMediaMensal ? "↑ acima da meta" : `↓ meta ${fmt(metaMediaMensal)}/dia` },
            { label:"Projeção",      val:projecao,                color: projecao>=metaMensal?"#10B981":"#F59E0B",
              sub:`${Math.round(data.dias_restantes||0)} dias restantes` },
            { label: falta<=0?"Meta Atingida ✓":"Necessário/Dia",
              val: falta<=0 ? Math.abs(falta) : necessario,
              color: falta<=0 ? "#10B981" : necessario<=metaMediaMensal*1.3 ? "#F59E0B" : "#EF4444",
              sub: falta<=0 ? `Superou em ${fmt(Math.abs(falta))}` : `faltam ${fmt(falta)}` },
          ].map((k,i) => (
            <div key={i} style={{ background:"#fff", borderRadius:12, padding:"16px 18px", borderTop:`3px solid ${k.color}`, boxShadow:"0 1px 3px rgba(0,0,0,0.05)" }}>
              <div style={{ fontSize:10, color:C.faint, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:6 }}>{k.label}</div>
              <div style={{ fontSize:17, fontWeight:800, color:k.color, lineHeight:1.1 }}>{fmt(k.val)}</div>
              {k.sub && <div style={{ fontSize:11, color:C.sub, marginTop:4 }}>{k.sub}</div>}
            </div>
          ))}
        </div>
      )}

      {/* ── BARRA DE PROGRESSO ── */}
      {data && (
        <div style={{ background:"#fff", borderRadius:12, padding:"16px 20px", marginBottom:20, boxShadow:"0 1px 3px rgba(0,0,0,0.05)" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:10 }}>
            <span style={{ fontSize:13, fontWeight:700, color:C.text }}>
              Progresso da Meta — <span style={{ color: pctMes>=100?"#10B981":pctMes>=70?"#F59E0B":"#8B1A1A" }}>{pctMes.toFixed(1)}%</span>
            </span>
            <span style={{ fontSize:12, color:C.sub }}>
              {fmt(data.total_geral)} de {fmt(metaMensal)} · {Math.round(data.dias_uteis_mes)} dias úteis
            </span>
          </div>
          <div style={{ height:10, background:"#EEEEEE", borderRadius:6, overflow:"hidden" }}>
            <div style={{ height:"100%", borderRadius:6, width:`${pctMes}%`, transition:"width 1s ease",
              background: pctMes>=100?"#10B981":pctMes>=70?"#F59E0B":"#8B1A1A" }} />
          </div>
          <div style={{ display:"flex", justifyContent:"space-between", marginTop:8 }}>
            {[0,25,50,75,100].map(p => (
              <span key={p} style={{ fontSize:10, color:C.faint }}>{p}%</span>
            ))}
          </div>
        </div>
      )}

      {/* ── CALENDÁRIO DE PRODUÇÃO ── */}
      {loading ? <Skeleton h={420}/> : (
        <div style={{ overflowX:"auto", WebkitOverflowScrolling:"touch", marginBottom:20 }}>
        <div style={{ background:"#fff", borderRadius:14, overflow:"hidden", boxShadow:"0 1px 3px rgba(0,0,0,0.05)", minWidth:560 }}>

          {/* Header dias da semana */}
          <div style={{ display:"grid", gridTemplateColumns:"60px repeat(6,1fr) 140px 120px", background:"#F2F2F2", borderBottom:`1px solid ${C.border}` }}>
            <div style={{ padding:"10px 12px", fontSize:11, fontWeight:700, color:C.faint, textTransform:"uppercase" }}>Sem.</div>
            {DIAS_NOME.map(d => (
              <div key={d} style={{ padding:"10px 8px", fontSize:11, fontWeight:700, color:C.sub, textTransform:"uppercase", textAlign:"center" }}>{d}</div>
            ))}
            <div style={{ padding:"10px 8px", fontSize:11, fontWeight:700, color:C.blue, textAlign:"right", textTransform:"uppercase" }}>Total Semana</div>
            <div style={{ padding:"10px 8px", fontSize:11, fontWeight:700, color:C.amber, textAlign:"right", textTransform:"uppercase" }}>Média/Dia</div>
          </div>

          {/* Semanas */}
          {semanas.map((semana, si) => {
            const diasV   = semana.filter(d => d?.total > 0);
            const totSem  = diasV.reduce((s,d) => s+(d.total||0),0);
            const totOcup = diasV.reduce((s,d) => s+(d.ocupacional||0),0);
            const totAss  = diasV.reduce((s,d) => s+(d.assistencial||0),0);
            const media   = diasV.length > 0 ? totSem/diasV.length : 0;
            const metaSem  = metaSemanaCalc(diasV);
            const corMedia = media===0?C.faint:media>=metaSem?"#10B981":"#EF4444";

            return (
              <div key={si} style={{ display:"grid", gridTemplateColumns:"60px repeat(6,1fr) 140px 120px", borderBottom:`1px solid ${C.border}` }}>

                {/* Label semana */}
                <div style={{ padding:"8px 12px", display:"flex", alignItems:"center", justifyContent:"center",
                  background:"#FFFFFF", borderRight:`1px solid ${C.border}` }}>
                  <span style={{ fontSize:11, fontWeight:700, color:C.faint }}>{si+1}ª</span>
                </div>

                {/* Células de dia */}
                {semana.map((cel, ci) => {
                  const c     = corCelula(cel);
                  const isH   = cel?.data === hojeStr;
                  const isFut = cel?.data > hojeStr;

                  return (
                    <div key={ci}
                      onMouseEnter={e => cel?.dia && setHover({ cel, rect: e.currentTarget.getBoundingClientRect() })}
                      onMouseLeave={() => setHover(null)}
                      style={{
                        padding:"10px 10px", minHeight:72, borderRight:`1px solid ${C.border}`,
                        background: isH ? "#FDF2F2" : c ? c.bg : isFut ? "#FAFAFA" : "#fff",
                        border: isH ? "2px solid #8B1A1A" : `1px solid ${c ? c.border : C.border}`,
                        cursor: cel?.dia ? "pointer" : "default",
                        transition:"all 0.1s", position:"relative",
                        boxSizing:"border-box",
                      }}>
                      {cel?.dia && (
                        <>
                          {/* Dia + badge hoje */}
                          <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:6 }}>
                            <span style={{ fontSize:13, fontWeight:700, color: isH ? "#8B1A1A" : c ? C.text : C.faint }}>
                              {cel.dia}
                            </span>
                            {isH && <span style={{ fontSize:9, fontWeight:700, color:"#8B1A1A", background:"#F5E0E0", borderRadius:4, padding:"1px 5px" }}>HOJE</span>}
                            {c && <span style={{ width:8, height:8, borderRadius:"50%", background:c.dot, flexShrink:0 }}/>}
                          </div>

                          {/* Valores */}
                          {cel.total > 0 ? (
                            <div style={{ display:"flex", flexDirection:"column", gap:2 }}>
                              <div style={{ fontSize:12, fontWeight:800, color:C.text, lineHeight:1 }}>
                                {fmt(cel.total)}
                              </div>
                              <div style={{ fontSize:10, color:"#8B5CF6" }}>
                                Ocup: {fmt(cel.ocupacional||0)}
                              </div>
                              <div style={{ fontSize:10, color:"#8B1A1A" }}>
                                Ass: {fmt(cel.assistencial||0)}
                              </div>
                            </div>
                          ) : !isFut ? (
                            <div style={{ fontSize:11, color:C.faint }}>Sem prod.</div>
                          ) : (
                            <div style={{ fontSize:11, color:"#CBD5E1" }}>—</div>
                          )}

                          {/* Barra de % meta */}
                          {cel.total > 0 && (
                            <div style={{ position:"absolute", bottom:0, left:0, right:0, height:3, background:"#EEEEEE" }}>
                              <div style={{
                                height:"100%",
                                width:`${Math.min(100,(cel.total/metaDoDia(cel.data))*100)}%`,
                                background: c?.dot,
                                borderRadius:"0 2px 2px 0",
                              }}/>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  );
                })}

                {/* Total semana */}
                <div style={{ padding:"10px 12px", display:"flex", flexDirection:"column", justifyContent:"center", alignItems:"flex-end", background:"#F2F2F2", borderLeft:`1px solid ${C.border}` }}>
                  {diasV.length > 0 ? (
                    <>
                      <div style={{ fontSize:13, fontWeight:800, color:C.blue }}>{fmt(totSem)}</div>
                      <div style={{ fontSize:10, color:"#8B5CF6", marginTop:2 }}>Oc: {fmt(totOcup)}</div>
                      <div style={{ fontSize:10, color:C.blue }}>As: {fmt(totAss)}</div>
                    </>
                  ) : <span style={{ color:C.faint, fontSize:12 }}>—</span>}
                </div>

                {/* Média/dia */}
                <div style={{ padding:"10px 12px", display:"flex", flexDirection:"column", justifyContent:"center", alignItems:"flex-end", background:"#FAFAFA" }}>
                  {media > 0 ? (
                    <>
                      <div style={{ fontSize:13, fontWeight:800, color:corMedia }}>{fmt(media)}</div>
                      <div style={{ fontSize:10, color:C.faint, marginTop:2 }}>
                        {media >= metaSem ? "↑ acima" : `↓ ${((media/metaSem)*100).toFixed(0)}% da meta`}
                      </div>
                    </>
                  ) : <span style={{ color:C.faint, fontSize:12 }}>—</span>}
                </div>
              </div>
            );
          })}

          {/* Footer totais */}
          {data && (
            <div style={{ display:"grid", gridTemplateColumns:"60px repeat(6,1fr) 140px 120px", background:"#FDF2F2", borderTop:`2px solid ${C.blue}` }}>
              <div style={{ padding:"12px", display:"flex", alignItems:"center", justifyContent:"center", borderRight:`1px solid ${C.border}` }}>
                <span style={{ fontSize:10, fontWeight:800, color:C.blue, textTransform:"uppercase" }}>Total</span>
              </div>
              {[0,1,2,3,4,5].map(i => <div key={i} style={{ borderRight:`1px solid ${C.border}` }}/>)}
              <div style={{ padding:"12px", textAlign:"right", borderLeft:`1px solid ${C.border}` }}>
                <div style={{ fontSize:14, fontWeight:800, color:"#10B981" }}>{fmt(data.total_geral)}</div>
                <div style={{ fontSize:10, color:"#8B5CF6" }}>Oc: {fmt(data.total_ocupacional)}</div>
                <div style={{ fontSize:10, color:C.blue }}>As: {fmt(data.total_assistencial)}</div>
              </div>
              <div style={{ padding:"12px", textAlign:"right" }}>
                <div style={{ fontSize:14, fontWeight:800, color: data.media_diaria>=metaMediaMensal?"#10B981":"#EF4444" }}>{fmt(data.media_diaria)}</div>
                <div style={{ fontSize:10, color:C.faint }}>meta: {fmt(metaMediaMensal)}</div>
              </div>
            </div>
          )}
        </div>
        </div>
      )}

      {/* ── TOOLTIP HOVER ── */}
      {hover?.cel?.total > 0 && (() => {
        const cel  = hover.cel;
        const r    = hover.rect;
        const metaC = metaDoDia(cel.data);
        const pctD = Math.min(100, ((cel.total||0)/metaC)*100).toFixed(1);
        const corD = cel.total >= metaC ? "#10B981" : cel.total >= metaC*0.8 ? "#F59E0B" : "#F43F5E";
        return (
          <div style={{
            position:"fixed",
            top: r.bottom + 8, left: Math.min(r.left, window.innerWidth - 240),
            zIndex:9999, background:"#fff", borderRadius:12,
            boxShadow:"0 8px 32px rgba(0,0,0,0.15), 0 0 0 1px rgba(0,0,0,0.06)",
            padding:"14px 16px", minWidth:200, pointerEvents:"none",
          }}>
            <div style={{ fontSize:13, fontWeight:800, color:C.text, marginBottom:10 }}>
              {cel.dia} de {MESES_PT[mes-1]} — {new Date(cel.data+"T12:00").toLocaleDateString("pt-BR",{weekday:"long"})}
            </div>
            <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
              <div style={{ display:"flex", justifyContent:"space-between", gap:16 }}>
                <span style={{ fontSize:12, color:C.sub }}>Total do dia</span>
                <span style={{ fontSize:12, fontWeight:800, color:corD }}>{fmt(cel.total)}</span>
              </div>
              <div style={{ display:"flex", justifyContent:"space-between" }}>
                <span style={{ fontSize:12, color:"#8B5CF6" }}>Ocupacional</span>
                <span style={{ fontSize:12, fontWeight:700, color:"#8B5CF6" }}>{fmt(cel.ocupacional||0)}</span>
              </div>
              <div style={{ display:"flex", justifyContent:"space-between" }}>
                <span style={{ fontSize:12, color:C.blue }}>Assistencial</span>
                <span style={{ fontSize:12, fontWeight:700, color:C.blue }}>{fmt(cel.assistencial||0)}</span>
              </div>
              <div style={{ height:1, background:C.border, margin:"4px 0" }}/>
              <div style={{ display:"flex", justifyContent:"space-between" }}>
                <span style={{ fontSize:12, color:C.sub }}>Meta do dia{ehSabado(cel.data) ? " (sábado)" : ""}</span>
                <span style={{ fontSize:12, fontWeight:700, color:C.sub }}>{fmt(metaC)}</span>
              </div>
              {/* Barra de progresso */}
              <div>
                <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3 }}>
                  <span style={{ fontSize:11, color:C.faint }}>Performance</span>
                  <span style={{ fontSize:11, fontWeight:700, color:corD }}>{pctD}%</span>
                </div>
                <div style={{ height:6, background:"#EEEEEE", borderRadius:4, overflow:"hidden" }}>
                  <div style={{ height:"100%", width:`${pctD}%`, background:corD, borderRadius:4 }}/>
                </div>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── OCUPACIONAL vs ASSISTENCIAL ── */}
      <GraficoOcupVsAssist/>

      {/* ── COMPARATIVO ANUAL ── */}
      <GraficoProducaoAnual/>

      {/* ── TABELA SEMANAL ── */}
      {data && !loading && (
        <div style={{ background:"#fff", borderRadius:14, overflow:"hidden", boxShadow:"0 1px 3px rgba(0,0,0,0.05)" }}>
          <div style={{ padding:"16px 20px 12px", borderBottom:`1px solid ${C.border}` }}>
            <div style={{ fontSize:14, fontWeight:700, color:C.text }}>Resumo Semanal</div>
            <div style={{ fontSize:12, color:C.faint, marginTop:2 }}>Totais e projeções por semana</div>
          </div>
          <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
            <thead>
              <tr style={{ background:"#F2F2F2" }}>
                {["Semana","Dias","Ocupacional","Assistencial","Total","Média/Dia","vs Meta","Status"].map(h=>(
                  <th key={h} style={{ padding:"10px 14px", fontSize:11, fontWeight:700, color:C.faint, textAlign:h==="Semana"?"left":"right", textTransform:"uppercase", letterSpacing:"0.05em" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {semanas.map((semana,si) => {
                const diasV  = semana.filter(d => d?.total>0);
                const totSem = diasV.reduce((s,d)=>s+(d.total||0),0);
                const totOc  = diasV.reduce((s,d)=>s+(d.ocupacional||0),0);
                const totAs  = diasV.reduce((s,d)=>s+(d.assistencial||0),0);
                const media  = diasV.length>0 ? totSem/diasV.length : 0;
                const metaSem = metaSemanaCalc(diasV);
                const vsMeta = media - metaSem;
                const diasFut= semana.filter(d=>d?.data>hojeStr&&d?.dia).length;
                const proj   = totSem + (media>0?media*diasFut:0);
                const corM   = media===0?C.faint:media>=metaSem?"#10B981":"#EF4444";
                return (
                  <tr key={si} style={{ borderBottom:`1px solid ${C.border}` }}
                    onMouseEnter={e=>e.currentTarget.style.background="#F2F2F2"}
                    onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                    <td style={{ padding:"12px 14px", fontWeight:700, color:C.sub }}>{si+1}ª Semana</td>
                    <td style={{ padding:"12px 14px", textAlign:"right", color:C.faint }}>{diasV.length}</td>
                    <td style={{ padding:"12px 14px", textAlign:"right", color:"#8B5CF6", fontWeight:600 }}>{diasV.length?fmt(totOc):"—"}</td>
                    <td style={{ padding:"12px 14px", textAlign:"right", color:C.blue, fontWeight:600 }}>{diasV.length?fmt(totAs):"—"}</td>
                    <td style={{ padding:"12px 14px", textAlign:"right", color:C.text, fontWeight:800 }}>{diasV.length?fmt(totSem):"—"}</td>
                    <td style={{ padding:"12px 14px", textAlign:"right", color:corM, fontWeight:700 }}>{media>0?fmt(media):"—"}</td>
                    <td style={{ padding:"12px 14px", textAlign:"right", color:vsMeta>0?"#10B981":vsMeta<0?"#EF4444":C.faint, fontWeight:700 }}>
                      {media>0?`${vsMeta>=0?"+":""}${fmt(vsMeta)}`:"—"}
                    </td>
                    <td style={{ padding:"12px 14px", textAlign:"right" }}>
                      {diasV.length===0 ? (
                        <span style={{ fontSize:11, color:C.faint }}>Futuro</span>
                      ) : diasFut>0 ? (
                        <span style={{ fontSize:11, color:C.amber, fontWeight:700 }}>Proj: {fmt(proj)}</span>
                      ) : (
                        <span style={{ padding:"3px 10px", borderRadius:20, fontSize:11, fontWeight:700,
                          background:media>=metaSem?"#D1FAE5":"#FEE2E2",
                          color:media>=metaSem?"#059669":"#DC2626" }}>
                          {media>=metaSem?"✓ Acima":"✕ Abaixo"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr style={{ background:"#FDF2F2", borderTop:`2px solid ${C.blue}` }}>
                <td style={{ padding:"12px 14px", fontWeight:800, color:C.text }}>Total do Mês</td>
                <td style={{ padding:"12px 14px", textAlign:"right", color:C.faint, fontWeight:700 }}>{data.dias_com_producao} dias</td>
                <td style={{ padding:"12px 14px", textAlign:"right", color:"#8B5CF6", fontWeight:800 }}>{fmt(data.total_ocupacional)}</td>
                <td style={{ padding:"12px 14px", textAlign:"right", color:C.blue, fontWeight:800 }}>{fmt(data.total_assistencial)}</td>
                <td style={{ padding:"12px 14px", textAlign:"right", color:"#10B981", fontWeight:800, fontSize:14 }}>{fmt(data.total_geral)}</td>
                <td style={{ padding:"12px 14px", textAlign:"right", color:data.media_diaria>=metaMediaMensal?"#10B981":"#EF4444", fontWeight:800 }}>{fmt(data.media_diaria)}</td>
                <td style={{ padding:"12px 14px", textAlign:"right", color:data.media_diaria>=metaMediaMensal?"#10B981":"#EF4444", fontWeight:700 }}>
                  {`${data.media_diaria-metaMediaMensal>=0?"+":""}${fmt(data.media_diaria-metaMediaMensal)}`}
                </td>
                <td style={{ padding:"12px 14px", textAlign:"right" }}>
                  <span style={{ padding:"3px 12px", borderRadius:20, fontSize:11, fontWeight:800,
                    background:data.total_geral>=metaMensal?"#D1FAE5":"#FEE2E2",
                    color:data.total_geral>=metaMensal?"#059669":"#DC2626" }}>
                    {data.total_geral>=metaMensal?"✓ Meta atingida":`${((data.total_geral/metaMensal)*100).toFixed(1)}% da meta`}
                  </span>
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
      <ProducaoProfissionais ano={ano} mes={mes} API={API} setAno={setAno} setMes={setMes} />
    </div>
  );
}


// ── FINANCEIRO ────────────────────────────────────────────────────────────────
function SecaoFinanceiro({ periodo, modulo }) {
  const atendSQL      = modulo?.atendCodes?.length === 1 ? modulo.atendCodes[0]
                      : modulo?.atendCodes?.length > 1  ? ""   // multi-code handled by setores or no filter
                      : "";
  const setoresFiltro = modulo?.id === "laboratorio" ? (modulo.setores||[]).join(",") : "";
  const isOcup        = modulo?.id === "med_ocup";
  const atendOcup     = isOcup ? "ADM" : atendSQL; // backend handles single code; for multi-ocup use resumo fields

  const { data: resumo, loading: lR, error: eR } = useFetch("/api/financeiro/resumo",       { periodo, atend: atendSQL, setores: setoresFiltro });
  const { data: conv,   loading: lCv }            = useFetch("/api/financeiro/por-convenio", { periodo, atend: atendSQL, setores: setoresFiltro });
  const { data: part,   loading: lPart }          = useFetch("/api/financeiro/particular",   { periodo, atend: atendSQL });

  const percParticular = resumo?.faturamento > 0 && part?.total
    ? ((part.total / resumo.faturamento) * 100).toFixed(1) : null;

  return (
    <>
      {eR && <Err msg={eR.message} />}

      {/* KPIs principais */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:16, marginBottom:16 }}>
        <KPI label="Faturado" value={brl(resumo?.faturamento)} loading={lR}
          sub={periodo==="30d" ? `${num(resumo?.total_os)} OSs · mês atual` : periodo==="90d" ? `${num(resumo?.total_os)} OSs · últimos 3 meses` : `${num(resumo?.total_os)} OSs · últimos 7 dias`}
          accent={"#8B1A1A"} />
        <KPI label="Ticket Médio" value={brl(resumo?.ticket_medio)} loading={lR} accent={"#6B2525"} />
        <KPI label="Particular" value={brl(part?.total)} loading={lPart}
          sub={`${num(part?.qtd_os)} OSs · ${(part?.convenios||[]).map(c=>c.convenio).join(" + ") || "—"}`}
          accent={"#F59E0B"} />
        <KPI label="% Particular" value={pct(percParticular)} loading={lR || lPart}
          deltaUp={percParticular >= 10}
          sub={percParticular >= 10 ? "Acima de 10% do total" : "Abaixo de 10% do total"}
          accent={"#F59E0B"} />
      </div>

      {/* Gráfico mensal — largura total, grande para fácil leitura */}
      <div style={{ marginBottom:12 }}>
        <GraficoComparativoAnual
          titulo="Produção Mensal" subtitulo="Comparativo por ano · R$"
          endpoint="/api/comparativo/receita-mensal" deps={{ atend: atendSQL }}
          dataKey="receita" fmt={brl} height={400}
        />
      </div>

      {/* Gráficos secundários */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginBottom:16 }}>
        <div style={{ display:"none" }}>placeholder</div>
        <Card title="Por Convênio" subtitle={`Top ${(conv||[]).slice(0,10).length} convênios no período`}>
          {lCv ? <Skeleton h={260} /> : (conv||[]).length === 0 ? (
            <div style={{ padding:"32px", textAlign:"center", color:"#6B7280", fontSize:12 }}>Sem dados no período</div>
          ) : (
            <div style={{ overflowY:"auto", maxHeight:260 }}>
              {(conv||[]).slice(0,10).map((item, i) => {
                const max = (conv||[])[0]?.receita || 1;
                const pct = Math.max(4, (item.receita / max) * 100);
                return (
                  <div key={i} style={{ marginBottom:10 }}>
                    <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:3 }}>
                      <span style={{ fontSize:11, color:"#111827", fontWeight:600, maxWidth:"60%", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                        {item.nom_convenio || "Sem convênio"}
                      </span>
                      <span style={{ fontSize:11, color:CORES_ESP[i%CORES_ESP.length], fontWeight:700 }}>
                        {brlk(item.receita)}
                      </span>
                    </div>
                    <div style={{ height:6, background:"#EAEDF2", borderRadius:4, overflow:"hidden" }}>
                      <div style={{
                        height:"100%", borderRadius:4,
                        width:`${pct}%`,
                        background:CORES_ESP[i%CORES_ESP.length],
                        transition:"width 0.6s ease",
                      }} />
                    </div>
                    <div style={{ fontSize:10, color:"#6B7280", marginTop:2 }}>
                      {num(item.qtd_os)} OSs
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      <GraficoComparativoAnual
        titulo="Produção Total — Comparativo Anual" subtitulo="Mesmo período em anos anteriores"
        endpoint="/api/comparativo/faturamento" deps={{ periodo, atend: atendSQL }}
        dataKey="producao" fmt={brl} height={160}
      />
    </>
  );
}

// ── ATENDIMENTOS ──────────────────────────────────────────────────────────────

// ── MÓDULO MEDICINA OCUPACIONAL ───────────────────────────────────────────────

// ── MÓDULO LABORATÓRIO ────────────────────────────────────────────────────────
const CORES_LAB = ["#8B1A1A", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6", "#56B4E9","#F0E442","#0072B2","#CC79A7","#009E73"];

function SecaoLaboratorio({ periodo }) {
  const { data: resumo, loading: lR } = useFetch("/api/laboratorio/resumo",    { periodo });
  const { data: setores, loading: lS } = useFetch("/api/laboratorio/por-setor",{ periodo });
  const { data: dias,   loading: lD } = useFetch("/api/atendimentos/por-dia",  { periodo, setores: "LAB,RAD,USG,CAR,PNE,FON,OFT,NEU,PSI,ACV" });

  const brlFull = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";

  // Mapa cod -> dados reais
  const mapaSetores = {};
  (setores||[]).forEach(s => { mapaSetores[s.cod_setor?.trim()] = s; });

  const SETORES_CONFIG = [
    { cod:"LAB", label:"Laboratório"    },
    { cod:"RAD", label:"Radiologia"     },
    { cod:"USG", label:"Ultrassom"      },
    { cod:"CAR", label:"Cardiologia"    },
    { cod:"PNE", label:"Pneumologia"    },
    { cod:"FON", label:"Fonoaudiologia" },
    { cod:"OFT", label:"Oftalmologia"   },
    { cod:"NEU", label:"Neurologia"     },
    { cod:"PSI", label:"Psicologia"     },
    { cod:"ACV", label:"Acuidade Visual"},
  ];

  return (
    <div style={{ background:"#fff", border:`2px solid ${"#10B981"}33`, borderRadius:16, overflow:"hidden" }}>
      {/* Header */}
      <div style={{ background:`${"#10B981"}18`, borderBottom:`1px solid ${"#10B981"}33`, padding:"14px 20px", display:"flex", alignItems:"center", gap:10, flexWrap:"wrap" }}>
        <span style={{ fontSize:20 }}>🔬</span>
        <div>
          <div style={{ fontSize:15, fontWeight:800, color:"#10B981" }}>Laboratório & Exames</div>
          <div style={{ fontSize:12, color:"#6B7280" }}>Lab · Radiologia · Ultrassom · Cardiologia · e outros</div>
        </div>
        <div style={{ marginLeft:"auto", display:"flex", gap:20 }}>
          {[
            { label:"Total Exames",    val: num(resumo?.total_exames),    color:"#10B981", sub: `${num(resumo?.total_os)} OSs` },
            { label:"Pacientes",       val: num(resumo?.pacientes_unicos),color:"#8B1A1A" },
            { label:"Produção",       val: brlFull(resumo?.faturamento), color:"#F59E0B"  },
            { label:"Ticket Médio",    val: brlFull(resumo?.ticket_medio),color:"#8B5CF6" },
          ].map((k,i) => (
            <div key={i} style={{ textAlign:"right" }}>
              <div style={{ fontSize:10, color:"#6B7280", fontWeight:600, textTransform:"uppercase" }}>{k.label}</div>
              <div style={{ fontSize:16, fontWeight:800, color:k.color }}>{lR ? "..." : k.val}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ padding:"16px 20px" }}>
        {/* Cards por setor com dados reais */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))", gap:8, marginBottom:16 }}>
          {SETORES_CONFIG.map((s,i) => {
            const d = mapaSetores[s.cod];
            const color = CORES_LAB[i % CORES_LAB.length];
            return (
              <div key={i} style={{ background:"#EEEEEE", borderRadius:10, padding:"12px 14px", borderTop:`3px solid ${color}` }}>
                <div style={{ fontSize:10, color:"#6B7280", fontWeight:700, textTransform:"uppercase", marginBottom:6 }}>{s.label}</div>
                {lS
                  ? <div style={{ height:22, background:"#EAEDF2", borderRadius:4, animation:"pulse 1.5s infinite" }} />
                  : <>
                      <div style={{ fontSize:22, fontWeight:800, color }}>{d ? num(d.total_itens) : "0"}</div>
                      <div style={{ fontSize:10, color:"#6B7280", marginTop:3 }}>
                        {d ? `${num(d.total_os)} OSs · ${num(d.pacientes)} pac.` : "sem dados"}
                      </div>
                      {d?.faturamento > 0 && (
                        <div style={{ fontSize:11, color:"#F59E0B", fontWeight:700, marginTop:2 }}>
                          {brlFull(d.faturamento)}
                        </div>
                      )}
                    </>
                }
              </div>
            );
          })}
        </div>

        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16 }}>
          {/* Ranking setores */}
          <Card title="Ranking por Setor" subtitle="Volume de exames no período">
            {lS ? <Skeleton h={260} /> : (setores||[]).length === 0 ? (
              <div style={{ padding:"40px", textAlign:"center", color:"#6B7280", fontSize:12 }}>Sem dados</div>
            ) : (
              <div style={{ overflowY:"auto", maxHeight:260 }}>
                {(setores||[]).map((s,i) => {
                  const max = (setores||[])[0]?.total_os || 1;
                  const pct = Math.max(3, (s.total_os / max) * 100);
                  const color = CORES_LAB[i % CORES_LAB.length];
                  return (
                    <div key={i} style={{ marginBottom:12 }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3 }}>
                        <span style={{ fontSize:12, color:"#111827", fontWeight:700 }}>{s.nome_setor}</span>
                        <span style={{ fontSize:12, color, fontWeight:800 }}>{num(s.total_itens)}</span>
                      </div>
                      <div style={{ height:7, background:"#EAEDF2", borderRadius:4, overflow:"hidden", marginBottom:2 }}>
                        <div style={{ height:"100%", width:`${pct}%`, borderRadius:4, background:color }} />
                      </div>
                      <div style={{ fontSize:10, color:"#6B7280" }}>{num(s.total_os)} OSs · {num(s.pacientes)} pac. · {brlFull(s.faturamento)}</div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>

          {/* Volume diário */}
          <Card title="Volume Diário de Exames" subtitle="Todos os setores">
            {lD ? <Skeleton h={260} /> : (
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={dias||[]}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
                  <XAxis dataKey="data" tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false}
                    tickFormatter={v => v?.slice(5)} />
                  <YAxis tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CTip />} />
                  <Line type="monotone" dataKey="qtd" stroke={"#10B981"} strokeWidth={3}
                    dot={{ r:4, fill:"#10B981", strokeWidth:0 }} name="Exames" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

// ── MÓDULO ASSISTENCIAL ────────────────────────────────────────────────────────
function SecaoAssistencial({ periodo }) {
  const { data: resumo, loading: lR } = useFetch("/api/atendimentos/resumo",            { periodo, atend: "ASS" });
  const { data: esp,    loading: lE } = useFetch("/api/atendimentos/por-especialidade",  { periodo, atend: "ASS" });
  const { data: dias,   loading: lD } = useFetch("/api/atendimentos/por-dia",            { periodo, atend: "ASS" });
  const { data: med,    loading: lM } = useFetch("/api/atendimentos/por-medico",         { periodo });
  const { data: conv,   loading: lC } = useFetch("/api/financeiro/por-convenio",         { periodo, atend: "ASS" });
  const { data: resumoFin, loading: lF } = useFetch("/api/financeiro/resumo",            { periodo, atend: "ASS" });

  const brlFull = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";

  const brlFullAssist = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v) : "n/d";
  const topMedico = (med||[])[0];
  const topConv   = (conv||[])[0];

  return (
    <div style={{ background:"#fff", border:`2px solid ${"#8B1A1A"}33`, borderRadius:16, overflow:"hidden" }}>
      <div style={{ background:`${"#8B1A1A"}18`, borderBottom:`1px solid ${"#8B1A1A"}33`, padding:"14px 20px", display:"flex", alignItems:"center", gap:10 }}>
        <span style={{ fontSize:20 }}>🩺</span>
        <div>
          <div style={{ fontSize:15, fontWeight:800, color:"#8B1A1A" }}>Assistencial</div>
          <div style={{ fontSize:12, color:"#6B7280" }}>Consultas e atendimentos clínicos</div>
        </div>
      </div>

      <div style={{ padding:"16px 20px" }}>
        <BriefingCard
          cor="#8B1A1A"
          cacheKey={`briefing_assistencial_${periodo}`}
          disabled={lR || lF}
          promptFn={() => `Você é um analista de gestão clínica. Gere um briefing executivo em no máximo 4 frases, direto e profissional, sem markdown.

DADOS — Módulo Assistencial (período: ${periodo}):
- Total de atendimentos: ${resumo?.total_atendimentos ?? "n/d"}
- Produção financeira: ${brlFullAssist(resumoFin?.faturamento)}
- Ticket médio: ${brlFullAssist(resumoFin?.ticket_medio)}
- Especialidades ativas: ${(esp||[]).length}
- Top médico: ${topMedico ? topMedico.profissional+" ("+brlFullAssist(topMedico.producao)+")" : "n/d"}
- Principal convênio: ${topConv ? topConv.convenio+" ("+brlFullAssist(topConv.producao)+")" : "n/d"}

Destaque desempenho dos médicos, alertas de queda e sugestões para aumentar a produção.`}
        />
        {/* KPIs */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:12, marginBottom:16 }}>
          <div style={{ background:"#EEEEEE", borderRadius:10, padding:"14px 16px", borderTop:`3px solid ${"#8B1A1A"}` }}>
            <div style={{ fontSize:11, color:"#6B7280", fontWeight:700, textTransform:"uppercase", marginBottom:6 }}>Total Atendimentos</div>
            <div style={{ fontSize:28, fontWeight:900, color:"#111827" }}>{lR ? "..." : num(resumo?.total_atendimentos)}</div>
          </div>
          <div style={{ background:"#EEEEEE", borderRadius:10, padding:"14px 16px", borderTop:`3px solid ${"#10B981"}` }}>
            <div style={{ fontSize:11, color:"#6B7280", fontWeight:700, textTransform:"uppercase", marginBottom:6 }}>Produção</div>
            <div style={{ fontSize:22, fontWeight:800, color:"#10B981" }}>{lF ? "..." : brlFull(resumoFin?.faturamento)}</div>
          </div>
          <div style={{ background:"#EEEEEE", borderRadius:10, padding:"14px 16px", borderTop:`3px solid ${"#8B5CF6"}` }}>
            <div style={{ fontSize:11, color:"#6B7280", fontWeight:700, textTransform:"uppercase", marginBottom:6 }}>Ticket Médio</div>
            <div style={{ fontSize:22, fontWeight:800, color:"#8B5CF6" }}>{lF ? "..." : brlFull(resumoFin?.ticket_medio)}</div>
          </div>
          <div style={{ background:"#EEEEEE", borderRadius:10, padding:"14px 16px", borderTop:`3px solid ${"#F59E0B"}` }}>
            <div style={{ fontSize:11, color:"#6B7280", fontWeight:700, textTransform:"uppercase", marginBottom:6 }}>Especialidades</div>
            <div style={{ fontSize:28, fontWeight:900, color:"#F59E0B" }}>{lE ? "..." : num((esp||[]).length)}</div>
          </div>
        </div>

        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginBottom:16 }}>
          {/* Especialidades */}
          <Card title="Por Especialidade" subtitle="Distribuição no período">
            {lE ? <Skeleton h={220} /> : (esp||[]).length === 0 ? (
              <div style={{ padding:"40px", textAlign:"center", color:"#6B7280", fontSize:12 }}>Sem dados</div>
            ) : (
              <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:0, alignItems:"center" }}>
                <ResponsiveContainer width="100%" height={220}>
                  <PieChart>
                    <Pie data={(esp||[]).slice(0,8)} dataKey="qtd" nameKey="especialidade"
                      cx="50%" cy="50%" outerRadius={85} innerRadius={50} paddingAngle={3}>
                      {(esp||[]).slice(0,8).map((_,i) => <Cell key={i} fill={CORES_ESP[i%CORES_ESP.length]} />)}
                    </Pie>
                    <Tooltip content={<CTip />} />
                  </PieChart>
                </ResponsiveContainer>
                <div style={{ paddingRight:8 }}>
                  {(esp||[]).slice(0,8).map((item,i) => {
                    const total = (esp||[]).slice(0,8).reduce((s,r)=>s+r.qtd,0);
                    const pct = total > 0 ? ((item.qtd/total)*100).toFixed(1) : 0;
                    return (
                      <div key={i} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:7 }}>
                        <div style={{ width:10, height:10, borderRadius:3, flexShrink:0, background:CORES_ESP[i%CORES_ESP.length] }} />
                        <div style={{ flex:1, minWidth:0 }}>
                          <div style={{ fontSize:11, color:"#111827", fontWeight:600, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{item.especialidade}</div>
                          <div style={{ fontSize:10, color:"#6B7280" }}>{num(item.qtd)} · {pct}%</div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </Card>

          {/* Atendimentos por dia */}
          <Card title="Volume Diário" subtitle="Atendimentos assistenciais">
            {lD ? <Skeleton h={220} /> : (
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={dias||[]}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
                  <XAxis dataKey="data" tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false}
                    tickFormatter={v => v?.slice(5)} />
                  <YAxis tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CTip />} />
                  <Line type="monotone" dataKey="qtd" stroke={"#8B1A1A"} strokeWidth={3}
                    dot={{ r:4, fill:"#8B1A1A", strokeWidth:0 }} name="Atendimentos" />
                </LineChart>
              </ResponsiveContainer>
            )}
          </Card>
        </div>

        {/* Top médicos */}
        <Card title="Top Médicos Assistenciais" subtitle="Por volume de atendimentos">
          {lM ? <Skeleton h={150} /> : (
            <div style={{ overflowX:"auto" }}>
              <table style={{ width:"100%", fontSize:12, borderCollapse:"collapse" }}>
                <thead>
                  <tr style={{ color:"#6B7280", borderBottom:`1px solid ${"#EAEDF2"}` }}>
                    {["#","Médico","Especialidade","OSs"].map(h => (
                      <th key={h} style={{ padding:"8px 10px", fontWeight:700, textAlign:h==="OSs"?"right":"left", fontSize:11 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(med||[]).slice(0,8).map((r,i) => (
                    <tr key={i} style={{ borderBottom:`1px solid ${"#EAEDF2"}` }}
                      onMouseEnter={e=>e.currentTarget.style.background="#F2F2F2"}
                      onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                      <td style={{ padding:"8px 10px", color:"#6B7280", fontWeight:700 }}>{i+1}</td>
                      <td style={{ padding:"8px 10px", color:"#111827", fontWeight:700 }}>{r.apelido||r.medico}</td>
                      <td style={{ padding:"8px 10px", color:"#6B7280" }}>{r.especialidade||"—"}</td>
                      <td style={{ padding:"8px 10px", textAlign:"right", color:"#8B1A1A", fontWeight:800 }}>{num(r.total_os)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

function SecaoOcupacional({ periodo }) {
  const { data: resumo, loading: lR } = useFetch("/api/ocupacional/resumo",    { periodo });
  const { data: emp,    loading: lE } = useFetch("/api/ocupacional/por-empresa",{ periodo });
  const { data: dias,   loading: lD } = useFetch("/api/ocupacional/por-dia",    { periodo });

  const brlFull = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";

  const tipos = [
    { label:"Admissional",   key:"admissional",  color:"#8B1A1A"  },
    { label:"Periódico",     key:"periodico",    color:"#10B981"   },
    { label:"Demissional",   key:"demissional",  color:"#EF4444"     },
    { label:"Ret. Trabalho", key:"ret_trabalho", color:"#F59E0B"   },
    { label:"Mud. Função",   key:"mud_funcao",   color:"#8B5CF6"  },
    { label:"Méd. Ocup.",    key:"med_ocup",     color:"#56B4E9" },
  ];

  return (
    <div style={{ background:"#fff", border:`2px solid ${"#F59E0B"}33`, borderRadius:16, overflow:"hidden", marginBottom:16 }}>
      {/* Header */}
      <div style={{ background:`${"#F59E0B"}18`, borderBottom:`1px solid ${"#F59E0B"}33`, padding:"14px 20px", display:"flex", alignItems:"center", gap:10 }}>
        <span style={{ fontSize:20 }}>🏭</span>
        <div>
          <div style={{ fontSize:15, fontWeight:800, color:"#F59E0B" }}>Medicina Ocupacional</div>
          <div style={{ fontSize:12, color:"#6B7280" }}>Admissional · Periódico · Demissional · e outros</div>
        </div>
      </div>

      <div style={{ padding:"16px 20px" }}>
        <BriefingCard
          cor="#D97706"
          cacheKey={`briefing_ocupacional_${periodo}`}
          disabled={lR}
          promptFn={() => {
            const topEmp = (emp||[])[0];
            return `Você é um analista de saúde ocupacional. Gere um briefing executivo em no máximo 4 frases, direto e profissional, sem markdown.

DADOS — Medicina Ocupacional (período: ${periodo}):
- Admissional: ${resumo?.admissional ?? "n/d"} exames
- Periódico: ${resumo?.periodico ?? "n/d"} exames
- Demissional: ${resumo?.demissional ?? "n/d"} exames
- Retorno ao trabalho: ${resumo?.ret_trabalho ?? "n/d"}
- Mudança de função: ${resumo?.mud_funcao ?? "n/d"}
- Total de exames: ${resumo?.total_os ?? "n/d"}
- Pacientes únicos: ${resumo?.pacientes_unicos ?? "n/d"}
- Produção financeira: ${resumo?.faturamento != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(resumo.faturamento) : "n/d"}
- Principal empresa: ${topEmp ? topEmp.empresa+" ("+topEmp.total+" exames)" : "n/d"}

Destaque tipos de exame em crescimento, alertas e oportunidades de captação de empresas.`;
          }}
        />
        {/* KPIs */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(140px,1fr))", gap:10, marginBottom:16 }}>
          {tipos.map(t => (
            <div key={t.key} style={{
              background:"#EEEEEE", borderRadius:10, padding:"12px 14px",
              borderTop:`3px solid ${t.color}`,
            }}>
              <div style={{ fontSize:10, color:"#6B7280", fontWeight:700, textTransform:"uppercase", letterSpacing:"0.05em", marginBottom:6 }}>{t.label}</div>
              {lR
                ? <div style={{ height:24, background:"#EAEDF2", borderRadius:4, animation:"pulse 1.5s infinite" }} />
                : <div style={{ fontSize:22, fontWeight:800, color:t.color }}>{num(resumo?.[t.key])}</div>
              }
            </div>
          ))}
        </div>

        {/* Métricas gerais */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:10, marginBottom:16 }}>
          <div style={{ background:"#EEEEEE", borderRadius:10, padding:"12px 14px", borderTop:`3px solid ${"#8B1A1A"}` }}>
            <div style={{ fontSize:10, color:"#6B7280", fontWeight:700, textTransform:"uppercase", marginBottom:6 }}>Total OSs</div>
            <div style={{ fontSize:24, fontWeight:800, color:"#111827" }}>{lR ? "..." : num(resumo?.total_os)}</div>
          </div>
          <div style={{ background:"#EEEEEE", borderRadius:10, padding:"12px 14px", borderTop:`3px solid ${"#10B981"}` }}>
            <div style={{ fontSize:10, color:"#6B7280", fontWeight:700, textTransform:"uppercase", marginBottom:6 }}>Pacientes Únicos</div>
            <div style={{ fontSize:24, fontWeight:800, color:"#10B981" }}>{lR ? "..." : num(resumo?.pacientes_unicos)}</div>
          </div>
          <div style={{ background:"#EEEEEE", borderRadius:10, padding:"12px 14px", borderTop:`3px solid ${"#8B5CF6"}` }}>
            <div style={{ fontSize:10, color:"#6B7280", fontWeight:700, textTransform:"uppercase", marginBottom:6 }}>Produção</div>
            <div style={{ fontSize:20, fontWeight:800, color:"#8B5CF6" }}>{lR ? "..." : brlFull(resumo?.faturamento)}</div>
          </div>
          <div style={{ background:"#EEEEEE", borderRadius:10, padding:"12px 14px", borderTop:`3px solid ${"#F59E0B"}` }}>
            <div style={{ fontSize:10, color:"#6B7280", fontWeight:700, textTransform:"uppercase", marginBottom:6 }}>Ticket Médio</div>
            <div style={{ fontSize:20, fontWeight:800, color:"#F59E0B" }}>{lR ? "..." : brlFull(resumo?.ticket_medio)}</div>
          </div>
        </div>

        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16 }}>
          {/* Volume por dia */}
          <Card title="Volume Diário — Ocupacional" subtitle="Por tipo de atendimento">
            {lD ? <Skeleton h={200} /> : (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={dias||[]} barSize={14}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
                  <XAxis dataKey="data" tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false}
                    tickFormatter={v => v?.slice(5)} />
                  <YAxis tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false} />
                  <Tooltip content={<CTip />} />
                  <Legend iconSize={10} wrapperStyle={{ fontSize:11, color:"#6B7280" }} />
                  <Bar dataKey="admissional" stackId="a" fill={"#8B1A1A"}  name="Admissional" />
                  <Bar dataKey="periodico"   stackId="a" fill={"#10B981"}   name="Periódico"   />
                  <Bar dataKey="demissional" stackId="a" fill={"#EF4444"}     name="Demissional" radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </Card>

          {/* Top empresas */}
          <Card title="Top Empresas" subtitle="Por volume de atendimentos">
            {lE ? <Skeleton h={200} /> : (
              <div style={{ overflowY:"auto", maxHeight:220 }}>
                {(emp||[]).map((e,i) => {
                  const max = (emp||[])[0]?.total_os || 1;
                  const pct = Math.max(4, (e.total_os / max) * 100);
                  return (
                    <div key={i} style={{ marginBottom:10 }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3 }}>
                        <span style={{ fontSize:11, color:"#111827", fontWeight:600, maxWidth:"65%", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                          {e.empresa}
                        </span>
                        <span style={{ fontSize:11, color:"#F59E0B", fontWeight:700 }}>{num(e.total_os)} OSs</span>
                      </div>
                      <div style={{ height:6, background:"#EAEDF2", borderRadius:4, overflow:"hidden" }}>
                        <div style={{ height:"100%", width:`${pct}%`, borderRadius:4, background:CORES_ANOS[i%CORES_ANOS.length] }} />
                      </div>
                      <div style={{ display:"flex", gap:10, marginTop:2, fontSize:10, color:"#6B7280" }}>
                        <span>Adm: {num(e.admissional)}</span>
                        <span>Per: {num(e.periodico)}</span>
                        <span>Dem: {num(e.demissional)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function SecaoAtendimentos({ periodo, modulo }) {
  const atendFiltro   = modulo?.atendCodes?.length === 1 ? modulo.atendCodes[0] : "";
  const setoresFiltro = modulo?.id === "laboratorio" ? modulo.setores.join(",") : "";

  const { data: resumo, loading: lR, error: eR } = useFetch("/api/atendimentos/resumo",            { periodo, atend: atendFiltro, setores: setoresFiltro });
  const { data: esp,    loading: lE }             = useFetch("/api/atendimentos/por-especialidade", { periodo, atend: atendFiltro, setores: setoresFiltro });
  const { data: dias,   loading: lD }             = useFetch("/api/atendimentos/por-dia",           { periodo, atend: atendFiltro, setores: setoresFiltro });
  const { data: med,    loading: lM }             = useFetch("/api/atendimentos/por-medico",        { periodo, setores: setoresFiltro });

  return (
    <>
      {eR && <Err msg={eR.message} />}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:16, marginBottom:16 }}>
        <KPI label="Total Atendimentos" value={num(resumo?.total_atendimentos)} loading={lR} accent={"#8B1A1A"} />
        <KPI label="Assistencial"       value={num(resumo?.assistencial)}       loading={lR} accent={"#10B981"}  />
        <KPI label="Med. Ocupacional"   value={num(resumo?.med_ocup)}           loading={lR} accent={"#6B2525"} />
        <KPI label="Med. Ocupacional"   value={num(resumo?.med_ocup)}           loading={lR} accent={"#F59E0B"} />
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginBottom:16 }}>
        <Card title="Por Especialidade" subtitle="Distribuição no período">
          {lE ? <Skeleton h={260} /> : (esp||[]).length === 0 ? (
            <div style={{ padding:"40px", textAlign:"center", color:"#6B7280", fontSize:12 }}>
              Sem dados de especialidade no período
            </div>
          ) : (
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:0, alignItems:"center" }}>
              <ResponsiveContainer width="100%" height={260}>
                <PieChart>
                  <Pie data={(esp||[]).slice(0,8)} dataKey="qtd" nameKey="especialidade"
                    cx="50%" cy="50%" outerRadius={90} innerRadius={52} paddingAngle={3}>
                    {(esp||[]).slice(0,8).map((_,i) => <Cell key={i} fill={CORES_ESP[i%CORES_ESP.length]} />)}
                  </Pie>
                  <Tooltip content={<CTip />} />
                </PieChart>
              </ResponsiveContainer>
              {/* Legenda lateral */}
              <div style={{ paddingRight:8 }}>
                {(esp||[]).slice(0,8).map((item,i) => {
                  const total = (esp||[]).slice(0,8).reduce((s,r) => s + r.qtd, 0);
                  const pct   = total > 0 ? ((item.qtd / total) * 100).toFixed(1) : 0;
                  return (
                    <div key={i} style={{ display:"flex", alignItems:"center", gap:8, marginBottom:8 }}>
                      <div style={{ width:10, height:10, borderRadius:3, flexShrink:0, background:CORES_ESP[i%CORES_ESP.length] }} />
                      <div style={{ flex:1, minWidth:0 }}>
                        <div style={{ fontSize:11, color:"#111827", fontWeight:600, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                          {item.especialidade}
                        </div>
                        <div style={{ fontSize:10, color:"#6B7280" }}>
                          {num(item.qtd)} atend. · {pct}%
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Card>

        <Card title="Atendimentos por Dia" subtitle="Volume diário no período">
          {lD ? <Skeleton h={220} /> : (
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={dias||[]}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
                <XAxis dataKey="data" tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false}
                  tickFormatter={v => v?.slice(5)} />
                <YAxis tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CTip />} />
                <Line type="monotone" dataKey="qtd" stroke={"#8B5CF6"} strokeWidth={2.5}
                  dot={false} name="Atendimentos" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <div style={{ marginBottom:12 }}>
        <GraficoComparativoAnual
          titulo="Total de Atendimentos — Comparativo Anual" subtitulo="Mesmo período em anos anteriores"
          endpoint="/api/comparativo/atendimentos" deps={{ periodo, atend: atendFiltro }}
          dataKey="total" fmt={num} height={160}
        />
      </div>

      <Card title="Top Médicos por Volume" subtitle="Ordenado por total de OSs">
        {lM ? <Skeleton h={160} /> : (
          <div style={{ overflowX:"auto" }}>
            <table style={{ width:"100%", fontSize:12, borderCollapse:"collapse" }}>
              <thead>
                <tr style={{ color:"#6B7280", borderBottom:`1px solid ${"#EAEDF2"}` }}>
                  {["#","Médico","Especialidade","OSs"].map(h => (
                    <th key={h} style={{ padding:"8px 10px", fontWeight:700, textAlign: h==="OSs" ? "right" : "left", fontSize:11 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(med||[]).map((r,i) => (
                  <tr key={i} style={{ borderBottom:`1px solid ${"#EAEDF2"}`, transition:"background 0.1s" }}
                    onMouseEnter={e => e.currentTarget.style.background="#F2F2F2"}
                    onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                    <td style={{ padding:"10px", color:"#6B7280", fontWeight:700 }}>{i+1}</td>
                    <td style={{ padding:"10px", color:"#111827", fontWeight:700 }}>{r.apelido||r.medico}</td>
                    <td style={{ padding:"10px", color:"#6B7280" }}>{r.especialidade||"—"}</td>
                    <td style={{ padding:"10px", color:"#8B1A1A", fontWeight:700, textAlign:"right" }}>{num(r.total_os)}</td>
                    <td style={{ padding:"10px", color:"#6B7280", textAlign:"right" }}>{num(r.cirurgias)}</td>
                    <td style={{ padding:"10px", color:"#6B7280", textAlign:"right" }}>{num(r.emergencias)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ── AGENDAMENTOS ──────────────────────────────────────────────────────────────

// ── AGENDA DO MÉDICO ──────────────────────────────────────────────────────────
function PainelAgendaMedico() {
  const hoje     = new Date();
  const hojeStr  = `${hoje.getFullYear()}-${String(hoje.getMonth()+1).padStart(2,"0")}-${String(hoje.getDate()).padStart(2,"0")}`;

  const [medicoSel, setMedicoSel]   = useState(null);
  const [busca,     setBusca]       = useState("");
  const [view,      setView]        = useState("dia");   // "dia" | "mensal"
  const [dataSel,   setDataSel]     = useState(hojeStr);
  const [anoSel,    setAnoSel]      = useState(hoje.getFullYear());
  const [mesSel,    setMesSel]      = useState(hoje.getMonth() + 1);
  const [diaSel,    setDiaSel]      = useState(null);    // clique no calendário mensal

  const { data: medicos, loading: lMed } = useFetch("/api/agenda/medicos", {});

  const { data: agendaDia, loading: lDia } = useFetch(
    "/api/agenda/dia",
    medicoSel ? { cod_medico: medicoSel.cod, data: view === "dia" ? dataSel : diaSel || hojeStr } : { skip: true }
  );

  const { data: agendaMes, loading: lMes } = useFetch(
    "/api/agenda/mensal",
    medicoSel ? { cod_medico: medicoSel.cod, ano: anoSel, mes: mesSel } : { skip: true }
  );

  const brlFull = (v) => v != null
    ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",minimumFractionDigits:2}).format(v) : "—";

  const STATUS_COR = { A: "#8B1A1A", E: "#10B981", C: "#EF4444", B: "#F59E0B" };
  const STATUS_BG  = { A: "#8B1A1A"+"22", E: "#10B981"+"22", C: "#EF4444"+"22", B: "#F59E0B"+"22" };
  const STATUS_LBL = { A:"Aberto", E:"Executado", C:"Cancelado", B:"Bloqueado" };

  // Mapa de dias do mês com dados
  const mapasMes = {};
  (agendaMes||[]).forEach(d => { mapasMes[d.data] = d; });

  // Monta calendário mensal
  const ultimoDia   = new Date(anoSel, mesSel, 0).getDate();
  const semanasCal  = (() => {
    const semanas = [];
    let semana    = new Array(6).fill(null);
    for (let d = 1; d <= ultimoDia; d++) {
      const date   = new Date(anoSel, mesSel - 1, d);
      const jsDay  = date.getDay();
      if (jsDay === 0) continue;
      const col    = jsDay - 1;
      const ds     = `${anoSel}-${String(mesSel).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
      semana[col]  = { dia: d, data: ds, ...(mapasMes[ds] || {}) };
      if (jsDay === 6 || d === ultimoDia) { semanas.push([...semana]); semana = new Array(6).fill(null); }
    }
    return semanas;
  })();

  const medicosFiltrados = (medicos||[]).filter(m =>
    !busca || m.nome?.toLowerCase().includes(busca.toLowerCase()) ||
    m.apelido?.toLowerCase().includes(busca.toLowerCase())
  );

  const btnView = (v, label) => (
    <button onClick={() => setView(v)} style={{
      padding:"5px 14px", borderRadius:8, border:`1px solid ${view===v ? "#8B1A1A" : "#EAEDF2"}`,
      background: view===v ? "#8B1A1A" : "#fff",
      color: view===v ? "#0F172A" : "#6B7280",
      fontSize:11, fontWeight:700, cursor:"pointer", transition:"all 0.15s",
    }}>{label}</button>
  );

  return (
    <div style={{ marginTop:16 }}>
      <div style={{ fontSize:13, fontWeight:800, color:"#111827", marginBottom:12 }}>Agenda do Médico</div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(260px,1fr))", gap:12 }}>

        {/* ── COLUNA ESQUERDA: lista de médicos ── */}
        <div style={{ background:"#fff", border:`1px solid ${"#EAEDF2"}`, borderRadius:12, overflow:"hidden" }}>
          <div style={{ padding:"12px 14px", borderBottom:`1px solid ${"#EAEDF2"}` }}>
            <div style={{ fontSize:11, fontWeight:800, color:"#6B7280", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>
              Médicos ({medicosFiltrados.length})
            </div>
            <input placeholder="Buscar médico..." value={busca}
              onChange={e => setBusca(e.target.value)} style={{
                width:"100%", padding:"6px 10px", borderRadius:7,
                border:`1px solid ${"#EAEDF2"}`, background:"#EEEEEE",
                color:"#111827", fontSize:11, outline:"none",
              }} />
          </div>
          <div style={{ overflowY:"auto", maxHeight:480 }}>
            {lMed ? (
              <div style={{ padding:16, color:"#6B7280", fontSize:12 }}>Carregando...</div>
            ) : medicosFiltrados.length === 0 ? (
              <div style={{ padding:16, color:"#6B7280", fontSize:12 }}>Nenhum médico com agenda futura</div>
            ) : medicosFiltrados.map((m,i) => (
              <button key={i} onClick={() => { setMedicoSel(m); setDiaSel(null); }} style={{
                width:"100%", textAlign:"left", padding:"10px 14px",
                border:"none", borderBottom:`1px solid ${"#EAEDF2"}`,
                background: medicoSel?.cod === m.cod ? "#FDF2F2" : "transparent",
                cursor:"pointer", transition:"background 0.1s",
                borderLeft: medicoSel?.cod === m.cod ? `3px solid ${"#8B1A1A"}` : "3px solid transparent",
              }}
                onMouseEnter={e => { if(medicoSel?.cod !== m.cod) e.currentTarget.style.background="#F2F2F2"; }}
                onMouseLeave={e => { if(medicoSel?.cod !== m.cod) e.currentTarget.style.background="transparent"; }}>
                <div style={{ fontSize:12, fontWeight:700, color:"#111827" }}>
                  {m.apelido || m.nome}
                </div>
                {m.especialidade && (
                  <div style={{ fontSize:10, color:"#6B7280", marginTop:2 }}>{m.especialidade}</div>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* ── COLUNA DIREITA: agenda ── */}
        <div>
          {!medicoSel ? (
            <div style={{
              background:"#fff", border:`1px solid ${"#EAEDF2"}`, borderRadius:12,
              padding:"60px 20px", textAlign:"center", color:"#6B7280", fontSize:13,
            }}>
              ← Selecione um médico para ver a agenda
            </div>
          ) : (
            <>
              {/* Header médico selecionado */}
              <div style={{
                background:"#fff", border:`1px solid ${"#EAEDF2"}`, borderRadius:12,
                padding:"14px 18px", marginBottom:10,
                display:"flex", alignItems:"center", justifyContent:"space-between", flexWrap:"wrap", gap:10,
              }}>
                <div>
                  <div style={{ fontSize:14, fontWeight:800, color:"#8B1A1A" }}>
                    {medicoSel.apelido || medicoSel.nome}
                  </div>
                  {medicoSel.especialidade && (
                    <div style={{ fontSize:11, color:"#6B7280", marginTop:2 }}>{medicoSel.especialidade}</div>
                  )}
                </div>
                <div style={{ display:"flex", gap:6, alignItems:"center" }}>
                  {btnView("dia",    "📅 Diário")}
                  {btnView("mensal", "📆 Mensal")}
                </div>
              </div>

              {/* ── VIEW DIÁRIA ── */}
              {view === "dia" && (
                <div style={{ background:"#fff", border:`1px solid ${"#EAEDF2"}`, borderRadius:12, overflow:"hidden" }}>
                  <div style={{ padding:"12px 16px", borderBottom:`1px solid ${"#EAEDF2"}`, display:"flex", alignItems:"center", gap:12 }}>
                    <input type="date" value={dataSel} onChange={e => setDataSel(e.target.value)} style={{
                      padding:"6px 10px", borderRadius:8, border:`1px solid ${"#EAEDF2"}`,
                      background:"#EEEEEE", color:"#111827", fontSize:12, outline:"none", fontWeight:700,
                    }} />
                    <span style={{ fontSize:11, color:"#6B7280" }}>
                      {(agendaDia||[]).length} agendamento{(agendaDia||[]).length !== 1 ? "s" : ""}
                    </span>
                  </div>

                  {lDia ? (
                    <div style={{ padding:20 }}><Skeleton h={200} /></div>
                  ) : (agendaDia||[]).length === 0 ? (
                    <div style={{ padding:"40px", textAlign:"center", color:"#6B7280", fontSize:12 }}>
                      Nenhum agendamento neste dia
                    </div>
                  ) : (
                    <div style={{ overflowY:"auto", maxHeight:420 }}>
                      {(agendaDia||[]).map((a,i) => (
                        <div key={i} style={{
                          padding:"12px 16px", borderBottom:`1px solid ${"#EAEDF2"}`,
                          display:"grid", gridTemplateColumns:"60px 1fr auto",
                          gap:12, alignItems:"center", transition:"background 0.1s",
                        }}
                          onMouseEnter={e => e.currentTarget.style.background="#F2F2F2"}
                          onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                          {/* Horário */}
                          <div style={{ textAlign:"center" }}>
                            <div style={{ fontSize:14, fontWeight:800, color:"#8B1A1A" }}>{a.hora_ini}</div>
                            {a.hora_fim && <div style={{ fontSize:10, color:"#6B7280" }}>{a.hora_fim}</div>}
                          </div>
                          {/* Info */}
                          <div>
                            <div style={{ fontSize:13, fontWeight:700, color:"#111827" }}>{a.paciente}</div>
                            <div style={{ display:"flex", gap:8, marginTop:4, flexWrap:"wrap" }}>
                              {a.convenio && <span style={{ fontSize:10, color:"#6B7280" }}>{a.convenio}</span>}
                              {a.local    && <span style={{ fontSize:10, color:"#6B7280" }}>• {a.local}</span>}
                              {a.confirmacao_label && (
                                <span style={{ fontSize:10, color: a.confirmacao==="C" ? "#10B981" : "#F59E0B" }}>
                                  • {a.confirmacao_label}
                                </span>
                              )}
                            </div>
                          </div>
                          {/* Status */}
                          <div style={{ textAlign:"right" }}>
                            <span style={{
                              padding:"3px 10px", borderRadius:20, fontSize:11, fontWeight:700,
                              background: STATUS_BG[a.status] || "#EAEDF2",
                              color: STATUS_COR[a.status] || "#6B7280",
                              border:`1px solid ${(STATUS_COR[a.status]||"#6B7280")}55`,
                              display:"block", marginBottom:4,
                            }}>{STATUS_LBL[a.status] || a.status}</span>
                            {a.valor > 0 && (
                              <div style={{ fontSize:11, color:"#F59E0B", fontWeight:700 }}>{brlFull(a.valor)}</div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* ── VIEW MENSAL ── */}
              {view === "mensal" && (
                <div style={{ background:"#fff", border:`1px solid ${"#EAEDF2"}`, borderRadius:12, overflow:"hidden" }}>
                  {/* Seletor mês/ano */}
                  <div style={{ padding:"12px 16px", borderBottom:`1px solid ${"#EAEDF2"}`, display:"flex", alignItems:"center", gap:10 }}>
                    <select value={mesSel} onChange={e => { setMesSel(Number(e.target.value)); setDiaSel(null); }} style={{
                      padding:"5px 10px", borderRadius:7, border:`1px solid ${"#EAEDF2"}`,
                      background:"#EEEEEE", color:"#111827", fontSize:12, fontWeight:700, outline:"none", cursor:"pointer",
                    }}>
                      {MESES_PT.map((m,i) => <option key={i+1} value={i+1}>{m}</option>)}
                    </select>
                    <select value={anoSel} onChange={e => { setAnoSel(Number(e.target.value)); setDiaSel(null); }} style={{
                      padding:"5px 10px", borderRadius:7, border:`1px solid ${"#EAEDF2"}`,
                      background:"#EEEEEE", color:"#111827", fontSize:12, fontWeight:700, outline:"none", cursor:"pointer",
                    }}>
                      {[hoje.getFullYear(), hoje.getFullYear()+1].map(a => <option key={a} value={a}>{a}</option>)}
                    </select>
                    <span style={{ fontSize:11, color:"#6B7280" }}>
                      {(agendaMes||[]).reduce((s,d)=>s+d.total,0)} agendamentos no mês
                    </span>
                  </div>

                  {/* Calendário */}
                  {lMes ? <div style={{ padding:20 }}><Skeleton h={280} /></div> : (
                    <div style={{ padding:"12px 16px" }}>
                      {/* Header dias */}
                      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(140px,1fr))", gap:4, marginBottom:6 }}>
                        {["Seg","Ter","Qua","Qui","Sex","Sáb"].map(d => (
                          <div key={d} style={{ textAlign:"center", fontSize:10, fontWeight:800, color:"#6B7280", padding:"4px 0" }}>{d}</div>
                        ))}
                      </div>
                      {semanasCal.map((sem, si) => (
                        <div key={si} style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(140px,1fr))", gap:4, marginBottom:4 }}>
                          {sem.map((cel, ci) => {
                            if (!cel) return <div key={ci} />;
                            const temAgenda  = cel.total > 0;
                            const isPast     = new Date(cel.data) < new Date(hojeStr);
                            const isHoje     = cel.data === hojeStr;
                            const isSel      = diaSel === cel.data;
                            return (
                              <button key={ci} onClick={() => { if(temAgenda){ setDiaSel(cel.data); setView("dia"); setDataSel(cel.data); }}} style={{
                                padding:"6px 4px", borderRadius:8, border:`1px solid ${isSel ? "#8B1A1A" : isHoje ? "#8B1A1A"+"55" : "#EAEDF2"}`,
                                background: isSel ? "#8B1A1A"+"33" : isHoje ? "#F2F2F2" : "transparent",
                                cursor: temAgenda ? "pointer" : "default",
                                textAlign:"center", transition:"all 0.15s",
                                opacity: isPast && !temAgenda ? 0.35 : 1,
                              }}
                                onMouseEnter={e => { if(temAgenda && !isSel) e.currentTarget.style.background="#F2F2F2"; }}
                                onMouseLeave={e => { if(!isSel) e.currentTarget.style.background= isHoje ? "#F2F2F2" : "transparent"; }}>
                                <div style={{ fontSize:12, fontWeight: isHoje ? 800 : 600, color: isHoje ? "#10B981" : "#111827" }}>
                                  {cel.dia}
                                </div>
                                {temAgenda && (
                                  <>
                                    <div style={{
                                      width:6, height:6, borderRadius:"50%", margin:"3px auto 1px",
                                      background: cel.cancelados === cel.total ? "#EF4444" : cel.executados === cel.total ? "#10B981" : "#8B1A1A",
                                    }} />
                                    <div style={{ fontSize:9, color:"#6B7280", fontWeight:700 }}>{cel.total}</div>
                                  </>
                                )}
                              </button>
                            );
                          })}
                        </div>
                      ))}

                      {/* Legenda */}
                      <div style={{ display:"flex", gap:16, marginTop:10, padding:"8px 0", borderTop:`1px solid ${"#EAEDF2"}` }}>
                        {[{cor:"#8B1A1A",label:"Agendado"},{cor:"#10B981",label:"Executado"},{cor:"#EF4444",label:"Cancelado"}].map((l,i)=>(
                          <div key={i} style={{ display:"flex", alignItems:"center", gap:5, fontSize:10, color:"#6B7280" }}>
                            <div style={{ width:8, height:8, borderRadius:"50%", background:l.cor }} />
                            {l.label}
                          </div>
                        ))}
                        <div style={{ fontSize:10, color:"#6B7280", marginLeft:"auto" }}>
                          Clique num dia para ver os horários
                        </div>
                      </div>

                      {/* Tabela resumo do mês */}
                      {(agendaMes||[]).length > 0 && (
                        <div style={{ marginTop:12, overflowX:"auto" }}>
                          <table style={{ width:"100%", borderCollapse:"collapse", fontSize:11 }}>
                            <thead>
                              <tr style={{ color:"#6B7280", borderBottom:`1px solid ${"#EAEDF2"}` }}>
                                {["Data","Total","Executados","Cancelados","Abertos","Valor"].map(h => (
                                  <th key={h} style={{ padding:"6px 10px", fontWeight:700, textAlign: h==="Data"?"left":"right", fontSize:10 }}>{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {(agendaMes||[]).map((d,i) => (
                                <tr key={i} style={{ borderBottom:`1px solid ${"#EAEDF2"}`, cursor:"pointer" }}
                                  onClick={() => { setDiaSel(d.data); setView("dia"); setDataSel(d.data); }}
                                  onMouseEnter={e => e.currentTarget.style.background="#F2F2F2"}
                                  onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                                  <td style={{ padding:"7px 10px", color:"#111827", fontWeight:700 }}>
                                    {new Date(d.data+"T12:00:00").toLocaleDateString("pt-BR",{weekday:"short",day:"2-digit",month:"2-digit"})}
                                  </td>
                                  <td style={{ padding:"7px 10px", textAlign:"right", color:"#111827", fontWeight:700 }}>{d.total}</td>
                                  <td style={{ padding:"7px 10px", textAlign:"right", color:"#10B981" }}>{d.executados}</td>
                                  <td style={{ padding:"7px 10px", textAlign:"right", color:"#EF4444" }}>{d.cancelados}</td>
                                  <td style={{ padding:"7px 10px", textAlign:"right", color:"#8B1A1A" }}>{d.abertos}</td>
                                  <td style={{ padding:"7px 10px", textAlign:"right", color:"#F59E0B", fontWeight:700 }}>{brlFull(d.valor_total)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function SecaoAgendamentos({ periodo, modulo }) {
  const atendFiltro = modulo?.atendCodes?.length === 1 ? modulo.atendCodes[0] : "";
  const { data: resumo, loading: lR, error: eR } = useFetch("/api/agendamentos/resumo",     { periodo, atend: atendFiltro });
  const { data: semana, loading: lS }             = useFetch("/api/agendamentos/por-semana", { periodo, atend: atendFiltro });
  const [proximos, setProximos]                   = useState(null);
  const [loadingP, setLoadingP]                   = useState(true);

  useEffect(() => {
    fetch(`${API}/api/agendamentos/proximos?limite=10`)
      .then(r => r.json()).then(setProximos).finally(() => setLoadingP(false));
  }, []);

  const STATUS = { A:"Aberto", E:"Executado", C:"Cancelado", B:"Bloqueado" };
  const COR    = { A:"#8B1A1A", E:"#10B981", C:"#EF4444", B:"#F59E0B" };

  return (
    <>
      {eR && <Err msg={eR.message} />}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:16, marginBottom:16 }}>
        <KPI label="Total Agendado"  value={num(resumo?.total)}               loading={lR} accent={"#8B1A1A"} />
        <KPI label="Executados"      value={num(resumo?.realizados)}          loading={lR} accent={"#10B981"} deltaUp={true} />
        <KPI label="Cancelados"      value={num(resumo?.cancelados)}          loading={lR} accent={"#EF4444"}   deltaUp={false} />
        <KPI label="Taxa Execução"   value={pct(resumo?.taxa_comparecimento)} loading={lR}
          accent={resumo?.taxa_comparecimento >= 70 ? "#10B981" : "#EF4444"}
          deltaUp={resumo?.taxa_comparecimento >= 70}
          sub={resumo?.taxa_comparecimento >= 70 ? "Boa taxa" : "Abaixo de 70%"} />
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginBottom:16 }}>
        <Card title="Status por Semana" subtitle="Executado · Cancelado · Bloqueado">
          {lS ? <Skeleton h={220} /> : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={semana||[]} barSize={26}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
                <XAxis dataKey="semana" tickFormatter={v=>`Sem ${v}`} tick={{ fontSize:11, fill:"#64748B" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:11, fill:"#64748B" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CTip />} />
                <Legend iconSize={18} iconType="circle" wrapperStyle={{ fontSize:14, color:"#0F172A", fontWeight:700, paddingTop:8 }} />
                <Bar dataKey="realizados" fill={"#10B981"} name="Executado"  stackId="a" />
                <Bar dataKey="cancelados" fill={"#EF4444"}   name="Cancelado"  stackId="a" />
                <Bar dataKey="bloqueados" fill={"#F59E0B"} name="Bloqueado"  stackId="a" radius={[4,4,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Próximos Agendamentos" subtitle="Aguardando execução">
          {loadingP ? <Skeleton h={200} /> : (
            <div style={{ overflowY:"auto", maxHeight:220 }}>
              <table style={{ width:"100%", fontSize:12, borderCollapse:"collapse" }}>
                <thead style={{ position:"sticky", top:0, background: "#fff" }}>
                  <tr style={{ color:"#6B7280", borderBottom:`1px solid ${"#EAEDF2"}` }}>
                    {["Paciente","Médico","Data/Hora","Status"].map(h => (
                      <th key={h} style={{ padding:"6px 8px", fontWeight:700, textAlign:"left", fontSize:11 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(proximos||[]).map((r,i) => (
                    <tr key={i} style={{ borderBottom:`1px solid ${"#EAEDF2"}` }}
                      onMouseEnter={e => e.currentTarget.style.background="#F2F2F2"}
                      onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                      <td style={{ padding:"8px", color:"#111827", fontWeight:600 }}>{r.nom_paciente}</td>
                      <td style={{ padding:"8px", color:"#6B7280" }}>{r.medico_apelido||r.medico}</td>
                      <td style={{ padding:"8px", color:"#6B7280", whiteSpace:"nowrap" }}>
                        {r.data_hora ? new Date(r.data_hora).toLocaleString("pt-BR",{
                          day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"
                        }) : "—"}
                      </td>
                      <td style={{ padding:"8px" }}>
                        <span style={{
                          padding:"2px 10px", borderRadius:20, fontSize:11, fontWeight:700,
                          background: (COR[r.status]||"#6B7280") + "22",
                          color: COR[r.status]||"#6B7280",
                          border:`1px solid ${(COR[r.status]||"#6B7280")}55`,
                        }}>
                          {STATUS[r.status]||r.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <GraficoComparativoAnual
        titulo="Total de Agendamentos — Comparativo Anual" subtitulo="Mesmo período em anos anteriores"
        endpoint="/api/comparativo/agendamentos" deps={{ periodo }}
        dataKey="total" fmt={num} height={160}
      />

      <PainelAgendaMedico />
    </>
  );
}

// ── PACIENTES ─────────────────────────────────────────────────────────────────
const MESES_PT = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];

const periodoParaLabel = (periodo) => {
  const now = new Date();
  if (periodo === "hoje") return `Hoje (${now.toLocaleDateString("pt-BR")})`;
  if (periodo === "30d")  return `${MESES_PT[now.getMonth()]} de ${now.getFullYear()}`;
  if (periodo === "ano")  return `Ano ${now.getFullYear()}`;
  if (periodo?.startsWith?.("mes:")) {
    const [ano, mes] = periodo.slice(4).split("-");
    return `${MESES_PT[Number(mes)-1] || mes} de ${ano}`;
  }
  return periodo;
};

function PainelTopAtendimentos({ periodo }) {
  const anoAtual = new Date().getFullYear();
  const mesAtual = new Date().getMonth() + 1;

  // Modos: "tudo" = histórico completo, "periodo" = filtro global, "anual", "mensal", "custom"
  const [modo, setModo]         = useState("tudo");
  const [anoSel, setAnoSel]     = useState(anoAtual);
  const [mesSel, setMesSel]     = useState(mesAtual);
  const [dataIni, setDataIni]   = useState("");
  const [dataFim, setDataFim]   = useState("");
  const [aplicado, setAplicado] = useState({ ini: "", fim: "" });

  // Monta params conforme modo
  const params = (() => {
    if (modo === "tudo")    return { todo_periodo: true, limite: 15 };
    if (modo === "periodo") return { periodo, limite: 15 };
    if (modo === "anual")   return { inicio: `${anoSel}-01-01`, fim: `${anoSel}-12-31`, limite: 15 };
    if (modo === "mensal") {
      const ultimo = new Date(anoAtual, mesSel, 0).getDate();
      return { inicio: `${anoAtual}-${String(mesSel).padStart(2,"0")}-01`, fim: `${anoAtual}-${String(mesSel).padStart(2,"0")}-${ultimo}`, limite: 15 };
    }
    if (modo === "custom" && aplicado.ini && aplicado.fim)
      return { inicio: aplicado.ini, fim: aplicado.fim, limite: 15 };
    return { todo_periodo: true, limite: 15 };
  })();

  const { data, loading } = useFetch("/api/pacientes/top-atendimentos", params);

  const labelPeriodo = (() => {
    if (modo === "tudo")    return "Todo o histórico";
    if (modo === "periodo") return `Período do filtro (${periodo})`;
    if (modo === "anual")   return `Ano ${anoSel}`;
    if (modo === "mensal")  return `${MESES_PT[mesSel-1]} ${anoAtual}`;
    if (modo === "custom" && aplicado.ini) return `${aplicado.ini} → ${aplicado.fim}`;
    return "—";
  })();

  const modoBtn = (m, label) => (
    <button onClick={() => setModo(m)} style={{
      padding:"5px 12px", borderRadius:8, border:`1px solid ${modo===m ? "#8B1A1A" : "#EAEDF2"}`,
      background: modo===m ? "#8B1A1A" : '#fff',
      color: modo===m ? "#0F172A" : "#6B7280",
      fontSize:11, fontWeight:700, cursor:"pointer", transition:"all 0.15s", whiteSpace:"nowrap",
    }}>{label}</button>
  );

  return (
    <Card title="Top Pacientes por Atendimentos" subtitle={labelPeriodo}>
      {/* Filtros de modo */}
      <div style={{ display:"flex", flexWrap:"wrap", gap:6, marginBottom:12, alignItems:"center" }}>
        {modoBtn("tudo",    "Todo período")}
        {modoBtn("periodo", "Período global")}
        {modoBtn("anual",   "Anual")}
        {modoBtn("mensal",  "Mensal")}
        {modoBtn("custom",  "Personalizado")}
      </div>

      {/* Sub-controles por modo */}
      {modo === "anual" && (
        <div style={{ display:"flex", gap:6, marginBottom:12, alignItems:"center" }}>
          <span style={{ fontSize:11, color:"#6B7280", fontWeight:600 }}>Ano:</span>
          {[anoAtual-2, anoAtual-1, anoAtual].map(a => (
            <button key={a} onClick={() => setAnoSel(a)} style={{
              padding:"4px 10px", borderRadius:7, border:`1px solid ${anoSel===a ? "#8B5CF6" : "#EAEDF2"}`,
              background: anoSel===a ? "#8B5CF6" : '#F8FAFC',
              color: anoSel===a ? "#fff" : "#6B7280",
              fontSize:11, fontWeight:700, cursor:"pointer", transition:"all 0.15s",
            }}>{a}</button>
          ))}
        </div>
      )}

      {modo === "mensal" && (
        <div style={{ display:"flex", flexWrap:"wrap", gap:4, marginBottom:12 }}>
          {MESES_PT.map((m, i) => (
            <button key={i+1} onClick={() => setMesSel(i+1)} style={{
              padding:"4px 9px", borderRadius:7, border:`1px solid ${mesSel===i+1 ? "#8B5CF6" : "#EAEDF2"}`,
              background: mesSel===i+1 ? "#8B5CF6" : '#F8FAFC',
              color: mesSel===i+1 ? "#fff" : "#6B7280",
              fontSize:11, fontWeight:700, cursor:"pointer", transition:"all 0.15s",
            }}>{m.slice(0,3)}</button>
          ))}
        </div>
      )}

      {modo === "custom" && (
        <div style={{ display:"flex", gap:8, marginBottom:12, alignItems:"center", flexWrap:"wrap" }}>
          <div style={{ display:"flex", alignItems:"center", gap:6 }}>
            <span style={{ fontSize:11, color:"#6B7280", fontWeight:600 }}>De:</span>
            <input type="date" value={dataIni} onChange={e => setDataIni(e.target.value)} style={{
              padding:"5px 8px", borderRadius:7, border:`1px solid ${"#EAEDF2"}`,
              background:"#EEEEEE", color:"#111827", fontSize:11, outline:"none",
            }} />
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:6 }}>
            <span style={{ fontSize:11, color:"#6B7280", fontWeight:600 }}>Até:</span>
            <input type="date" value={dataFim} onChange={e => setDataFim(e.target.value)} style={{
              padding:"5px 8px", borderRadius:7, border:`1px solid ${"#EAEDF2"}`,
              background:"#EEEEEE", color:"#111827", fontSize:11, outline:"none",
            }} />
          </div>
          <button onClick={() => setAplicado({ ini: dataIni, fim: dataFim })}
            disabled={!dataIni || !dataFim}
            style={{
              padding:"5px 14px", borderRadius:7, border:"none", cursor: dataIni&&dataFim ? "pointer" : "not-allowed",
              background: dataIni&&dataFim ? "#10B981" : "#EAEDF2",
              color: dataIni&&dataFim ? "#0F172A" : "#6B7280",
              fontSize:11, fontWeight:700, transition:"all 0.15s",
            }}>Aplicar</button>
        </div>
      )}

      {/* Tabela */}
      {loading ? <Skeleton h={280} /> : (
        <div style={{ overflowY:"auto", maxHeight:300 }}>
          <table style={{ width:"100%", fontSize:12, borderCollapse:"collapse" }}>
            <thead style={{ position:"sticky", top:0, background:"#fff" }}>
              <tr style={{ color:"#6B7280", borderBottom:`1px solid ${"#EAEDF2"}` }}>
                {["#","Paciente","Idade","Sexo","Convênio","Atend.","Último atend."].map(h => (
                  <th key={h} style={{ padding:"8px 10px", fontWeight:700, textAlign: h==="Atend." ? "right" : "left", fontSize:11, whiteSpace:"nowrap" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data||[]).length === 0 ? (
                <tr><td colSpan={7} style={{ padding:"24px", textAlign:"center", color:"#6B7280", fontSize:12 }}>Nenhum dado encontrado</td></tr>
              ) : (data||[]).map((r,i) => (
                <tr key={i} style={{ borderBottom:`1px solid ${"#EAEDF2"}`, transition:"background 0.1s" }}
                  onMouseEnter={e => e.currentTarget.style.background="#F2F2F2"}
                  onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                  <td style={{ padding:"9px 10px", color:"#6B7280", fontWeight:700, fontSize:11 }}>{i+1}</td>
                  <td style={{ padding:"9px 10px", color:"#111827", fontWeight:700, maxWidth:180, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{r.nome}</td>
                  <td style={{ padding:"9px 10px", color:"#6B7280" }}>{r.idade ? `${r.idade}a` : "—"}</td>
                  <td style={{ padding:"9px 10px" }}>
                    <span style={{
                      padding:"2px 8px", borderRadius:12, fontSize:11, fontWeight:700,
                      background: r.sexo==="M" ? "#8B1A1A"+"22" : "#EF4444"+"22",
                      color: r.sexo==="M" ? "#8B1A1A" : "#EF4444",
                    }}>{r.sexo==="M"?"M":"F"}</span>
                  </td>
                  <td style={{ padding:"9px 10px", color:"#6B7280", fontSize:11, maxWidth:100, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{r.convenio||"—"}</td>
                  <td style={{ padding:"9px 10px", color:"#F59E0B", fontWeight:800, textAlign:"right", fontSize:15 }}>{r.total_atendimentos}</td>
                  <td style={{ padding:"9px 10px", color:"#6B7280", fontSize:11, whiteSpace:"nowrap" }}>
                    {r.ultimo_atendimento ? new Date(r.ultimo_atendimento).toLocaleDateString("pt-BR") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function PainelAniversariantes() {
  const mesAtual = new Date().getMonth() + 1;
  const [mes, setMes] = useState(mesAtual);
  const [busca, setBusca] = useState("");
  const { data, loading } = useFetch("/api/pacientes/aniversariantes", { mes });

  const filtrados = (data||[]).filter(r =>
    !busca || r.nome?.toLowerCase().includes(busca.toLowerCase())
  );

  const hoje = new Date().getDate();

  return (
    <Card title="Aniversariantes" subtitle="Filtre por mês e pesquise por nome">
      {/* Seletor de mês */}
      <div style={{ display:"flex", flexWrap:"wrap", gap:4, marginBottom:14 }}>
        {MESES_PT.map((m, i) => (
          <button key={i+1} onClick={() => setMes(i+1)} style={{
            padding:"5px 10px", borderRadius:8, border:`1px solid ${mes===i+1 ? "#8B1A1A" : "#EAEDF2"}`,
            background: mes===i+1 ? "#8B1A1A" : '#F8FAFC',
            color: mes===i+1 ? "#0F172A" : "#6B7280",
            fontSize:11, fontWeight:700, cursor:"pointer", transition:"all 0.15s",
          }}>{m.slice(0,3)}</button>
        ))}
      </div>

      {/* Busca */}
      <div style={{ marginBottom:12 }}>
        <input
          placeholder="Buscar paciente..."
          value={busca}
          onChange={e => setBusca(e.target.value)}
          style={{
            width:"100%", padding:"8px 12px", borderRadius:8,
            border:`1px solid ${"#EAEDF2"}`, background:"#EEEEEE",
            color:"#111827", fontSize:12, outline:"none",
          }}
        />
      </div>

      {/* Contador */}
      {!loading && (
        <div style={{ fontSize:12, color:"#6B7280", marginBottom:10 }}>
          <span style={{ color:"#8B1A1A", fontWeight:700 }}>{filtrados.length}</span> aniversariante{filtrados.length !== 1 ? "s" : ""} em <span style={{ color:"#111827", fontWeight:600 }}>{MESES_PT[mes-1]}</span>
        </div>
      )}

      {loading ? <Skeleton h={280} /> : (
        <div style={{ overflowY:"auto", maxHeight:300 }}>
          <table style={{ width:"100%", fontSize:12, borderCollapse:"collapse" }}>
            <thead style={{ position:"sticky", top:0, background:"#fff" }}>
              <tr style={{ color:"#6B7280", borderBottom:`1px solid ${"#EAEDF2"}` }}>
                {["Dia","Paciente","Idade","Sexo","Último atend."].map(h => (
                  <th key={h} style={{ padding:"7px 10px", fontWeight:700, textAlign:"left", fontSize:11 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtrados.length === 0 ? (
                <tr><td colSpan={5} style={{ padding:"24px", textAlign:"center", color:"#6B7280", fontSize:12 }}>Nenhum aniversariante encontrado</td></tr>
              ) : filtrados.map((r,i) => {
                const ehHoje = mes === mesAtual && r.dia === hoje;
                return (
                  <tr key={i} style={{
                    borderBottom:`1px solid ${"#EAEDF2"}`,
                    background: ehHoje ? "#ECFDF5" : "transparent",
                    transition:"background 0.1s",
                  }}
                    onMouseEnter={e => { if(!ehHoje) e.currentTarget.style.background="#F2F2F2"; }}
                    onMouseLeave={e => { if(!ehHoje) e.currentTarget.style.background="transparent"; }}>
                    <td style={{ padding:"9px 10px" }}>
                      <span style={{
                        display:"inline-flex", alignItems:"center", justifyContent:"center",
                        width:28, height:28, borderRadius:"50%", fontWeight:800, fontSize:12,
                        background: ehHoje ? "#10B981"+"33" : "#EAEDF2",
                        color: ehHoje ? "#10B981" : "#111827",
                        border: ehHoje ? `1px solid ${"#10B981"}` : "none",
                      }}>{r.dia}</span>
                    </td>
                    <td style={{ padding:"9px 10px", color:"#111827", fontWeight: ehHoje ? 700 : 400, maxWidth:220, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                      {ehHoje && <span style={{ marginRight:6, fontSize:13 }}>🎂</span>}
                      {r.nome}
                    </td>
                    <td style={{ padding:"9px 10px", color:"#6B7280" }}>{r.idade ? `${r.idade} anos` : "—"}</td>
                    <td style={{ padding:"9px 10px" }}>
                      <span style={{
                        padding:"2px 8px", borderRadius:12, fontSize:11, fontWeight:700,
                        background: r.sexo==="M" ? "#8B1A1A"+"22" : "#EF4444"+"22",
                        color: r.sexo==="M" ? "#8B1A1A" : "#EF4444",
                      }}>{r.sexo==="M"?"M":"F"}</span>
                    </td>
                    <td style={{ padding:"9px 10px", color:"#6B7280", fontSize:11 }}>
                      {r.ultimo_atendimento || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function SecaoPacientes({ periodo, modulo }) {
  const atendFiltro = modulo?.atendCodes?.length === 1 ? modulo.atendCodes[0] : "";
  const { data: resumo, loading: lR, error: eR } = useFetch("/api/pacientes/resumo",           { periodo, atend: atendFiltro });
  const { data: novos,  loading: lN }             = useFetch("/api/pacientes/novos-por-semana", { periodo });
  const { data: faixa,  loading: lF }             = useFetch("/api/pacientes/faixa-etaria",    { periodo });
  const { data: sexo,   loading: lS }             = useFetch("/api/pacientes/por-sexo",        { periodo });
  const { data: conv,   loading: lC }             = useFetch("/api/pacientes/por-convenio",    { periodo });

  return (
    <>
      {eR && <Err msg={eR.message} />}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:16, marginBottom:16 }}>
        <KPI label="Atendidos"       value={num(resumo?.pacientes_atendidos)} loading={lR} accent={"#8B1A1A"} />
        <KPI label="Novos Cadastros" value={num(resumo?.novos_cadastros)}     loading={lR} accent={"#10B981"} deltaUp={true} />
        <KPI label="Retorno"         value={num(resumo?.retorno)}             loading={lR} accent={"#6B2525"} deltaUp={true} sub="mais de 1 atend." />
        <KPI label="Base Total"      value={num(resumo?.total_base)}          loading={lR} accent={"#F59E0B"} />
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginBottom:16 }}>
        <Card title="Novos Pacientes por Semana" subtitle="Cadastros no período">
          {lN ? <Skeleton /> : (
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={novos||[]}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
                <XAxis dataKey="semana" tickFormatter={v=>`Sem ${v}`} tick={{ fontSize:11, fill:"#64748B" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:11, fill:"#64748B" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CTip />} />
                <Line type="monotone" dataKey="novos" stroke={"#EF4444"} strokeWidth={2.5}
                  dot={{ r:3, fill:"#EF4444", strokeWidth:0 }} name="Novos" />
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Faixa Etária" subtitle="Pacientes atendidos">
          {lF ? <Skeleton /> : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={faixa||[]} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false} />
                <XAxis dataKey="faixa" tick={{ fontSize:11, fill:"#64748B" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize:11, fill:"#64748B" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CTip />} />
                <Bar dataKey="qtd" radius={[4,4,0,0]} name="Pacientes">
                  {(faixa||[]).map((_,i) => <Cell key={i} fill={CORES_ESP[i%CORES_ESP.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Por Sexo" subtitle="Distribuição de pacientes">
          {lS ? <Skeleton h={180} /> : (
            <ResponsiveContainer width="100%" height={180}>
              <PieChart>
                <Pie data={sexo||[]} dataKey="qtd" nameKey="sexo"
                  cx="50%" cy="50%" outerRadius={70} innerRadius={42} paddingAngle={3}
                  label={({sexo,percent}) => `${sexo} ${(percent*100).toFixed(0)}%`}
                  labelLine={false} style={{ fontSize:11, fill:"#64748B" }}>
                  {(sexo||[]).map((_,i) => <Cell key={i} fill={["#8B1A1A","#EF4444","#6B7280"][i]} />)}
                </Pie>
                <Tooltip content={<CTip />} />
              </PieChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card title="Por Convênio" subtitle="Top convênios">
          {lC ? <Skeleton h={180} /> : (
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={(conv||[]).slice(0,5)} layout="vertical" barSize={13}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" horizontal={false} />
                <XAxis type="number" tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false} />
                <YAxis dataKey="nom_convenio" type="category" width={85} tick={{ fontSize:10, fill:"#64748B" }} axisLine={false} tickLine={false} />
                <Tooltip content={<CTip />} />
                <Bar dataKey="qtd_pacientes" radius={[0,4,4,0]} name="Pacientes">
                  {(conv||[]).slice(0,5).map((_,i) => <Cell key={i} fill={CORES_ESP[i%CORES_ESP.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <GraficoComparativoAnual
        titulo="Pacientes Atendidos — Comparativo Anual" subtitulo="Mesmo período em anos anteriores"
        endpoint="/api/comparativo/pacientes" deps={{ periodo }}
        dataKey="pacientes_atendidos" fmt={num} height={160}
      />

      {/* Top pacientes + Aniversariantes */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginTop:12 }}>
        <PainelTopAtendimentos periodo={periodo} />
        <PainelAniversariantes />
      </div>
    </>
  );
}

// ── APP ───────────────────────────────────────────────────────────────────────
// ── MÓDULOS E FILTRO GLOBAL ──────────────────────────────────────────────────
const ABAS = [
  { id:"financeiro",   label:"Produção"   },  // financeiro + produção
  { id:"operacional",  label:"Operacional"  },  // atendimentos + agendamentos
  { id:"pacientes",    label:"Pacientes"    },
];

const MODULOS = [
  { id: "",            label: "Todos",            desc: "Visão geral",                          icon:"⊞",  atendCodes: [],                                    setores: [],                                                color: "#2196F3" },
  { id: "assistencial",label: "Assistencial",     desc: "Consultas e atendimentos clínicos",    icon:"🩺", atendCodes: ["ASS"],                               setores: ["CSM","PED","GIN","ORT","NUT","PSQ","URO","END","DER","REU","4B ","4A ","TO "], color: "#2196F3" },
  { id: "med_ocup",    label: "Med. Ocupacional", desc: "Admissional, Periódico, Demissional",  icon:"🏭", atendCodes: ["ADM","PER","DEM","RTB","MDF","MOC"], setores: ["EXA","13 ","1H ","PCM"],                          color: "#E69F00" },
  { id: "laboratorio", label: "Laboratório",      desc: "Exames laboratoriais e de imagem",     icon:"🔬", atendCodes: [],                                    setores: ["LAB","RAD","USG","CAR","PNE","FON","OFT","NEU","PSI","ACV"], color: "#009E73" },
  { id: "agendamentos",label: "Agendamentos",     desc: "Agenda médica e indicadores",          icon:"📅", atendCodes: [],                                    setores: [],                                                color: "#CC79A7" },
];
const PERIODOS = [
  { value:"7d",  label:"7 dias"  },
  { value:"30d", label:"Mês atual" },
  { value:"90d", label:"90 dias" },
];

// ── ÍCONES SVG MODERNOS ──────────────────────────────────────────────────────
// ── ÍCONES SVG ────────────────────────────────────────────────────────────────
/* ─── DESIGN SYSTEM ──────────────────────────────────────────────────────── */
const C = {
  bg:        "#F7F8FA",
  sidebar:   "#FFFFFF",
  card:      "#FFFFFF",
  topbar:    "#FFFFFF",
  border:    "#EAEDF2",
  text:      "#111827",
  sub:       "#6B7280",
  faint:     "#9CA3AF",
  blue:      "#8B1A1A",
  blueLight: "#FDF2F2",
  green:     "#10B981",
  greenLight:"#D1FAE5",
  amber:     "#F59E0B",
  amberLight:"#FEF3C7",
  red:       "#EF4444",
  redLight:  "#FEE2E2",
  purple:    "#8B5CF6",
  purpleLight:"#EDE9FE",
  shadow:    "0 1px 4px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.04)",
};

/* ─── ICONS ──────────────────────────────────────────────────────────────── */
const IconStethoscope = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="9" cy="6" r="3"/>
    <path d="M9 9 Q9 15 14 17 Q19 19 19 14"/>
    <circle cx="19" cy="13" r="2" fill={color} stroke="none"/>
    <line x1="7" y1="3" x2="7" y2="5"/>
    <line x1="11" y1="3" x2="11" y2="5"/>
  </svg>
);

const IconBrain = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 20 Q10 20 9 18 Q5 18 3 14 Q1 10 3 6 Q5 2 9 3 Q10 1 12 1"/>
    <path d="M12 20 Q14 20 15 18 Q19 18 21 14 Q23 10 21 6 Q19 2 15 3 Q14 1 12 1"/>
    <line x1="12" y1="1" x2="12" y2="20" strokeDasharray="2 2" strokeWidth="1.2"/>
    <path d="M5 10 Q8 8 11 10" strokeWidth="1.3"/>
    <path d="M5 14 Q8 12 11 14" strokeWidth="1.3"/>
    <path d="M13 10 Q16 8 19 10" strokeWidth="1.3"/>
    <path d="M13 14 Q16 12 19 14" strokeWidth="1.3"/>
    <path d="M11 20 Q11 22 12 22 Q13 22 13 20" strokeWidth="1.5"/>
  </svg>
);

const IconHardhat = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 14h20"/>
    <path d="M4 14 Q4 8 12 6 Q20 8 20 14"/>
    <path d="M8 14 Q8 10 12 9 Q16 10 16 14"/>
    <rect x="2" y="14" width="20" height="3" rx="1.5"/>
  </svg>
);

const IconMicroscope = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M6 18h12"/>
    <path d="M9 18 Q9 14 11 12"/>
    <rect x="9" y="4" width="6" height="8" rx="2"/>
    <line x1="12" y1="4" x2="12" y2="2"/>
    <circle cx="12" cy="2" r="1.2" fill={color} stroke="none"/>
    <path d="M15 8 Q18 8 18 12 Q18 16 15 16"/>
  </svg>
);

const IconCalendarClock = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="12" height="13" rx="2"/>
    <line x1="7" y1="2" x2="7" y2="6"/>
    <line x1="11" y1="2" x2="11" y2="6"/>
    <line x1="3" y1="9" x2="15" y2="9"/>
    <circle cx="18" cy="17" r="4"/>
    <polyline points="18 15 18 17 20 17"/>
  </svg>
);

const IconMoneyTrend = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 17 8 12 12 15 20 6"/>
    <polyline points="16 6 20 6 20 10"/>
    <circle cx="10" cy="19" r="2.5"/>
    <line x1="10" y1="16.5" x2="10" y2="21.5"/>
    <line x1="7.5" y1="19" x2="12.5" y2="19"/>
  </svg>
);

const IconBox = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M12 2L2 7l10 5 10-5-10-5z"/>
    <path d="M2 17l10 5 10-5"/>
    <path d="M2 12l10 5 10-5"/>
    <line x1="12" y1="7" x2="12" y2="22"/>
  </svg>
);

const IconMonitor = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="3" width="20" height="14" rx="2"/>
    <polyline points="8 21 12 17 16 21"/>
    <line x1="12" y1="17" x2="12" y2="21"/>
    <polyline points="6 10 9 10 11 7 13 13 15 10 17 10" strokeWidth="1.5"/>
  </svg>
);

const Icon = ({ name, size=18, color="currentColor" }) => {
  if (name === "layers")        return <IconLayers        size={size} color={color}/>;
  if (name === "users")         return <IconUsers         size={size} color={color}/>;
  if (name === "stethoscope")   return <IconStethoscope   size={size} color={color}/>;
  if (name === "brain")         return <IconBrain         size={size} color={color}/>;
  if (name === "hardhat")       return <IconHardhat       size={size} color={color}/>;
  if (name === "microscope")    return <IconMicroscope    size={size} color={color}/>;
  if (name === "calendar-clock")return <IconCalendarClock size={size} color={color}/>;
  if (name === "money-trend")   return <IconMoneyTrend    size={size} color={color}/>;
  if (name === "box")           return <IconBox           size={size} color={color}/>;
  if (name === "monitor")       return <IconMonitor       size={size} color={color}/>;
  if (name === "home")          return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>;
  const p = {
    dollar:    "M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6",
    trending:  "M23 6l-9.5 9.5-5-5L1 18M17 6h6v6",
    bar:       "M18 20V10M12 20V4M6 20v-6",
    pulse:     "M22 12h-4l-3 9L9 3l-3 9H2",
    calendar:  "M3 4h18v16a1 1 0 01-1 1H4a1 1 0 01-1-1V4zM16 2v4M8 2v4M3 10h18",
    users:     "M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2M9 7a4 4 0 100 8 4 4 0 000-8zM23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75",
    layers:    "M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",
    package:   "M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16zM3.27 6.96L12 12.01l8.73-5.05M12 22.08V12",
    flask:     "M6 2v6l-4 10a2 2 0 001.9 2.7h12.2A2 2 0 0018 18L14 8V2M6 2h8M9 12h6",
    factory:   "M2 20a2 2 0 002 2h16a2 2 0 002-2V8l-7 5V8l-7 5V4a2 2 0 00-2-2H4a2 2 0 00-2 2z",
    heart:     "M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z",
    grid:      "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
    settings:  "M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z",
    check:     "M20 6L9 17l-5-5",
    wifi:      "M5 12.55a11 11 0 0114.08 0M1.42 9a16 16 0 0121.16 0M8.53 16.11a6 6 0 016.95 0M12 20h.01",
    activity:  "M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01",
    document:  "M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M8 13h8M8 17h8M8 9h1",
    clock:     "M12 22a10 10 0 100-20 10 10 0 000 20zM12 6v6l4 2",
  };
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      {(p[name]||"").split("M").filter(Boolean).map((d,i) => <path key={i} d={"M"+d}/>)}
    </svg>
  );
};

/* ─── CONFIG ─────────────────────────────────────────────────────────────── */
// ══════════════════════════════════════════════════════════════════════════════
// COMPONENTES DE MÓDULO
// ══════════════════════════════════════════════════════════════════════════════

function ModuloCard({ label, value, sub, color, loading, icon }) {
  return (
    <div style={{
      background: `linear-gradient(135deg, ${color}3A 0%, ${color}14 100%)`,
      borderRadius: 16, padding: "18px 20px",
      border: `1.5px solid ${color}55`,
      boxShadow: `0 6px 18px ${color}22, 0 1px 4px rgba(0,0,0,0.05)`,
      display: "flex", flexDirection: "column", gap: 10,
      position: "relative", overflow: "hidden",
    }}>
      <div style={{ position:"absolute", right:-14, top:-14, width:80, height:80, borderRadius:"50%", background:`${color}20`, pointerEvents:"none" }}/>
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between" }}>
        {icon && (
          <div style={{
            width:38, height:38, borderRadius:11,
            background: color,
            display:"flex", alignItems:"center", justifyContent:"center",
            boxShadow: `0 4px 12px ${color}60`,
          }}>
            <Icon name={icon} size={18} color="#fff"/>
          </div>
        )}
      </div>
      {loading
        ? <div style={{ height:32, width:"60%", background:`${color}30`, borderRadius:7, animation:"pulse 1.5s infinite" }}/>
        : <div style={{ fontSize:fitFontSize(value,26,14), fontWeight:900, color:"#111827", lineHeight:1.15, letterSpacing:"-0.5px", overflowWrap:"anywhere" }}>{value}</div>
      }
      <div>
        <span style={{ fontSize:10, color:color, fontWeight:800, textTransform:"uppercase", letterSpacing:"0.08em" }}>{label}</span>
        {sub && <div style={{ fontSize:11, color:"#fff", fontWeight:700, marginTop:3, background:color, borderRadius:5, padding:"2px 7px", display:"inline-block" }}>{sub}</div>}
      </div>
    </div>
  );
}

function ConvenioBar({ data }) {
  const max = data?.[0]?.valor || data?.[0]?.faturamento || 1;
  const fmt = v => new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v||0);
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
      {(data||[]).slice(0,8).map((item,i) => {
        const cor = CORES_ESP[i%CORES_ESP.length];
        const val = item.valor || item.faturamento || 0;
        const largPct = Math.max(4, (val/max)*100);
        return (
          <div key={i} style={{ display:"flex", alignItems:"center", gap:12 }}>
            <div style={{ width:28, height:28, borderRadius:8, background:`${cor}18`, border:`1.5px solid ${cor}30`,
              display:"flex", alignItems:"center", justifyContent:"center",
              fontSize:11, fontWeight:900, color:cor, flexShrink:0 }}>{i+1}</div>
            <div style={{ flex:1, minWidth:0 }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:4 }}>
                <span style={{ fontSize:12, color:"#111827", fontWeight:600, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", maxWidth:"58%" }}>{item.convenio||item.empresa||"—"}</span>
                <span style={{ fontSize:12, color:cor, fontWeight:800, flexShrink:0 }}>{fmt(val)}</span>
              </div>
              <div style={{ height:6, background:"#F1F5F9", borderRadius:4, overflow:"hidden" }}>
                <div style={{ height:"100%", borderRadius:4,
                  background:`linear-gradient(90deg, ${cor}70, ${cor})`,
                  width:`${largPct}%`, transition:"width 0.8s ease" }}/>
              </div>
              <div style={{ fontSize:10, color:"#94A3B8", marginTop:2 }}>{(item.qtd_os||item.total||0).toLocaleString("pt-BR")} OSs</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function LinhaChart({ data, dataKey="valor", color="#8B1A1A", height=180 }) {
  const gradId = `lg_${color.replace("#","")}`;
  const fmt = v => `R$${(v/1000).toFixed(0)}k`;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data||[]} margin={{top:4,right:8,bottom:0,left:0}}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={color} stopOpacity={0.35}/>
            <stop offset="100%" stopColor={color} stopOpacity={0.02}/>
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false}/>
        <XAxis dataKey="data" tick={{fontSize:10,fill:"#94A3B8"}} axisLine={false} tickLine={false}
          tickFormatter={v=>v?.slice(5)}/>
        <YAxis tickFormatter={fmt} tick={{fontSize:10,fill:"#94A3B8"}} axisLine={false} tickLine={false} width={52}/>
        <Tooltip content={<CTip fmt={v=>new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v)}/>}
          cursor={{stroke:color,strokeWidth:1,strokeDasharray:"3 3"}}/>
        <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2.5}
          fill={`url(#${gradId})`} dot={false} activeDot={{r:5,fill:color,strokeWidth:2,stroke:"#fff"}} name="Produção"/>
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function BarChart2({ data, dataKey="qtd_os", color="#8B1A1A", height=180 }) {
  const gradId = `bg_${color.replace("#","")}`;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data||[]} barSize={18} margin={{top:4,right:8,bottom:0,left:0}}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%"   stopColor={color} stopOpacity={0.9}/>
            <stop offset="100%" stopColor={color} stopOpacity={0.4}/>
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false}/>
        <XAxis dataKey="data" tick={{fontSize:10,fill:"#94A3B8"}} axisLine={false} tickLine={false}
          tickFormatter={v=>v?.slice(5)}/>
        <YAxis tick={{fontSize:10,fill:"#94A3B8"}} axisLine={false} tickLine={false} width={36}/>
        <Tooltip content={<CTip/>} cursor={{fill:`${color}10`}}/>
        <Bar dataKey={dataKey} fill={`url(#${gradId})`} radius={[6,6,0,0]} name="OSs"/>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ── MÓDULO ASSISTENCIAL ───────────────────────────────────────────────────────
function EspBar({ dados, label, cor, brl, num, periodo, atend }) {
  // dados tem campo esp_cod (ex: "CLI") e especialidade (ex: "Clínica Geral")
  const [espSel, setEspSel] = useState(null);
  const [medicos, setMedicos] = useState([]);
  const [loadMed, setLoadMed] = useState(false);

  const handleClick = async (d) => {
    const key = d.especialidade;
    if (espSel === key) { setEspSel(null); setMedicos([]); return; }
    setEspSel(key);
    setLoadMed(true);
    try {
      // Usa esp_cod se disponível, senão usa o nome
      const cod = d.esp_cod || d.especialidade;
      const r = await fetch(`/api/modulo/assistencial/medicos-por-especialidade?periodo=${periodo||"30d"}&especialidade=${encodeURIComponent(cod)}&atend=${atend||"ASS"}`);
      const j = await r.json();
      setMedicos(j || []);
    } catch(e) { setMedicos([]); }
    setLoadMed(false);
  };

  if (!dados?.length) return <div style={{ color:"#9CA3AF", fontSize:13, padding:"20px 0", textAlign:"center" }}>Sem dados</div>;
  const maxV = dados[0]?.valor || 1;
  return (
    <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
      {dados.map((d,i) => (
        <div key={i}>
          <div
            onClick={() => handleClick(d)}
            style={{ display:"flex", justifyContent:"space-between", marginBottom:4, alignItems:"center",
              cursor:"pointer", padding:"4px 6px", borderRadius:8, transition:"background 0.1s",
              background: espSel===d.especialidade ? cor+"12" : "transparent",
            }}
            onMouseEnter={e=>e.currentTarget.style.background=cor+"10"}
            onMouseLeave={e=>e.currentTarget.style.background=espSel===d.especialidade?cor+"12":"transparent"}
          >
            <span style={{ fontSize:13, fontWeight:600, color:"#111827", display:"flex", alignItems:"center", gap:6 }}>
              <span style={{ fontSize:10, color:cor }}>{espSel===d.especialidade?"▼":"▶"}</span>
              {d.especialidade}
            </span>
            <div style={{ textAlign:"right" }}>
              <span style={{ fontSize:13, fontWeight:700, color:cor }}>{brl(d.valor)}</span>
              <span style={{ fontSize:11, color:"#9CA3AF", marginLeft:8 }}>{num(d.qtd)} guias · {num(d.pacientes)} pac.</span>
            </div>
          </div>
          <div style={{ height:7, background:"#EEEEEE", borderRadius:4, overflow:"hidden", marginBottom: espSel===d.especialidade?8:0 }}>
            <div style={{ height:"100%", width:`${Math.max(3,(d.valor/maxV)*100)}%`, background:cor, borderRadius:4 }}/>
          </div>

          {/* Drawer de médicos */}
          {espSel===d.especialidade && (
            <div style={{ background:cor+"08", borderRadius:10, padding:"10px 12px",
              border:`1px solid ${cor}20`, marginBottom:4 }}>
              {loadMed ? (
                <div style={{ fontSize:12, color:"#9CA3AF", textAlign:"center", padding:"8px 0" }}>Carregando...</div>
              ) : medicos.length === 0 ? (
                <div style={{ fontSize:12, color:"#9CA3AF", textAlign:"center", padding:"8px 0" }}>Sem médicos encontrados</div>
              ) : (
                <div style={{ display:"flex", flexDirection:"column", gap:6 }}>
                  <div style={{ fontSize:10, color:cor, fontWeight:800, textTransform:"uppercase",
                    letterSpacing:"0.07em", marginBottom:4 }}>Médicos — {d.especialidade}</div>
                  {medicos.map((m,j) => (
                    <div key={j} style={{ display:"flex", justifyContent:"space-between", alignItems:"center",
                      padding:"5px 8px", background:"#fff", borderRadius:7, border:"1px solid #EEEEEE" }}>
                      <div>
                        <div style={{ fontSize:12, fontWeight:700, color:"#2D1B1B" }}>{m.medico}</div>
                        <div style={{ fontSize:10, color:"#9CA3AF" }}>{num(m.qtd)} guias · {num(m.pacientes)} pac.</div>
                      </div>
                      <div style={{ textAlign:"right" }}>
                        <div style={{ fontSize:13, fontWeight:700, color:cor }}>{brl(m.valor)}</div>
                        <div style={{ fontSize:10, color:"#9CA3AF" }}>
                          {m.qtd > 0 ? `Tick: ${brl(m.valor/m.qtd)}` : ""}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function SecaoModuloAssistencial({ periodo }) {
  const { data, loading, error } = useFetch("/api/modulo/assistencial/resumo", { periodo });
  const fin = data?.financeiro || {};
  const op  = data?.operacional || {};
  const v   = data?.variacoes || {};
  const brl = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";
  const brlK = v => v != null ? `R$${(Number(v)/1000).toFixed(0)}k` : "—";
  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";

  return (
    <div style={{ animation:"fadeIn 0.35s ease" }}>
      {error && <Err msg={error.message}/>}

      <ModuleHero
        title="Módulo Assistencial"
        subtitle={`Período: ${periodoParaLabel(periodo)}`}
        cor="#8B1A1A"
        loading={loading}
        stats={[
          { label:"Guias Abertas",      value: num(fin.total_os),        sub: `${num(fin.pacientes_unicos)} pac.`, trend: v.total_os },
          { label:"Produção Líquida",   value: brlK(fin.faturamento),    sub: `Ticket: ${brl(fin.ticket_medio)}`, trend: v.faturamento },
          { label:"Pend. Faturamento",  value: brlK(fin.val_aberto),     sub: "guias não faturadas" },
          { label:"Atendimentos",       value: num((op.consultas_medicas||0) + (op.equipe_mult||0) + (op.exames_diag||0)), sub: "consultas + serviços + exames" },
        ]}
      />

      <MetaModulo modulo="assistencial" cor="#8B1A1A" atual={fin.faturamento} periodo={periodo}/>

      <BriefingCard
        cor="#8B1A1A"
        cacheKey={`briefing_assistencial_${periodoParaLabel(periodo)}`}
        disabled={loading}
        promptFn={() => `Você é um analista de gestão clínica. Gere um briefing executivo em no máximo 4 frases, direto e profissional, sem markdown.

DADOS — Módulo Assistencial (período: ${periodoParaLabel(periodo)}):
- Total de guias: ${fin.total_os ?? "n/d"}
- Pacientes atendidos: ${fin.pacientes_unicos ?? "n/d"}
- Produção financeira: ${brl(fin.faturamento)}
- Ticket médio por paciente: ${fin.faturamento > 0 && fin.pacientes_unicos > 0 ? brl(fin.faturamento / fin.pacientes_unicos) : "n/d"}
- Total de atendimentos (consultas + serviços + exames): ${((op.consultas_medicas||0) + (op.equipe_mult||0) + (op.exames_diag||0)) || "n/d"}

Destaque desempenho, alertas de queda e sugestões para aumentar a produção assistencial.`}
      />

      {/* KPIs linha 1 */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:14, marginBottom:12 }}>
        <ModuloCard label="Total Guias"         value={num(fin.total_os)}           color="#8B1A1A" loading={loading} icon="bar"/>
        <ModuloCard label="Pacientes Atendidos" value={num(fin.pacientes_unicos)}   color="#8B5CF6" loading={loading} icon="users"
          sub={fin.faturamento > 0 && fin.pacientes_unicos > 0
            ? `Ticket/pac: ${brl(fin.faturamento / fin.pacientes_unicos)}`
            : null}/>
        {/* Card Produção com cálculo detalhado */}
        <div style={{
          background: "linear-gradient(135deg, #10B9813A 0%, #10B98114 100%)",
          borderRadius: 16, padding: "18px 20px",
          border: "1.5px solid #10B98155",
          boxShadow: "0 6px 18px #10B98122, 0 1px 4px rgba(0,0,0,0.05)",
          display: "flex", flexDirection: "column", gap: 6,
          position: "relative", overflow: "hidden",
        }}>
          <div style={{ position:"absolute", right:-14, top:-14, width:80, height:80, borderRadius:"50%", background:"#10B98120", pointerEvents:"none" }}/>
          <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:2 }}>
            <div style={{
              width:38, height:38, borderRadius:11, background:"#10B981",
              display:"flex", alignItems:"center", justifyContent:"center",
              boxShadow:"0 4px 12px #10B98160",
            }}>
              <Icon name="dollar" size={18} color="#fff"/>
            </div>
          </div>
          {loading ? <Skeleton h={32}/> : (
            <div style={{ fontSize:fitFontSize(brl(fin.faturamento),26,14), fontWeight:900, color:"#111827", lineHeight:1.15, letterSpacing:"-0.5px", overflowWrap:"anywhere" }}>
              {brl(fin.faturamento)}
            </div>
          )}
          <span style={{ fontSize:10, color:"#10B981", fontWeight:800, textTransform:"uppercase", letterSpacing:"0.08em" }}>Produção</span>
          {/* Cálculo */}
          {!loading && fin.valor_bruto > 0 && (
            <div style={{ fontSize:10, color:"#374151", borderTop:"1px solid #10B98135", paddingTop:6 }}>
              <div style={{ display:"flex", justifyContent:"space-between", marginBottom:2 }}>
                <span>Bruto</span>
                <span style={{ fontWeight:600, color:"#374151" }}>{brl(fin.valor_bruto)}</span>
              </div>
              {fin.total_desconto > 0 && <div style={{ display:"flex", justifyContent:"space-between", marginBottom:2 }}>
                <span>− Descontos</span>
                <span style={{ color:"#EF4444" }}>−{brl(fin.total_desconto)}</span>
              </div>}
              {fin.total_copartic > 0 && <div style={{ display:"flex", justifyContent:"space-between", marginBottom:2 }}>
                <span>− Copartic.</span>
                <span style={{ color:"#EF4444" }}>−{brl(fin.total_copartic)}</span>
              </div>}
              {fin.total_ajuste != 0 && <div style={{ display:"flex", justifyContent:"space-between", marginBottom:2 }}>
                <span>{fin.total_ajuste > 0 ? "+ Ajustes" : "− Ajustes"}</span>
                <span style={{ color: fin.total_ajuste > 0 ? "#10B981" : "#EF4444" }}>
                  {fin.total_ajuste > 0 ? "+" : ""}{brl(fin.total_ajuste)}
                </span>
              </div>}
              <div style={{ display:"flex", justifyContent:"space-between", borderTop:"1px dashed #10B98150",
                paddingTop:4, marginTop:2, fontWeight:700 }}>
                <span style={{ color:"#10B981" }}>= Líquido</span>
                <span style={{ color:"#10B981" }}>{brl(fin.faturamento)}</span>
              </div>
            </div>
          )}
          {!loading && (!fin.valor_bruto || fin.valor_bruto === fin.faturamento) && (
            <div style={{ fontSize:10, color:"#9CA3AF" }}>
              Ticket médio: {brl(fin.ticket_medio)}
            </div>
          )}
        </div>
        <ModuloCard label="Pend. Fat."   value={brl(fin.val_aberto)}         color="#F59E0B" loading={loading} icon="trending"
          sub="Guias ainda não faturadas"/>
      </div>

      {/* Card Particular — destaque */}
      <div style={{ background:"linear-gradient(135deg,#FFF7ED,#FFEDD5)", borderRadius:14,
        padding:"16px 24px", marginBottom:20, border:"1.5px solid #FED7AA",
        display:"flex", alignItems:"center", justifyContent:"space-between", gap:16 }}>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          <div style={{ width:44, height:44, borderRadius:12, background:"#F97316",
            display:"flex", alignItems:"center", justifyContent:"center", fontSize:22, flexShrink:0 }}>💰</div>
          <div>
            <div style={{ fontSize:11, color:"#EA580C", fontWeight:800, textTransform:"uppercase",
              letterSpacing:"0.07em", marginBottom:2 }}>Já Recebido / Particular</div>
            <div style={{ fontSize:13, color:"#9A3412" }}>
              {loading ? "…" : `${num(op.particular_os)} guias PAR · ${num(op.particular_pac)} pacientes`}
            </div>
          </div>
        </div>
        {/* Fórmula */}
        {!loading && (
          <div style={{ fontSize:12, color:"#9A3412", textAlign:"center", lineHeight:1.6 }}>
            <div>{brl(op.producao_total_calc)}</div>
            <div style={{ color:"#EF4444" }}>− {brl(op.pendente_calc)}</div>
            <div style={{ borderTop:"1px solid #FED7AA", marginTop:2, paddingTop:2,
              fontWeight:700, color:"#EA580C" }}>= {brl(op.particular_valor)}</div>
            <div style={{ fontSize:10, color:"#9CA3AF" }}>Produção − Pendente</div>
          </div>
        )}
        <div style={{ textAlign:"center" }}>
          <div style={{ fontSize:11, color:"#EA580C", fontWeight:600, marginBottom:2 }}>% Recebido</div>
          <div style={{ fontSize:26, fontWeight:900, color:"#C2410C" }}>
            {loading ? "…" : op.producao_total_calc > 0
              ? `${(((op.producao_total_calc - (op.pendente_calc||0))/op.producao_total_calc)*100).toFixed(1)}%`
              : "—"}
          </div>
        </div>
        <div style={{ textAlign:"right" }}>
          <div style={{ fontSize:11, color:"#EA580C", fontWeight:600, marginBottom:2 }}>Valor Recebido</div>
          <div style={{ fontSize:32, fontWeight:900, color:"#C2410C", lineHeight:1 }}>
            {loading ? "…" : brl(op.particular_valor)}
          </div>
          <div style={{ fontSize:11, color:"#9CA3AF", marginTop:3 }}>
            Convênio PAR: {loading ? "…" : brl(
              op.producao_total_calc > 0
                ? (op.particular_os||0) > 0 ? (op.particular_valor||0) : 0
                : 0
            )}
          </div>
        </div>
      </div>

      {/* Divisão Consultas Médicas x Equipe Mult */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:14, marginBottom:20 }}>
        {/* Consultas Médicas */}
        <div style={{ background:"#FDF2F2", borderRadius:14, padding:"18px 20px", borderLeft:"4px solid #8B1A1A" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:14 }}>
            <div>
              <div style={{ fontSize:11, color:"#8B1A1A", fontWeight:800, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:4 }}>
                🩺 Consultas Médicas
              </div>
              <div style={{ fontSize:32, fontWeight:900, color:"#7A1515", lineHeight:1 }}>
                {loading ? "…" : num(op.consultas_medicas)}
              </div>
              <div style={{ fontSize:12, color:"#6B7280", marginTop:3 }}>guias no período</div>
            </div>
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:11, color:"#6B7280", marginBottom:2 }}>Produção</div>
              <div style={{ fontSize:18, fontWeight:800, color:"#8B1A1A" }}>{loading?"…":brl(op.valor_consultas)}</div>
            </div>
          </div>
          <EspBar dados={data?.consultas} label="consultas" cor="#8B1A1A" brl={brl} num={num} periodo={periodo} atend="ASS"/>
        </div>

        {/* Equipe Multidisciplinar */}
        <div style={{ background:"#F5F3FF", borderRadius:14, padding:"18px 20px", borderLeft:"4px solid #8B5CF6" }}>
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:14 }}>
            <div>
              <div style={{ fontSize:11, color:"#8B5CF6", fontWeight:800, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:4 }}>
                🤝 Equipe Multidisciplinar
              </div>
              <div style={{ fontSize:32, fontWeight:900, color:"#7C3AED", lineHeight:1 }}>
                {loading ? "…" : num(op.equipe_mult)}
              </div>
              <div style={{ fontSize:12, color:"#6B7280", marginTop:3 }}>guias no período</div>
            </div>
            <div style={{ textAlign:"right" }}>
              <div style={{ fontSize:11, color:"#6B7280", marginBottom:2 }}>Produção</div>
              <div style={{ fontSize:18, fontWeight:800, color:"#8B5CF6" }}>{loading?"…":brl(op.valor_equipe_mult)}</div>
            </div>
          </div>
          <EspBar dados={data?.equipe_mult} label="equipe" cor="#8B5CF6" brl={brl} num={num} periodo={periodo} atend="ASS"/>
        </div>
      </div>

      {/* Gráficos */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginBottom:16 }}>
        <Card title="Produção por Dia" subtitle="Evolução no período">
          <LinhaChart data={data?.por_dia} dataKey="valor" color="#8B1A1A"/>
        </Card>
        <Card title="Serviços por Dia" subtitle="Volumetria de serviços realizados">
          {loading ? <Skeleton h={180}/> : (
            <ResponsiveContainer width="100%" height={180}>
              <ComposedChart data={data?.servicos_dia||[]} margin={{top:4,right:8,bottom:0,left:0}}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false}/>
                <XAxis dataKey="data" tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false}
                  tickFormatter={v=>v?.slice(5)} interval="preserveStartEnd"/>
                <YAxis yAxisId="left" tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} width={30}/>
                <YAxis yAxisId="right" orientation="right" tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} width={30}/>
                <Tooltip content={<CTip fmt={v=>v?.toLocaleString("pt-BR")}/>}/>
                <Legend iconSize={10} wrapperStyle={{fontSize:11,paddingTop:6}}/>
                <Bar yAxisId="left" dataKey="qtd_servicos" fill="#8B5CF6" radius={[3,3,0,0]}
                  name="Serviços" opacity={0.85} barSize={14}/>
                <Bar yAxisId="left" dataKey="qtd_os" fill="#8B1A1A" radius={[3,3,0,0]}
                  name="Guias" opacity={0.7} barSize={10}/>
                <Line yAxisId="right" type="monotone" dataKey="qtd_pac"
                  stroke="#10B981" strokeWidth={2} dot={{r:3}} name="Pacientes"/>
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      {/* SADT */}
      <Card title="Exames SADT" subtitle="Laboratoriais · Imagem · Outros Serviços" style={{ marginTop:16 }}>
        {loading ? <Skeleton h={300}/> : (() => {
          const brl = v => new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v||0);
          const num = v => Number(v||0).toLocaleString("pt-BR");
          const sadt = data?.sadt || [];

          // Group by categoria
          const grupos = {};
          sadt.forEach(r => {
            if (!grupos[r.categoria]) grupos[r.categoria] = { itens:[], total_servicos:0, total_valor:0, total_pac:0 };
            grupos[r.categoria].itens.push(r);
            grupos[r.categoria].total_servicos += r.qtd_servicos||0;
            grupos[r.categoria].total_valor    += r.valor||0;
            grupos[r.categoria].total_pac      += r.qtd_pac||0;
          });

          const COR_CAT = {
            "Laboratorial":   "#10B981",
            "Imagem":         "#8B1A1A",
            "Outros Serviços":"#F59E0B",
          };
          const ICON_CAT = { "Laboratorial":"🧪", "Imagem":"🩻", "Outros Serviços":"⚕️" };

          if (!sadt.length) return (
            <div style={{ padding:"30px", textAlign:"center", color:"#9CA3AF" }}>
              Sem exames SADT no período
            </div>
          );

          const labExames = data?.sadt_lab_exames || [];
          const maxLabVal = labExames[0]?.qtd_servicos || 1;

          return (
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))", gap:16 }}>
              {Object.entries(grupos).map(([cat, g]) => {
                const cor  = COR_CAT[cat] || "#6B7280";
                const icon = ICON_CAT[cat] || "🔬";
                const maxV = g.itens[0]?.valor || 1;
                const isLab = cat === "Laboratorial";
                return (
                  <div key={cat} style={{ background:"#F2F2F2", borderRadius:12,
                    borderTop:`3px solid ${cor}`, padding:"14px 16px" }}>
                    {/* Header */}
                    <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:12 }}>
                      <div>
                        <div style={{ fontSize:14, fontWeight:800, color:"#111827", marginBottom:3 }}>
                          {icon} {cat}
                        </div>
                        <div style={{ fontSize:11, color:"#6B7280" }}>
                          {num(g.total_servicos)} serviços · {num(g.total_pac)} pac.
                        </div>
                      </div>
                      <div style={{ textAlign:"right" }}>
                        <div style={{ fontSize:16, fontWeight:800, color:cor }}>{brl(g.total_valor)}</div>
                      </div>
                    </div>

                    {/* Laboratorial: lista de exames por nome */}
                    {isLab ? (
                      <div style={{ display:"flex", flexDirection:"column", gap:6,
                        maxHeight:320, overflowY:"auto" }}>
                        {labExames.map((ex,i) => (
                          <div key={i}>
                            <div style={{ display:"flex", justifyContent:"space-between",
                              alignItems:"center", marginBottom:3 }}>
                              <span style={{ fontSize:11, fontWeight:600, color:"#374151",
                                overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap",
                                maxWidth:"65%" }} title={ex.nome}>
                                {ex.nome_curto || ex.cod}
                              </span>
                              <div style={{ display:"flex", gap:8, flexShrink:0 }}>
                                <span style={{ fontSize:11, fontWeight:700, color:cor }}>
                                  {num(ex.qtd_servicos)}×
                                </span>
                                <span style={{ fontSize:10, color:"#9CA3AF" }}>
                                  {num(ex.qtd_pac)} pac.
                                </span>
                              </div>
                            </div>
                            <div style={{ height:4, background:"#E2E8F0", borderRadius:3 }}>
                              <div style={{ height:"100%", background:cor, borderRadius:3,
                                width:`${Math.max(3,(ex.qtd_servicos/maxLabVal)*100)}%`, opacity:.8 }}/>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      /* Imagem e Outros: lista por especialidade */
                      <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                        {g.itens.map((item,i) => (
                          <div key={i}>
                            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3 }}>
                              <span style={{ fontSize:12, fontWeight:600, color:"#374151" }}>
                                {item.especialidade || item.esp_cod}
                              </span>
                              <div style={{ textAlign:"right" }}>
                                <span style={{ fontSize:12, fontWeight:700, color:cor }}>{brl(item.valor)}</span>
                                <span style={{ fontSize:10, color:"#9CA3AF", marginLeft:6 }}>
                                  {num(item.qtd_servicos)} serv.
                                </span>
                              </div>
                            </div>
                            <div style={{ height:5, background:"#E2E8F0", borderRadius:3, overflow:"hidden" }}>
                              <div style={{ height:"100%", borderRadius:3, background:cor,
                                width:`${Math.max(3,(item.valor/maxV)*100)}%`, opacity:.8 }}/>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          );
        })()}
      </Card>

      <Card title="Por Convênio" subtitle="Top convênios — produção">
        {loading ? <Skeleton/> : <ConvenioBar data={data?.por_convenio}/>}
      </Card>
    </div>
  );
}

// ── MÓDULO OCUPACIONAL ────────────────────────────────────────────────────────
function SecaoModuloOcupacional({ periodo }) {
  const { data, loading, error } = useFetch("/api/modulo/ocupacional/resumo", { periodo });
  const fin = data?.financeiro || {};
  const op  = data?.operacional || {};
  const v   = data?.variacoes || {};
  const brl = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";
  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";

  const tiposOcup = [
    { label:"Admissional",   key:"admissional",  color:"#8B1A1A", cod:"ADM" },
    { label:"Periódico",     key:"periodico",    color:"#10B981", cod:"PER" },
    { label:"Demissional",   key:"demissional",  color:"#EF4444", cod:"DEM" },
    { label:"Ret. Trabalho", key:"ret_trabalho", color:"#F59E0B", cod:"RTB" },
    { label:"Mud. Função",   key:"mud_funcao",   color:"#8B5CF6", cod:"MDF" },
    { label:"Med. Ocup.",    key:"med_ocup",     color:"#0891B2", cod:"MOC" },
  ];

  const brlK = v => v != null ? `R$${(Number(v)/1000).toFixed(0)}k` : "—";

  return (
    <div style={{ animation:"fadeIn 0.35s ease" }}>
      {error && <Err msg={error.message}/>}

      <ModuleHero
        title="Medicina Ocupacional"
        subtitle={`Período: ${periodoParaLabel(periodo)}`}
        cor="#D97706"
        loading={loading}
        stats={[
          { label:"Total OSs",        value: num(op.total_os),          sub: `${num(op.pacientes_unicos)} pac.`, trend: v.total_os },
          { label:"Empresas",         value: num(op.empresas),          sub: "atendidas no período" },
          { label:"Produção",         value: brlK(fin.faturamento),     sub: `Ticket: ${brl(fin.ticket_medio)}`, trend: v.faturamento },
          { label:"Admissional",      value: num(op.admissional),       sub: `Demissional: ${num(op.demissional)}` },
        ]}
      />

      <MetaModulo modulo="ocupacional" cor="#D97706" atual={fin.faturamento} periodo={periodo}/>

      <BriefingCard
        cor="#D97706"
        cacheKey={`briefing_ocupacional_${periodoParaLabel(periodo)}`}
        disabled={loading}
        promptFn={() => `Você é um analista de saúde ocupacional. Gere um briefing executivo em no máximo 4 frases, direto e profissional, sem markdown.

DADOS — Medicina Ocupacional (período: ${periodoParaLabel(periodo)}):
- Admissional: ${op?.admissional ?? "n/d"} | Periódico: ${op?.periodico ?? "n/d"} | Demissional: ${op?.demissional ?? "n/d"}
- Retorno ao trabalho: ${op?.ret_trabalho ?? "n/d"} | Mudança de função: ${op?.mud_funcao ?? "n/d"}
- Total OSs: ${op?.total_os ?? "n/d"} | Empresas atendidas: ${op?.empresas ?? "n/d"}
- Pacientes únicos: ${op?.pacientes_unicos ?? "n/d"}
- Produção financeira: ${brl(fin?.faturamento)} | Ticket médio: ${brl(fin?.ticket_medio)}

Destaque tipos em crescimento, oportunidades de captação de empresas e alertas operacionais.`}
      />

      {/* Tipos de atendimento — cards gradiente */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(148px,1fr))", gap:12, marginBottom:20 }}>
        {tiposOcup.map(t => {
          const val = op[t.key];
          const total = op.total_os || 1;
          const parcPct = val ? Math.round((val/total)*100) : 0;
          return (
          <div key={t.cod} style={{
            background:`linear-gradient(135deg, ${t.color}18 0%, ${t.color}06 100%)`,
            borderRadius:14, padding:"16px", border:`1.5px solid ${t.color}28`,
            boxShadow:`0 4px 14px ${t.color}10`, textAlign:"center",
          }}>
            <div style={{ width:40, height:40, borderRadius:12, background:t.color,
              display:"flex", alignItems:"center", justifyContent:"center",
              margin:"0 auto 10px", boxShadow:`0 4px 10px ${t.color}40` }}>
              <span style={{ fontSize:18, color:"#fff", fontWeight:900 }}>{loading?"…":num(val)?.split(".")[0]?.slice(0,3)}</span>
            </div>
            <div style={{ fontSize:26, fontWeight:900, color:t.color, lineHeight:1, marginBottom:4 }}>
              {loading ? "…" : num(val)}
            </div>
            <div style={{ fontSize:10, color:"#64748B", fontWeight:800, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:4 }}>{t.label}</div>
            <div style={{ height:3, borderRadius:3, background:`${t.color}20`, overflow:"hidden" }}>
              <div style={{ height:"100%", width:`${parcPct}%`, background:t.color, transition:"width 0.8s ease" }}/>
            </div>
            <div style={{ fontSize:10, color:t.color, fontWeight:700, marginTop:3 }}>{parcPct}% do total</div>
          </div>
          );
        })}
      </div>

      {/* KPIs financeiros */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:14, marginBottom:20 }}>
        <ModuloCard label="Total OSs"        value={num(op.total_os)}        color="#8B1A1A" loading={loading} icon="bar"/>
        <ModuloCard label="Empresas Atend."  value={num(op.empresas)}        color="#8B5CF6" loading={loading} icon="factory"/>
        <ModuloCard label="Produção"      value={brl(fin.faturamento)}    color="#10B981" loading={loading} icon="dollar"
          sub={`Ticket: ${brl(fin.ticket_medio)}`}/>
        <ModuloCard label="Pacientes Únicos" value={num(op.pacientes_unicos)} color="#F59E0B" loading={loading} icon="users"/>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginBottom:16 }}>
        <Card title="Produção por Dia" subtitle="Evolução no período">
          <LinhaChart data={data?.por_dia} dataKey="valor" color="#F59E0B"/>
        </Card>
        <Card title="Volume por Dia" subtitle="OSs por dia">
          <BarChart2 data={data?.por_dia} dataKey="qtd_os" color="#8B1A1A"/>
        </Card>
      </div>

      <Card title="Top Empresas" subtitle="Por volume de atendimentos">
        {loading ? <Skeleton h={280}/> : (
          <div style={{ overflowX:"auto" }}>
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
              <thead>
                <tr style={{ background:"#F2F2F2", borderBottom:`1px solid ${C.border}` }}>
                  {["#","Empresa","Adm.","Per.","Dem.","Total","Produção"].map(h=>(
                    <th key={h} style={{ padding:"10px 14px", fontWeight:700, color:C.faint, textAlign:h==="Empresa"||h==="#"?"left":"right", fontSize:11, textTransform:"uppercase" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data?.empresas||[]).map((e,i)=>(
                  <tr key={i} style={{ borderBottom:`1px solid ${C.border}` }}
                    onMouseEnter={ev=>ev.currentTarget.style.background="#F2F2F2"}
                    onMouseLeave={ev=>ev.currentTarget.style.background="transparent"}>
                    <td style={{ padding:"10px 14px", color:C.faint, fontWeight:700 }}>{i+1}</td>
                    <td style={{ padding:"10px 14px", fontWeight:600, color:"#111827" }}>{e.empresa}</td>
                    <td style={{ padding:"10px 14px", textAlign:"right", color:"#8B1A1A" }}>{num(e.adm)}</td>
                    <td style={{ padding:"10px 14px", textAlign:"right", color:"#10B981" }}>{num(e.per)}</td>
                    <td style={{ padding:"10px 14px", textAlign:"right", color:"#EF4444" }}>{num(e.dem)}</td>
                    <td style={{ padding:"10px 14px", textAlign:"right", fontWeight:800, color:"#111827" }}>{num(e.total)}</td>
                    <td style={{ padding:"10px 14px", textAlign:"right", color:"#F59E0B", fontWeight:700 }}>{brl(e.faturamento)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}

// ── MÓDULO SERVIÇOS (PSI, NUT, FON, etc) ─────────────────────────────────────
function SecaoModuloServicos({ periodo }) {
  const { data, loading, error } = useFetch("/api/modulo/servicos/resumo", { periodo });
  const fin = data?.financeiro || {};
  const v   = data?.variacoes || {};
  const brl = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";
  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";

  const CORES_SVC = { PSI:"#8B5CF6",NUT:"#10B981",FON:"#8B1A1A",FIS:"#F59E0B",OFT:"#0891B2",DER:"#DB2777",END:"#D97706",GIN:"#EC4899",PED:"#14B8A6",ORT:"#6366F1" };

  const brlK = v => v != null ? `R$${(Number(v)/1000).toFixed(0)}k` : "—";

  return (
    <div style={{ animation:"fadeIn 0.35s ease" }}>
      {error && <Err msg={error.message}/>}

      <ModuleHero
        title="Serviços Especializados"
        subtitle={`Período: ${periodoParaLabel(periodo)} · PSI · NUT · FON · FIS · OFT e mais`}
        cor="#8B5CF6"
        loading={loading}
        stats={[
          { label:"Total OSs",       value: num(fin.total_os),          sub: `${num(fin.pacientes_unicos)} pac.`, trend: v.total_os },
          { label:"Produção",        value: brlK(fin.faturamento),      sub: "faturamento líquido", trend: v.faturamento },
          { label:"Ticket Médio",    value: brl(fin.ticket_medio),      sub: "por OS", trend: v.ticket_medio },
          { label:"Serviços Ativos", value: num((data?.por_servico||[]).length), sub: "especialidades" },
        ]}
      />

      <MetaModulo modulo="servicos" cor="#8B5CF6" atual={fin.faturamento} periodo={periodo}/>

      <BriefingCard
        cor="#8B5CF6"
        cacheKey={`briefing_servicos_${periodoParaLabel(periodo)}`}
        disabled={loading}
        promptFn={() => {
          const top3svc = (data?.por_servico||[]).slice(0,3).map(s=>`${s.nome}: ${num(s.qtd_os)} OSs (${brl(s.faturamento)})`).join("; ");
          return `Você é um analista de gestão clínica. Gere um briefing executivo em no máximo 4 frases, direto e profissional, sem markdown.

DADOS — Serviços Especializados (período: ${periodoParaLabel(periodo)}):
- Total OSs: ${fin.total_os ?? "n/d"} | Pacientes únicos: ${fin.pacientes_unicos ?? "n/d"}
- Produção financeira: ${brl(fin.faturamento)} | Ticket médio: ${brl(fin.ticket_medio)}
- Top serviços: ${top3svc || "n/d"}

Destaque serviços com maior demanda, oportunidades de crescimento e alertas de queda.`;
        }}
      />

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:14, marginBottom:20 }}>
        <ModuloCard label="Total OSs"        value={num(fin.total_os)}        color="#8B5CF6" loading={loading} icon="bar"/>
        <ModuloCard label="Pacientes Únicos" value={num(fin.pacientes_unicos)} color="#8B1A1A" loading={loading} icon="users"/>
        <ModuloCard label="Produção"         value={brlK(fin.faturamento)}    color="#10B981" loading={loading} icon="dollar"/>
        <ModuloCard label="Ticket Médio"     value={brl(fin.ticket_medio)}    color="#F59E0B" loading={loading} icon="trending"/>
      </div>

      {/* Cards por serviço — gradiente */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(165px,1fr))", gap:12, marginBottom:20 }}>
        {(data?.por_servico||[]).map((s,i)=>{
          const cor = CORES_SVC[s.codigo] || CORES_ESP[i%CORES_ESP.length];
          const maxFat = (data?.por_servico||[])[0]?.faturamento || 1;
          const largPct = Math.max(8, (s.faturamento/maxFat)*100);
          return (
            <div key={i} style={{
              background:`linear-gradient(135deg, ${cor}14 0%, ${cor}05 100%)`,
              borderRadius:14, padding:"16px 18px",
              border:`1.5px solid ${cor}25`,
              boxShadow:`0 4px 12px ${cor}10`,
            }}>
              <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10 }}>
                <span style={{ fontSize:10, color:"#64748B", fontWeight:800, textTransform:"uppercase", letterSpacing:"0.07em" }}>{s.nome}</span>
                <span style={{ fontSize:10, fontWeight:700, color:cor, background:`${cor}18`, borderRadius:5, padding:"2px 6px" }}>{s.codigo}</span>
              </div>
              <div style={{ fontSize:28, fontWeight:900, color:cor, lineHeight:1, marginBottom:3 }}>{num(s.qtd_os)}</div>
              <div style={{ fontSize:11, color:"#64748B", marginBottom:10 }}>OSs · {num(s.pacientes)} pac.</div>
              <div style={{ fontSize:13, fontWeight:800, color:"#111827", marginBottom:8 }}>{brl(s.faturamento)}</div>
              <div style={{ height:4, borderRadius:3, background:`${cor}15`, overflow:"hidden" }}>
                <div style={{ height:"100%", width:`${largPct}%`, background:`linear-gradient(90deg,${cor}80,${cor})`, transition:"width 0.8s" }}/>
              </div>
            </div>
          );
        })}
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16 }}>
        <Card title="Produção por Dia">
          <LinhaChart data={data?.por_dia} dataKey="valor" color="#8B5CF6"/>
        </Card>
        <Card title="Por Convênio">
          {loading ? <Skeleton/> : <ConvenioBar data={data?.por_convenio}/>}
        </Card>
      </div>
    </div>
  );
}

// ── MÓDULO LABORATÓRIO ────────────────────────────────────────────────────────
// ── DASHBOARD RECOLETA ────────────────────────────────────────────────────────
function DashboardRecoleta({ periodo, setor }) {
  const { data, loading } = useFetch("/api/laboratorio/recoleta", { periodo, setor });
  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";
  const pct = v => v != null ? `${Number(v).toFixed(2)}%` : "—";

  const taxaCor = !data ? "#9CA3AF"
    : data.taxa_recoleta_pct < 2 ? "#10B981"
    : data.taxa_recoleta_pct < 5 ? "#F59E0B"
    : "#EF4444";

  const taxaLabel = !data ? "—"
    : data.taxa_recoleta_pct < 2 ? "Ótimo"
    : data.taxa_recoleta_pct < 5 ? "Atenção"
    : "Crítico";

  return (
    <div style={{ marginTop:24, marginBottom:24 }}>
      <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:16 }}>
        <div style={{ width:4, height:20, borderRadius:2, background:"#EF4444" }}/>
        <span style={{ fontSize:15, fontWeight:700, color:"#111827" }}>Taxa de Recoleta</span>
        <span style={{ fontSize:12, color:C.faint }}>— cancelamentos por nova amostra</span>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(140px,1fr))", gap:12, marginBottom:16 }}>
        {/* Taxa principal */}
        <div style={{ background:"#fff", borderRadius:14, padding:"20px 16px",
          borderTop:`4px solid ${taxaCor}`, boxShadow:"0 1px 3px rgba(0,0,0,0.06)",
          display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", gap:6 }}>
          <span style={{ fontSize:10, color:C.faint, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em", textAlign:"center" }}>Taxa de Recoleta</span>
          {loading
            ? <div style={{ height:44, width:80, background:"#F3F4F6", borderRadius:8, animation:"pulse 1.5s infinite" }}/>
            : <span style={{ fontSize:36, fontWeight:900, color:taxaCor, lineHeight:1 }}>{pct(data?.taxa_recoleta_pct)}</span>
          }
          {data && <span style={{ fontSize:11, fontWeight:700, color:taxaCor, background:taxaCor+"15", padding:"2px 10px", borderRadius:12 }}>{taxaLabel}</span>}
          <span style={{ fontSize:10, color:C.faint, textAlign:"center" }}>meta: &lt; 2%</span>
        </div>

        {[
          { label:"Total Recoletas",    val:num(data?.total_recoletas),   color:"#EF4444", sub:`de ${num(data?.total_exames)} exames` },
          { label:"OSs Afetadas",       val:num(data?.os_com_recoleta),   color:"#F59E0B", sub:`de ${num(data?.total_os)} OSs` },
          { label:"Pacientes Afetados", val:num(data?.pacientes_recoleta),color:"#8B5CF6", sub:"com recoleta" },
          { label:"Média/Dia",
            val: data?.por_dia?.length ? (data.total_recoletas/data.por_dia.length).toFixed(1) : "—",
            color:"#0891B2", sub:"recoletas por dia" },
        ].map((k,i) => (
          <div key={i} style={{ background:"#fff", borderRadius:14, padding:"18px 20px",
            borderTop:`3px solid ${k.color}`, boxShadow:"0 1px 3px rgba(0,0,0,0.06)",
            display:"flex", flexDirection:"column", gap:4 }}>
            <span style={{ fontSize:10, color:C.faint, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em" }}>{k.label}</span>
            {loading
              ? <div style={{ height:30, width:"60%", background:"#F3F4F6", borderRadius:6, animation:"pulse 1.5s infinite" }}/>
              : <span style={{ fontSize:24, fontWeight:800, color:"#111827", lineHeight:1.1 }}>{k.val}</span>
            }
            <span style={{ fontSize:11, color:C.sub }}>{k.sub}</span>
          </div>
        ))}
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr 1fr", gap:14, marginBottom:14 }}>
        {/* Por motivo */}
        <Card title="Por Motivo" subtitle="Causa da recoleta">
          {loading ? <Skeleton h={160}/> : !(data?.por_motivo?.length) ? (
            <div style={{ padding:"24px", textAlign:"center", color:C.faint, fontSize:12 }}>Sem dados</div>
          ) : (
            <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
              {(data.por_motivo||[]).map((m,i) => {
                const max  = data.por_motivo[0]?.qtd || 1;
                const pBar = Math.max(6,(m.qtd/max)*100);
                const cores = ["#EF4444","#F59E0B","#8B5CF6","#0891B2"];
                return (
                  <div key={i}>
                    <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3 }}>
                      <span style={{ fontSize:12, color:"#111827", fontWeight:600 }}>{m.motivo_nome}</span>
                      <span style={{ fontSize:12, color:cores[i%cores.length], fontWeight:700 }}>{m.qtd}</span>
                    </div>
                    <div style={{ height:6, background:"#EEEEEE", borderRadius:4, overflow:"hidden" }}>
                      <div style={{ height:"100%", width:`${pBar}%`, background:cores[i%cores.length], borderRadius:4 }}/>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* Por exame */}
        <Card title="Exames Mais Recoletados" subtitle="Top 10 exames">
          {loading ? <Skeleton h={160}/> : !(data?.por_exame?.length) ? (
            <div style={{ padding:"24px", textAlign:"center", color:C.faint, fontSize:12 }}>Sem dados</div>
          ) : (
            <div style={{ display:"flex", flexDirection:"column", gap:7 }}>
              {(data.por_exame||[]).map((e,i) => {
                const max  = data.por_exame[0]?.qtd_recoleta || 1;
                const pBar = Math.max(6,(e.qtd_recoleta/max)*100);
                return (
                  <div key={i} style={{ display:"flex", alignItems:"center", gap:8 }}>
                    <span style={{ fontSize:11, fontFamily:"monospace", fontWeight:700, color:"#374151", width:64, flexShrink:0 }}>{e.exame_cod}</span>
                    <div style={{ flex:1, height:16, background:"#EEEEEE", borderRadius:4, overflow:"hidden", position:"relative" }}>
                      <div style={{ height:"100%", width:`${pBar}%`, background:"#EF4444", borderRadius:4, opacity:.8 }}/>
                      <span style={{ position:"absolute", right:6, top:"50%", transform:"translateY(-50%)", fontSize:10, fontWeight:700, color:"#374151" }}>{e.qtd_recoleta}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* Por médico */}
        <Card title="Por Médico Requisitante" subtitle="Quem mais gera recoleta">
          {loading ? <Skeleton h={160}/> : !(data?.por_medico?.length) ? (
            <div style={{ padding:"24px", textAlign:"center", color:C.faint, fontSize:12 }}>Sem dados</div>
          ) : (
            <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
              {(data.por_medico||[]).map((m,i) => {
                const max  = data.por_medico[0]?.recoletas || 1;
                const pBar = Math.max(6,(m.recoletas/max)*100);
                return (
                  <div key={i}>
                    <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3 }}>
                      <span style={{ fontSize:11, color:"#111827", fontWeight:600, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", maxWidth:"75%" }}>{m.medico||"Não informado"}</span>
                      <span style={{ fontSize:11, color:"#EF4444", fontWeight:700 }}>{m.recoletas}</span>
                    </div>
                    <div style={{ height:4, background:"#EEEEEE", borderRadius:3, overflow:"hidden" }}>
                      <div style={{ height:"100%", width:`${pBar}%`, background:"#EF4444", borderRadius:3, opacity:.7 }}/>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {/* Tendência diária */}
      <Card title="Tendência Diária de Recoletas" subtitle="Evolução no período">
        {loading ? <Skeleton h={140}/> : !(data?.por_dia?.length) ? (
          <div style={{ padding:"24px", textAlign:"center", color:C.faint, fontSize:12 }}>Sem recoletas no período</div>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <BarChart data={data.por_dia} barSize={16}>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false}/>
              <XAxis dataKey="data" tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} tickFormatter={v=>v?.slice(5)}/>
              <YAxis tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} allowDecimals={false}/>
              <Tooltip content={<CTip/>}/>
              <Bar dataKey="recoletas"   fill="#EF4444" radius={[4,4,0,0]} name="Recoletas" opacity={0.85}/>
              <Bar dataKey="os_afetadas" fill="#F59E0B" radius={[4,4,0,0]} name="OSs afetadas" opacity={0.75}/>
              <Legend iconSize={10} wrapperStyle={{fontSize:12,color:"#374151",paddingTop:6}}/>
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>
    </div>
  );
}


// ── Tabela de médicos lab com sort (componente separado para evitar hooks condicionais)
function TabelaMedicosLab({ medicos, labelColuna = "Médico", semDadosTexto = "Sem dados de médico requisitante" }) {
  const [sortCol, setSortCol] = useState("producao");
  const [sortDir, setSortDir] = useState("desc");
  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";
  const brl = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";

  const toggle = (col) => {
    if (sortCol === col) setSortDir(d => d==="desc"?"asc":"desc");
    else { setSortCol(col); setSortDir("desc"); }
  };

  const sorted = [...(medicos||[])].sort((a,b) => {
    const va = a[sortCol]||0, vb = b[sortCol]||0;
    return sortDir==="desc" ? vb-va : va-vb;
  });

  const maxVal = sorted[0]?.[sortCol] || 1;

  const TH = ({ col, label }) => {
    const active = sortCol === col;
    return (
      <th onClick={() => toggle(col)} style={{
        padding:"10px 14px", fontWeight:700, textAlign:"right",
        color: active ? "#10B981" : C.faint, fontSize:11,
        textTransform:"uppercase", letterSpacing:"0.05em",
        cursor:"pointer", userSelect:"none",
        background: active ? "#F0FDF4" : "transparent",
      }}>
        {label} <span style={{ opacity:active?1:0.3 }}>{active?(sortDir==="desc"?"↓":"↑"):"↕"}</span>
      </th>
    );
  };

  if (!sorted.length) return (
    <div style={{ padding:"32px", textAlign:"center", color:C.faint, fontSize:13 }}>{semDadosTexto}</div>
  );

  return (
    <div style={{ overflowX:"auto" }}>
      <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
        <thead>
          <tr style={{ background:"#F2F2F2", borderBottom:`1px solid ${C.border}` }}>
            <th style={{ padding:"10px 14px", fontWeight:700, color:C.faint, textAlign:"left", fontSize:11, textTransform:"uppercase" }}>#</th>
            <th style={{ padding:"10px 14px", fontWeight:700, color:C.faint, textAlign:"left", fontSize:11, textTransform:"uppercase" }}>{labelColuna}</th>
            <TH col="total_os"      label="OSs"/>
            <TH col="total_exames"  label="Exames"/>
            <TH col="pacientes"     label="Pacientes"/>
            <TH col="producao"   label="Produção"/>
            <TH col="ticket_por_os" label="Ticket/OS"/>
          </tr>
        </thead>
        <tbody>
          {sorted.map((m,i) => {
            const pct = Math.max(4, ((m[sortCol]||0)/maxVal)*100);
            const barCor = sortCol==="producao"||sortCol==="ticket_por_os" ? C.amber
                         : sortCol==="total_exames" ? "#8B1A1A" : "#10B981";
            return (
              <tr key={i} style={{ borderBottom:`1px solid ${C.border}` }}
                onMouseEnter={e => e.currentTarget.style.background="#F2F2F2"}
                onMouseLeave={e => e.currentTarget.style.background="transparent"}>
                <td style={{ padding:"10px 14px", color:C.faint, fontWeight:700, fontSize:11 }}>{i+1}</td>
                <td style={{ padding:"10px 14px", minWidth:180 }}>
                  <div style={{ fontWeight:600, color:"#111827" }}>{m.medico}</div>
                  <div style={{ height:3, background:"#EEEEEE", borderRadius:2, marginTop:4, overflow:"hidden" }}>
                    <div style={{ height:"100%", width:`${pct}%`, background:barCor, borderRadius:2, transition:"width 0.4s" }}/>
                  </div>
                </td>
                <td style={{ padding:"10px 14px", textAlign:"right", fontWeight:sortCol==="total_os"?800:500, color:sortCol==="total_os"?"#10B981":"#111827" }}>{num(m.total_os)}</td>
                <td style={{ padding:"10px 14px", textAlign:"right", fontWeight:sortCol==="total_exames"?800:500, color:sortCol==="total_exames"?"#8B1A1A":C.sub }}>{num(m.total_exames)}</td>
                <td style={{ padding:"10px 14px", textAlign:"right", color:C.sub }}>{num(m.pacientes)}</td>
                <td style={{ padding:"10px 14px", textAlign:"right", fontWeight:sortCol==="producao"?800:600, color:sortCol==="producao"?"#10B981":"#111827" }}>{brl(m.faturamento)}</td>
                <td style={{ padding:"10px 14px", textAlign:"right", fontWeight:sortCol==="ticket_por_os"?800:500, color:sortCol==="ticket_por_os"?C.amber:C.sub }}>{brl(m.ticket_por_os)}</td>
              </tr>
            );
          })}
        </tbody>
        <tfoot>
          <tr style={{ background:"#F0FDF4", borderTop:`2px solid #10B981` }}>
            <td colSpan={2} style={{ padding:"10px 14px", fontWeight:800, color:"#111827" }}>TOTAL</td>
            <td style={{ padding:"10px 14px", textAlign:"right", fontWeight:800, color:"#10B981" }}>{num(sorted.reduce((s,m)=>s+(m.total_os||0),0))}</td>
            <td style={{ padding:"10px 14px", textAlign:"right", color:"#8B1A1A", fontWeight:700 }}>{num(sorted.reduce((s,m)=>s+(m.total_exames||0),0))}</td>
            <td style={{ padding:"10px 14px", textAlign:"right", color:C.sub }}>—</td>
            <td style={{ padding:"10px 14px", textAlign:"right", fontWeight:800, color:"#111827" }}>{brl(sorted.reduce((s,m)=>s+(m.faturamento||0),0))}</td>
            <td/>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

const RECEPCOES_LAB = [
  { id: "",    nome: "Todas"                 },
  { id: "RDI", nome: "Recepção Diagnóstico"  },
  { id: "RCI", nome: "Recepção Censo Imagem" },
  { id: "ROC", nome: "Recepção Ocupacional"  },
  { id: "RCN", nome: "Recepção Consultórios" },
  { id: "REX", nome: "Recepção Externa"      },
];

const RECEPCAO_LAB_CORES = {
  RDI: "#8B5CF6", RCI: "#10B981", ROC: "#F59E0B", RCN: "#3B82F6", REX: "#EF4444",
};

// Colunas fixas do card "Produção por Recepção" no módulo Laboratório
const RECEPCOES_LAB_PRODUCAO = [
  { cod: "RDI", nome: "Diagnóstico"   },
  { cod: "RCN", nome: "Consultórios"  },
  { cod: "ROC", nome: "Ocupacional"   },
  { cod: "RCI", nome: "Censo Imagem"  },
];

function SecaoModuloLaboratorio({ periodo }) {
  const [setor, setSetor] = useState("");
  const [recepcao, setRecepcao] = useState("");
  const [mesFiltro, setMesFiltro] = useState(""); // "" = usa o período global do topbar
  const [anoFiltro, setAnoFiltro] = useState(new Date().getFullYear());
  const periodoEfetivo = mesFiltro ? `mes:${anoFiltro}-${String(mesFiltro).padStart(2,"0")}` : periodo;

  const { data, loading, error } = useFetch("/api/modulo/laboratorio/resumo", { periodo: periodoEfetivo, setor, recepcao });
  const fin = data?.financeiro || {};
  const v   = data?.variacoes || {};
  const brl = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";
  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";

  // Top exames flat list do grupo lab
  const topExames = data?.grupos?.lab?.top_exames || [];

  const brlK = v => v != null ? `R$${(Number(v)/1000).toFixed(0)}k` : "—";

  const { data: bancadasData, loading: lBanc } = useFetch("/api/modulo/laboratorio/bancadas", { periodo: periodoEfetivo, setor, recepcao });
  const bancadas = bancadasData?.bancadas || [];
  const resumoBanc = bancadasData?.resumo || {};
  const naoClassificados = bancadasData?.nao_classificados || [];
  const [verNaoClassificados, setVerNaoClassificados] = useState(false);

  const { data: porRecepcaoData, loading: lRecep } = useFetch("/api/modulo/laboratorio/por-recepcao", { periodo: periodoEfetivo, setor });
  const porRecepcao = porRecepcaoData || [];

  const { data: tempoColetaData, loading: lColeta } = useFetch("/api/modulo/laboratorio/tempo-coleta", { periodo: periodoEfetivo, setor, recepcao });
  const senhaColeta = tempoColetaData?.senha_coleta || {};
  const osColeta    = tempoColetaData?.os_coleta || {};
  const senhaColetaPorRecepcao = senhaColeta.por_recepcao || [];
  const osColetaPorRecepcao    = osColeta.por_recepcao || [];
  const min = v => v != null ? `${Math.round(v)} min` : "—";

  const { data: producaoProfissionalData, loading: lProfissional } = useFetch("/api/modulo/laboratorio/producao-por-profissional", { periodo: periodoEfetivo, setor, recepcao });
  const producaoProfissional = producaoProfissionalData || [];

  return (
    <div style={{ animation:"fadeIn 0.35s ease" }}>
      {error && <Err msg={error.message}/>}

      <ModuleHero
        title="Laboratório"
        subtitle={`Período: ${periodoParaLabel(periodoEfetivo)} · Diagnóstico · Ocupacional`}
        cor="#10B981"
        loading={loading}
        stats={[
          { label:"Total Exames",   value: num(fin.total_exames||fin.total_os), sub:`${num(fin.total_os)} OSs`, trend: v.total_os },
          { label:"Pacientes",      value: num(fin.pacientes_unicos),           sub:"atendidos", trend: v.pacientes_unicos },
          { label:"Produção",       value: brlK(fin.faturamento),               sub:`Ticket: ${brl(fin.ticket_medio)}`, trend: v.faturamento },
          { label:"Top Exame",      value: topExames[0]?.exame_cod || "—",      sub: topExames[0] ? `${num(topExames[0].qtd)} realizações` : "" },
        ]}
      />

      <MetaModulo modulo="laboratorio" cor="#10B981" atual={fin.faturamento} periodo={periodoEfetivo}/>

      <BriefingCard
        cor="#10B981"
        cacheKey={`briefing_laboratorio_${periodoParaLabel(periodoEfetivo)}_${setor}_${recepcao}`}
        disabled={loading}
        promptFn={() => {
          const top3ex = topExames.slice(0,3).map(e=>`${e.nome||e.codigo}: ${num(e.qtd)}`).join("; ");
          const setorLabel = setor === "diagnostico" ? "Diagnóstico" : setor === "ocupacional" ? "Ocupacional" : "Todos";
          return `Você é um analista de gestão clínica. Gere um briefing executivo em no máximo 4 frases, direto e profissional, sem markdown.

DADOS — Laboratório / Exames (período: ${periodoParaLabel(periodoEfetivo)}, setor: ${setorLabel}):
- Total exames: ${(fin.total_exames || fin.total_os) ?? "n/d"} | OSs: ${fin.total_os ?? "n/d"}
- Pacientes únicos: ${fin.pacientes_unicos ?? "n/d"}
- Produção financeira: ${brl(fin.faturamento)} | Ticket médio por OS: ${brl(fin.ticket_medio)}
- Exames mais realizados: ${top3ex || "n/d"}

Destaque exames em alta, alertas de capacidade e sugestões para aumentar a produção laboratorial.`;
        }}
      />

      {/* Filtro setor + recepção + mês */}
      <div style={{ display:"flex", gap:16, marginBottom:20, alignItems:"center", flexWrap:"wrap" }}>
        <div style={{ display:"flex", gap:8, alignItems:"center", flexWrap:"wrap" }}>
          <span style={{ fontSize:12, color:C.faint, fontWeight:600 }}>Filtrar por:</span>
          {[
            { id:"",            label:"Todos"       },
            { id:"diagnostico", label:"Diagnóstico" },
            { id:"ocupacional", label:"Ocupacional" },
          ].map(s => (
            <button key={s.id} onClick={() => setSetor(s.id)} style={{
              padding:"6px 16px", borderRadius:8,
              border:`1.5px solid ${setor===s.id?"#10B981":"#E2E8F0"}`,
              background: setor===s.id?"#D1FAE5":"#fff",
              color: setor===s.id?"#059669":"#6B7280",
              fontSize:13, fontWeight:600, cursor:"pointer", transition:"all 0.12s",
            }}>{s.label}</button>
          ))}
        </div>

        <div style={{ display:"flex", gap:8, alignItems:"center", flexWrap:"wrap" }}>
          <span style={{ fontSize:12, color:C.faint, fontWeight:600 }}>Recepção:</span>
          <select value={recepcao} onChange={e=>setRecepcao(e.target.value)} style={{
            padding:"6px 12px", borderRadius:8, border:"1.5px solid #E2E8F0",
            background:"#fff", color:"#374151", fontSize:13, fontWeight:600,
            cursor:"pointer", outline:"none",
          }}>
            {RECEPCOES_LAB.map(r => <option key={r.id} value={r.id}>{r.nome}</option>)}
          </select>
        </div>

        <div style={{ display:"flex", gap:8, alignItems:"center" }}>
          <span style={{ fontSize:12, color:C.faint, fontWeight:600 }}>Mês:</span>
          <select value={mesFiltro} onChange={e=>setMesFiltro(e.target.value)} style={{
            padding:"6px 12px", borderRadius:8, border:"1.5px solid #E2E8F0",
            background:"#fff", color:"#374151", fontSize:13, fontWeight:600,
            cursor:"pointer", outline:"none",
          }}>
            <option value="">Período do topo</option>
            {MESES_PT.map((nome,i) => <option key={i} value={i+1}>{nome}</option>)}
          </select>
          {mesFiltro && (
            <select value={anoFiltro} onChange={e=>setAnoFiltro(Number(e.target.value))} style={{
              padding:"6px 12px", borderRadius:8, border:"1.5px solid #E2E8F0",
              background:"#fff", color:"#374151", fontSize:13, fontWeight:600,
              cursor:"pointer", outline:"none",
            }}>
              {[0,1,2].map(off => {
                const ano = new Date().getFullYear() - off;
                return <option key={ano} value={ano}>{ano}</option>;
              })}
            </select>
          )}
          {mesFiltro && (
            <button onClick={()=>setMesFiltro("")} style={{
              padding:"6px 10px", borderRadius:8, border:"none", cursor:"pointer",
              background:"#FEE2E2", color:"#DC2626", fontSize:12, fontWeight:700,
            }}>✕ limpar</button>
          )}
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:14, marginBottom:20 }}>
        <ModuloCard label="Total Exames" value={num(fin.total_exames||fin.total_os)} color="#8B1A1A" loading={loading} icon="bar"
          sub={`${num(fin.total_os)} OSs`}/>
        <ModuloCard label="Pacientes"    value={num(fin.pacientes_unicos)} color="#8B5CF6" loading={loading} icon="users"/>
        <ModuloCard label="Produção"  value={brl(fin.faturamento)}     color="#10B981" loading={loading} icon="dollar"/>
        <ModuloCard label="Ticket / OS"  value={brl(fin.ticket_medio)}    color="#F59E0B" loading={loading} icon="trending"
          sub="faturamento ÷ nº de OSs"/>
        <ModuloCard label="Senha → Coleta" value={min(senhaColeta.media_min)} color="#0891B2" loading={lColeta} icon="clock"
          sub={senhaColeta.amostras ? `${num(senhaColeta.amostras)} amostras` : ""}/>
        <ModuloCard label="OS → Coleta" value={min(osColeta.media_min)} color="#7C3AED" loading={lColeta} icon="clock"
          sub={osColeta.amostras ? `${num(osColeta.amostras)} amostras` : ""}/>
      </div>

      {/* Tempo até a Coleta — duas métricas, por ponto de recepção */}
      <Card title="Tempo até a Coleta" subtitle="Duas etapas do trajeto até a coleta da amostra laboratorial, por ponto de recepção" style={{ marginBottom:16 }}>
        <div style={{ fontSize:12, fontWeight:800, color:"#0891B2", textTransform:"uppercase", letterSpacing:"0.05em", marginBottom:10 }}>
          Emissão da senha → Coleta
        </div>
        {lColeta ? <Skeleton h={140}/> : senhaColetaPorRecepcao.length === 0 ? (
          <div style={{ padding:"20px", textAlign:"center", color:C.faint, fontSize:12 }}>Sem coletas com senha registrada no período</div>
        ) : (
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))", gap:14, marginBottom:24 }}>
            {RECEPCOES_LAB_PRODUCAO.map(rc => {
              const r = senhaColetaPorRecepcao.find(x => x.recepcao_cod === rc.cod);
              const cor = RECEPCAO_LAB_CORES[rc.cod] || "#64748B";
              return (
                <div key={rc.cod} style={{
                  background:`linear-gradient(135deg, ${cor}22 0%, ${cor}0A 100%)`,
                  borderRadius:12, padding:"16px 18px", border:`1.5px solid ${cor}35`,
                }}>
                  <div style={{ fontSize:13, fontWeight:800, color:"#111827", marginBottom:12 }}>{rc.nome}</div>
                  <div style={{ fontSize:10, color:cor, fontWeight:800, textTransform:"uppercase", letterSpacing:"0.05em" }}>Tempo médio</div>
                  <div style={{ fontSize:28, fontWeight:900, color:cor, lineHeight:1.15 }}>{r ? min(r.tempo_medio_min) : "—"}</div>
                  <div style={{ fontSize:11, color:"#6B7280", marginTop:10, fontWeight:600 }}>
                    {r ? `${num(r.amostras)} amostras · min ${min(r.tempo_min_min)} · max ${min(r.tempo_max_min)}` : "sem amostras no período"}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div style={{ fontSize:12, fontWeight:800, color:"#7C3AED", textTransform:"uppercase", letterSpacing:"0.05em", marginBottom:10 }}>
          Abertura da OS → Coleta
        </div>
        {lColeta ? <Skeleton h={140}/> : osColetaPorRecepcao.length === 0 ? (
          <div style={{ padding:"20px", textAlign:"center", color:C.faint, fontSize:12 }}>Sem coletas com OS registrada no período</div>
        ) : (
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))", gap:14 }}>
            {RECEPCOES_LAB_PRODUCAO.map(rc => {
              const r = osColetaPorRecepcao.find(x => x.recepcao_cod === rc.cod);
              const cor = RECEPCAO_LAB_CORES[rc.cod] || "#64748B";
              return (
                <div key={rc.cod} style={{
                  background:`linear-gradient(135deg, ${cor}22 0%, ${cor}0A 100%)`,
                  borderRadius:12, padding:"16px 18px", border:`1.5px solid ${cor}35`,
                }}>
                  <div style={{ fontSize:13, fontWeight:800, color:"#111827", marginBottom:12 }}>{rc.nome}</div>
                  <div style={{ fontSize:10, color:cor, fontWeight:800, textTransform:"uppercase", letterSpacing:"0.05em" }}>Tempo médio</div>
                  <div style={{ fontSize:28, fontWeight:900, color:cor, lineHeight:1.15 }}>{r ? min(r.tempo_medio_min) : "—"}</div>
                  <div style={{ fontSize:11, color:"#6B7280", marginTop:10, fontWeight:600 }}>
                    {r ? `${num(r.amostras)} amostras · min ${min(r.tempo_min_min)} · max ${min(r.tempo_max_min)}` : "sem amostras no período"}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Produção por Recepção — Diagnóstico, Consultórios, Ocupacional, Censo Imagem */}
      <Card title="Produção por Recepção" subtitle="Faturamento, OS e pacientes de exames laboratoriais, por ponto de recepção" style={{ marginBottom:16 }}>
        {lRecep ? <Skeleton h={160}/> : (
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(200px,1fr))", gap:14 }}>
            {RECEPCOES_LAB_PRODUCAO.map(rc => {
              const r = porRecepcao.find(x => x.recepcao_cod === rc.cod) || {};
              const cor = RECEPCAO_LAB_CORES[rc.cod] || "#64748B";
              return (
                <div key={rc.cod} style={{
                  background:`linear-gradient(135deg, ${cor}22 0%, ${cor}0A 100%)`,
                  borderRadius:12, padding:"16px 18px", border:`1.5px solid ${cor}35`,
                }}>
                  <div style={{ fontSize:13, fontWeight:800, color:"#111827", marginBottom:12 }}>{rc.nome}</div>
                  <div style={{ marginBottom:14 }}>
                    <div style={{ fontSize:10, color:cor, fontWeight:800, textTransform:"uppercase", letterSpacing:"0.05em" }}>Produção</div>
                    <div style={{ fontSize:fitFontSize(brl(r.faturamento),28,18), fontWeight:900, color:cor, lineHeight:1.15 }}>{brl(r.faturamento)}</div>
                  </div>
                  <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:8 }}>
                    <div>
                      <div style={{ fontSize:10, color:"#6B7280", fontWeight:800, textTransform:"uppercase" }}>OS</div>
                      <div style={{ fontSize:22, fontWeight:900, color:"#111827" }}>{num(r.total_os)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize:10, color:"#6B7280", fontWeight:800, textTransform:"uppercase" }}>Pacientes</div>
                      <div style={{ fontSize:22, fontWeight:900, color:"#111827" }}>{num(r.pacientes)}</div>
                    </div>
                  </div>
                  <div style={{ fontSize:11, color:"#6B7280", marginTop:10, fontWeight:600 }}>{num(r.total_exames)} exames · ticket {brl(r.ticket_medio)}</div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* Por Bancada — interno vs. laboratório de apoio (externo) */}
      <Card title="Por Bancada" subtitle="Processamento interno vs. Laboratório de Apoio (externo)" style={{ marginBottom:16 }}>
        {lBanc ? <Skeleton h={220}/> : bancadas.length === 0 ? (
          <div style={{ padding:"32px", textAlign:"center", color:C.faint, fontSize:12 }}>Sem exames vinculados a bancada no período</div>
        ) : (
          <>
            <div style={{ marginBottom:18 }}>
              <div style={{ display:"flex", flexDirection:"column", gap:14, marginBottom:12 }}>
                <div>
                  <div style={{ fontSize:11, fontWeight:800, color:"#111827", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>
                    💰 Por valor faturado
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6, fontSize:12 }}>
                    <span style={{ color:"#059669", fontWeight:800 }}>🏠 Interno {(100 - (resumoBanc.pct_externo_valor||0)).toFixed(1)}%</span>
                    <span style={{ color:"#7C3AED", fontWeight:800 }}>🚚 Externo {resumoBanc.pct_externo_valor||0}%</span>
                  </div>
                  <div style={{ height:12, borderRadius:6, overflow:"hidden", display:"flex", background:"#F1F5F9" }}>
                    <div style={{ width:`${100-(resumoBanc.pct_externo_valor||0)}%`, background:"linear-gradient(90deg,#059669,#10B981)" }}/>
                    <div style={{ width:`${resumoBanc.pct_externo_valor||0}%`, background:"linear-gradient(90deg,#7C3AED,#8B5CF6)" }}/>
                  </div>
                  <div style={{ fontSize:12, color:"#374151", fontWeight:600, marginTop:6 }}>
                    <span style={{ color:"#059669", fontWeight:800 }}>{brl(resumoBanc.interno_valor)}</span> interno vs{" "}
                    <span style={{ color:"#7C3AED", fontWeight:800 }}>{brl(resumoBanc.externo_valor)}</span> externo
                  </div>
                </div>
                <div>
                  <div style={{ fontSize:11, fontWeight:800, color:"#111827", textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:8 }}>
                    🧪 Por quantidade de exames
                  </div>
                  <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6, fontSize:12 }}>
                    <span style={{ color:"#059669", fontWeight:800 }}>🏠 {num(resumoBanc.interno_qtd)} exames</span>
                    <span style={{ color:"#7C3AED", fontWeight:800 }}>🚚 {num(resumoBanc.externo_qtd)} exames</span>
                  </div>
                  <div style={{ height:12, borderRadius:6, overflow:"hidden", display:"flex", background:"#F1F5F9" }}>
                    <div style={{ width:`${100-(resumoBanc.pct_externo_qtd||0)}%`, background:"linear-gradient(90deg,#059669,#10B981)" }}/>
                    <div style={{ width:`${resumoBanc.pct_externo_qtd||0}%`, background:"linear-gradient(90deg,#7C3AED,#8B5CF6)" }}/>
                  </div>
                  <div style={{ fontSize:12, color:"#374151", fontWeight:600, marginTop:6 }}>
                    <span style={{ color:"#7C3AED", fontWeight:800 }}>{resumoBanc.pct_externo_qtd||0}%</span> dos exames foram externos
                  </div>
                </div>
              </div>
            </div>
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(190px,1fr))", gap:10 }}>
              {bancadas.map(b => {
                const cor = b.tipo === "externo" ? "#7C3AED" : "#059669";
                return (
                  <div key={b.codigo} style={{
                    background:`linear-gradient(135deg, ${cor}22 0%, ${cor}0A 100%)`,
                    borderRadius:12, padding:"12px 14px", border:`1.5px solid ${cor}35`,
                  }}>
                    <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:8 }}>
                      <span style={{ fontSize:12, fontWeight:800, color:"#111827" }}>{b.nome}</span>
                      <span style={{ fontSize:9, fontWeight:800, color:"#fff", background:cor, borderRadius:5, padding:"2px 6px", whiteSpace:"nowrap" }}>
                        {b.tipo === "externo" ? "EXTERNO" : "INTERNO"}
                      </span>
                    </div>
                    <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-end", gap:8 }}>
                      <div>
                        <div style={{ fontSize:9, color:cor, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.05em" }}>Valor</div>
                        <div style={{ fontSize:fitFontSize(brl(b.valor),18,12), fontWeight:900, color:cor, lineHeight:1.15 }}>{brl(b.valor)}</div>
                      </div>
                      <div style={{ textAlign:"right" }}>
                        <div style={{ fontSize:9, color:cor, fontWeight:700, textTransform:"uppercase", letterSpacing:"0.05em" }}>Exames</div>
                        <div style={{ fontSize:18, fontWeight:900, color:"#111827", lineHeight:1.15 }}>{num(b.qtd_exames)}</div>
                      </div>
                    </div>
                    <div style={{ fontSize:10, color:"#6B7280", marginTop:6 }}>{num(b.pacientes)} pacientes</div>
                  </div>
                );
              })}
            </div>
            {resumoBanc.nao_classificado_qtd > 0 && (
              <div style={{ fontSize:11, color:"#B45309", marginTop:10, fontWeight:600 }}>
                ℹ {num(resumoBanc.nao_classificado_qtd)} exames sem bancada vinculada no Pixeon foram somados no card{" "}
                <b>DIAGNOSTICOS DO BRASIL</b> acima.{" "}
                <span onClick={()=>setVerNaoClassificados(v=>!v)} style={{ color:"#D97706", fontWeight:700, cursor:"pointer", textDecoration:"underline" }}>
                  {verNaoClassificados ? "▲ ocultar lista" : "▼ ver quais exames"}
                </span>
              </div>
            )}

            {verNaoClassificados && (
              <div style={{ marginTop:16, background:"#FFFBEB", border:"1.5px solid #FDE68A", borderRadius:12, padding:"14px 16px" }}>
                <div style={{ fontSize:12, fontWeight:800, color:"#92400E", marginBottom:2 }}>⚠ Exames sem bancada vinculada</div>
                <div style={{ fontSize:11, color:"#B45309", marginBottom:10 }}>
                  Esses códigos de exame precisam ser cadastrados na tela "Bancadas" do Pixeon (vínculo exame → bancada) pra entrarem na classificação interno/externo.
                </div>
                <div style={{ overflowX:"auto" }}>
                  <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                    <thead>
                      <tr style={{ borderBottom:"1.5px solid #FDE68A" }}>
                        <th style={{ textAlign:"left", padding:"6px 8px", color:"#92400E", fontWeight:800 }}>Código</th>
                        <th style={{ textAlign:"left", padding:"6px 8px", color:"#92400E", fontWeight:800 }}>Exame</th>
                        <th style={{ textAlign:"right", padding:"6px 8px", color:"#92400E", fontWeight:800 }}>Qtd</th>
                        <th style={{ textAlign:"right", padding:"6px 8px", color:"#92400E", fontWeight:800 }}>Pacientes</th>
                        <th style={{ textAlign:"right", padding:"6px 8px", color:"#92400E", fontWeight:800 }}>Valor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {naoClassificados.map((n,i) => (
                        <tr key={i} style={{ borderBottom:"1px solid #FEF3C7" }}>
                          <td style={{ padding:"6px 8px", fontFamily:"monospace", fontWeight:700, color:"#78350F" }}>{n.codigo}</td>
                          <td style={{ padding:"6px 8px", color:"#78350F", maxWidth:260, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }} title={n.nome}>{n.nome || "—"}</td>
                          <td style={{ padding:"6px 8px", textAlign:"right", fontWeight:700, color:"#78350F" }}>{num(n.qtd_exames)}</td>
                          <td style={{ padding:"6px 8px", textAlign:"right", color:"#92400E" }}>{num(n.pacientes)}</td>
                          <td style={{ padding:"6px 8px", textAlign:"right", fontWeight:700, color:"#78350F" }}>{brl(n.valor)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        )}
      </Card>

      {/* Top exames + Gráficos */}
      {/* Gráfico combinado largura total */}
      <Card title="Produção e Volume por Dia" subtitle="Barras = R$ faturado · Linha = nº de OSs" style={{ marginBottom:16 }}>
        {loading ? <Skeleton h={220}/> : !(data?.por_dia?.length) ? (
          <div style={{ padding:"40px", textAlign:"center", color:C.faint, fontSize:12 }}>Sem dados no período</div>
        ) : (
          <ResponsiveContainer width="100%" height={220}>
            <ComposedChart data={data.por_dia} barSize={18} margin={{top:4,right:20,bottom:0,left:0}}>
              <defs>
                <linearGradient id="gradLab" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%"  stopColor="#8B1A1A" stopOpacity={0.85}/>
                  <stop offset="95%" stopColor="#8B1A1A" stopOpacity={0.25}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false}/>
              <XAxis dataKey="data" tick={{fontSize:11,fill:"#9CA3AF"}} axisLine={false} tickLine={false}
                tickFormatter={v=>v?.slice(5)} interval="preserveStartEnd"/>
              <YAxis yAxisId="val" tickFormatter={v=>`R$${(v/1000).toFixed(0)}k`}
                tick={{fontSize:11,fill:"#9CA3AF"}} axisLine={false} tickLine={false} width={56}/>
              <YAxis yAxisId="os" orientation="right"
                tick={{fontSize:11,fill:"#9CA3AF"}} axisLine={false} tickLine={false} width={36}/>
              <Tooltip content={<CTip fmt={v => typeof v === 'number' && v > 100
                ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : v}/>}/>
              <Legend iconSize={11} wrapperStyle={{fontSize:12,color:"#374151",paddingTop:8}}/>
              <Bar yAxisId="val" dataKey="valor" fill="url(#gradLab)" radius={[4,4,0,0]} name="Produção"/>
              <Line yAxisId="os" type="monotone" dataKey="qtd_os" stroke="#10B981" strokeWidth={2.5}
                dot={{r:3,fill:"#10B981",strokeWidth:0}} name="OSs"/>
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Convênios em baixo */}
      <Card title="Por Convênio" subtitle="Top convênios — faturamento no período" style={{ marginBottom:16 }}>
        {loading ? <Skeleton h={200}/> : <ConvenioBar data={data?.por_convenio}/>}
      </Card>

      {/* Top exames — ranking visual */}
      {topExames.length > 0 && (
        <Card title="Top Exames Realizados" subtitle="Exames mais solicitados no período" accent="#10B981" style={{ marginBottom:16 }}>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(165px,1fr))", gap:10 }}>
            {topExames.slice(0,10).map((ex,i) => {
              const max = topExames[0]?.qtd || 1;
              const pctW = Math.max(6, (ex.qtd/max)*100);
              const cor = ["#10B981","#0891B2","#8B5CF6","#F59E0B","#EF4444","#DB2777","#D97706","#6366F1","#14B8A6","#059669"][i] || "#10B981";
              return (
                <div key={i} style={{
                  background:`linear-gradient(135deg, ${cor}12 0%, ${cor}04 100%)`,
                  borderRadius:12, padding:"14px 15px",
                  border:`1.5px solid ${cor}22`,
                  position:"relative",
                }}>
                  <div style={{
                    position:"absolute", top:10, right:12,
                    width:24, height:24, borderRadius:8,
                    background: cor, color:"#fff",
                    display:"flex", alignItems:"center", justifyContent:"center",
                    fontSize:11, fontWeight:900,
                  }}>{i+1}</div>
                  <div style={{ fontSize:12, fontFamily:"monospace", fontWeight:900, color:cor, marginBottom:4 }}>{ex.exame_cod}</div>
                  <div style={{ fontSize:22, fontWeight:900, color:"#111827", lineHeight:1, marginBottom:6 }}>{num(ex.qtd)}</div>
                  <div style={{ height:4, background:`${cor}18`, borderRadius:3, overflow:"hidden" }}>
                    <div style={{ height:"100%", width:`${pctW}%`, background:`linear-gradient(90deg,${cor}70,${cor})`, transition:"width 0.8s" }}/>
                  </div>
                  <div style={{ fontSize:10, color:cor, fontWeight:700, marginTop:4 }}>{pctW.toFixed(0)}% do 1º</div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Recoleta */}
      <DashboardRecoleta periodo={periodoEfetivo} setor={setor}/>

      {/* Top Médicos */}
      <div style={{ marginTop:16 }}>
        <Card title="Top Médicos — Laboratório" subtitle="Clique na coluna para ordenar · padrão: maior faturamento">
          {loading ? <Skeleton h={280}/> : <TabelaMedicosLab medicos={data?.top_medicos}/>}
        </Card>
      </div>

      {/* Produção por Profissional */}
      <div style={{ marginTop:16 }}>
        <Card title="Produção por Profissional" subtitle="Quem lançou/registrou o exame na OS (recepção) · não há registro de quem fisicamente colhe a amostra nesta base">
          {lProfissional ? <Skeleton h={280}/> : <TabelaMedicosLab medicos={producaoProfissional} labelColuna="Profissional" semDadosTexto="Sem dados de profissional no período"/>}
        </Card>
      </div>
    </div>
  );
}


// ── MÓDULO AGENDAMENTOS ───────────────────────────────────────────────────────

function TabelaMedicosAgenda({ medicos, periodo }) {
  const [aberto, setAberto] = useState(null);
  const [detalhe, setDetalhe] = useState({});
  const [loadDet, setLoadDet] = useState({});
  const brl = v => v!=null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";
  const num = v => v!=null ? Number(v).toLocaleString("pt-BR") : "—";
  const pct = v => v!=null ? `${Number(v).toFixed(1)}%` : "—";
  const API = `${window.location.protocol}//${window.location.host}`;

  const toggleMedico = async (m, i) => {
    const key = i;
    if (aberto === key) { setAberto(null); return; }
    setAberto(key);
    if (!detalhe[key]) {
      setLoadDet(l => ({...l, [key]: true}));
      try {
        const r = await fetch(`${API}/api/modulo/agendamentos/medico-detalhe?psv_cod=${m.psv_cod}&periodo=${periodo}`);
        const d = await r.json();
        setDetalhe(prev => ({...prev, [key]: d}));
      } catch(e) {}
      setLoadDet(l => ({...l, [key]: false}));
    }
  };

  // ← MUDANÇA 1: adicionado "Encaixe" entre "Faltantes" e "Cancelados"
  const cols = ["#","Médico","Turno","Vagas","Agendados","Atendidos","Faltantes","Encaixe","Cancelados","Abs.%"];

  return (
    <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
      <thead>
        <tr style={{ background:"#F2F2F2", borderBottom:"1px solid #E5E7EB" }}>
          {cols.map(h=>(
            <th key={h} style={{ padding:"9px 12px", fontWeight:700, color:"#6B7280",
              textAlign:h==="#"||h==="Médico"?"left":"right",
              fontSize:10, textTransform:"uppercase", whiteSpace:"nowrap" }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {medicos.map((m,i) => (
          <>
            <tr key={i}
              onClick={() => toggleMedico(m, i)}
              style={{ borderBottom:"1px solid #E5E7EB", cursor:"pointer",
                background: aberto===i ? "#FDF2F2" : "transparent",
                transition:"background 0.15s" }}
              onMouseEnter={ev=>{ if(aberto!==i) ev.currentTarget.style.background="#F2F2F2"; }}
              onMouseLeave={ev=>{ if(aberto!==i) ev.currentTarget.style.background="transparent"; }}>
              <td style={{ padding:"10px 12px", color:"#9CA3AF", fontWeight:700 }}>{i+1}</td>
              <td style={{ padding:"10px 12px", fontWeight:700, color:"#111827", whiteSpace:"nowrap" }}>
                <span style={{ marginRight:6, fontSize:10 }}>{aberto===i?"▲":"▼"}</span>
                {m.medico||m.nome_completo}
              </td>
              {/* Turno */}
              <td style={{ padding:"10px 12px", textAlign:"center" }}>
                <span style={{
                  fontSize:10, fontWeight:700, padding:"2px 8px", borderRadius:10,
                  background: m.turno==="manha" ? "#FEF3C7" : "#EDE9FE",
                  color: m.turno==="manha" ? "#D97706" : "#7C3AED",
                }}>
                  {m.turno==="manha" ? "☀ Manhã" : m.turno==="tarde" ? "🌙 Tarde" : "—"}
                </span>
              </td>
              {/* Vagas */}
              <td style={{ padding:"10px 12px", textAlign:"right", color:"#6B7280" }}>
                {num(m.vagas_disp)}
              </td>
              {/* Agendados */}
              <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:600, color:"#7C3AED" }}>
                {num(m.marcacoes)}
              </td>
              {/* Atendidos */}
              <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:700, color:"#10B981" }}>
                {num(m.atendidos)}
              </td>
              {/* Faltantes */}
              <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:600, color:"#F59E0B" }}>
                {num(m.faltantes)}
              </td>

              {/* ← MUDANÇA 2: nova célula Encaixe */}
              <td style={{ padding:"10px 12px", textAlign:"right" }}>
                {(m.encaixe || 0) > 0 ? (
                  <span style={{
                    display:"inline-flex", alignItems:"center", justifyContent:"center",
                    padding:"2px 9px", borderRadius:12, fontSize:11, fontWeight:700,
                    background:"#EDE9FE", color:"#7C3AED", border:"1px solid #DDD6FE",
                  }}>
                    +{num(m.encaixe)}
                  </span>
                ) : (
                  <span style={{ color:"#D1D5DB", fontSize:12 }}>—</span>
                )}
              </td>

              {/* Cancelados */}
              <td style={{ padding:"10px 12px", textAlign:"right", color:"#EF4444", fontWeight:600 }}>
                {num(m.cancelados)}
              </td>
              {/* Taxa Absenteísmo */}
              <td style={{ padding:"10px 12px", textAlign:"right" }}>
                {(() => {
                  const base = (m.marcacoes||0);
                  const taxa_abs = base > 0 ? ((m.faltantes||0) / base * 100) : 0;
                  const cor = taxa_abs <= 10 ? "#D1FAE5" : taxa_abs <= 25 ? "#FEF3C7" : "#FEE2E2";
                  const txt = taxa_abs <= 10 ? "#059669" : taxa_abs <= 25 ? "#D97706" : "#DC2626";
                  return (
                    <span style={{ padding:"2px 8px", borderRadius:12, fontSize:11, fontWeight:700,
                      background:cor, color:txt }}>
                      {taxa_abs.toFixed(1)}%
                    </span>
                  );
                })()}
              </td>
            </tr>

            {/* Dropdown detalhamento por convênio */}
            {/* ← MUDANÇA 3: colSpan de 8 → 9 por causa da nova coluna */}
            {aberto === i && (
              <tr key={`det-${i}`}>
                <td colSpan={9} style={{ padding:0, background:"#F0F7FF",
                  borderBottom:"2px solid #BFDBFE" }}>
                  <div style={{ padding:"12px 48px" }}>
                    <div style={{ fontSize:11, fontWeight:700, color:"#6B1010",
                      textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:10 }}>
                      📊 Atendimentos por Convênio — {m.medico}
                    </div>
                    {loadDet[i] ? (
                      <div style={{ color:"#94A3B8", fontSize:12 }}>Carregando...</div>
                    ) : !detalhe[i]?.length ? (
                      <div style={{ color:"#94A3B8", fontSize:12 }}>Sem atendimentos com OS no período</div>
                    ) : (
                      <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                        <thead>
                          <tr>
                            {["Convênio","Atendimentos","Pacientes","Produção"].map(h=>(
                              <th key={h} style={{ padding:"6px 12px", textAlign:h==="Convênio"?"left":"right",
                                color:"#6B7280", fontSize:10, fontWeight:700, textTransform:"uppercase",
                                borderBottom:"1px solid #BFDBFE" }}>{h}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {detalhe[i].map((d,j) => {
                            const maxProd = detalhe[i][0]?.producao || 1;
                            return (
                              <tr key={j} style={{ borderBottom:"1px solid #DBEAFE" }}>
                                <td style={{ padding:"7px 12px", fontWeight:600, color:"#6B1010" }}>
                                  {d.convenio}
                                </td>
                                <td style={{ padding:"7px 12px", textAlign:"right", color:"#374151" }}>
                                  {num(d.atendimentos)}
                                </td>
                                <td style={{ padding:"7px 12px", textAlign:"right", color:"#374151" }}>
                                  {num(d.pacientes)}
                                </td>
                                <td style={{ padding:"7px 12px", textAlign:"right" }}>
                                  <div style={{ display:"flex", alignItems:"center", justifyContent:"flex-end", gap:8 }}>
                                    <div style={{ width:60, height:5, background:"#F5E0E0", borderRadius:3, overflow:"hidden" }}>
                                      <div style={{ height:"100%", background:"#8B1A1A", borderRadius:3,
                                        width:`${Math.max(3,(d.producao/maxProd)*100)}%` }}/>
                                    </div>
                                    <span style={{ fontWeight:700, color:"#7A1515", minWidth:80, textAlign:"right" }}>
                                      {brl(d.producao)}
                                    </span>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                          <tr style={{ background:"#F5E0E0" }}>
                            <td style={{ padding:"7px 12px", fontWeight:800, color:"#6B1010" }}>Total</td>
                            <td style={{ padding:"7px 12px", textAlign:"right", fontWeight:800, color:"#6B1010" }}>
                              {num(detalhe[i].reduce((s,d)=>s+(d.atendimentos||0),0))}
                            </td>
                            <td style={{ padding:"7px 12px", textAlign:"right", fontWeight:800, color:"#6B1010" }}>
                              {num(detalhe[i].reduce((s,d)=>s+(d.pacientes||0),0))}
                            </td>
                            <td style={{ padding:"7px 12px", textAlign:"right", fontWeight:800, color:"#6B1010" }}>
                              {brl(detalhe[i].reduce((s,d)=>s+(d.producao||0),0))}
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    )}
                  </div>
                </td>
              </tr>
            )}
          </>
        ))}
      </tbody>
    </table>
  );
}


function SecaoModuloAgendamentos({ periodo }) {
  const { data, loading, error } = useFetch("/api/modulo/agendamentos/resumo", { periodo }, 30000);
  const { data: hoje, loading: lH } = useFetch("/api/modulo/agendamentos/resumo-hoje", {}, 30000);
  const [fullscreen, setFullscreen] = useState(false);
  const [showCnvModal, setShowCnvModal] = useState(false);
  const [cnvData, setCnvData] = useState([]);
  const [loadCnv, setLoadCnv] = useState(false);
  const API = `${window.location.protocol}//${window.location.host}`;
  const s  = data?.stats || {};
  const sh = hoje?.stats || {};
  const v  = data?.variacoes || {};
  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";
  const pct = v => v != null ? `${Number(v).toFixed(1)}%` : "—";
  const brl = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v) : "—";

  const taxaHoje = sh.marcacoes > 0 ? ((sh.faltantes||0) / sh.marcacoes * 100) : 0;
  const taxaCorH = taxaHoje <= 10 ? "#059669" : taxaHoje <= 25 ? "#D97706" : "#DC2626";
  const pctAtendH = sh.marcacoes > 0 ? ((sh.atendidos||0) / sh.marcacoes * 100) : 0;

  const abrirCnvModal = async () => {
    setShowCnvModal(true);
    if (cnvData.length) return;
    setLoadCnv(true);
    try {
      const r = await fetch(`${API}/api/modulo/agendamentos/producao-hoje-convenio`);
      setCnvData(await r.json());
    } catch(e) {}
    setLoadCnv(false);
  };

  return (
    <div style={{ animation:"fadeIn 0.35s ease" }}>
      {error && <Err msg={error.message}/>}

      <ModuleHero
        title="Agendamentos"
        subtitle={`Período: ${periodoParaLabel(periodo)} · Agenda médica · Comparecimento · Absenteísmo`}
        cor="#7C3AED"
        loading={loading}
        stats={[
          { label:"Marcações",     value: num(s.marcacoes||s.total),  sub: `de ${num(s.total)} slots`, trend: v.marcacoes },
          { label:"Compareceram",  value: num(s.executados),          sub: `${pct(s.taxa_exec)} de exec.`, trend: v.executados },
          { label:"Via Agenda",    value: num(s.com_os_vinculada),    sub: "recepcionados" },
          { label:"Cancelados",    value: num(s.cancelados),          sub: null, trend: v.cancelados },
        ]}
      />

      <BriefingCard
        cor="#7C3AED"
        cacheKey={`briefing_agendamentos_${periodoParaLabel(periodo)}`}
        disabled={loading}
        promptFn={() => `Você é um analista de gestão de agenda médica. Gere um briefing executivo em no máximo 4 frases, direto e profissional, sem markdown.

DADOS — Agendamentos (período: ${periodoParaLabel(periodo)}):
- Marcações: ${s?.marcacoes ?? s?.total ?? "n/d"} | Compareceram: ${s?.executados ?? "n/d"} (${pct(s?.taxa_exec)})
- Recepcionados via agenda: ${s?.com_os_vinculada ?? "n/d"} | Cancelados: ${s?.cancelados ?? "n/d"}

Destaque tendências de absenteísmo, eficiência da agenda e pontos de atenção operacional.`}
      />

      {/* ── RESUMO DO DIA ── */}
      <div style={{ background:"linear-gradient(135deg,#0F172A,#1E293B)", borderRadius:16,
        padding:"20px 24px", marginBottom:20, border:"1px solid #334155" }}>
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16 }}>
          <div>
            <div style={{ fontSize:13, color:"#94A3B8", fontWeight:700, textTransform:"uppercase",
              letterSpacing:"0.07em" }}>📅 Agenda de Hoje</div>
            <div style={{ fontSize:11, color:"#475569", marginTop:2 }}>
              {new Date().toLocaleDateString("pt-BR",{weekday:"long",day:"numeric",month:"long"})}
            </div>
          </div>
          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
            <span style={{ fontSize:11, color:"#475569" }}>{num(sh.medicos_agenda)} médicos</span>
            <button onClick={()=>setFullscreen(true)}
              style={{ background:"#1E293B", border:"1px solid #334155", borderRadius:8,
                color:"#94A3B8", padding:"6px 12px", cursor:"pointer", fontSize:12,
                display:"flex", alignItems:"center", gap:6 }}>
              ⛶ Expandir
            </button>
          </div>
        </div>

        {/* KPIs do dia */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))", gap:12, marginBottom:16 }}>
          {[
            { label:"Total Horários",    val:num(sh.total_horarios), cor:"#64748B", icon:"📋",
              sub: sh.vagas_disp > 0 ? `${num(sh.vagas_disp)} disponíveis` : null },
            { label:"Marcações",         val:num(sh.marcacoes),   cor:"#7C3AED", icon:"📌" },
            { label:"Atendidos",         val:num(sh.atendidos),   cor:"#10B981", icon:"✅" },
            { label:"Faltantes",         val:num(sh.faltantes),   cor:"#F59E0B", icon:"⚠️" },
            { label:"Cancelados",        val:num(sh.cancelados),  cor:"#EF4444", icon:"❌" },
          ].map((k,i) => (
            <div key={i} style={{ background:"#0F172A", borderRadius:10, padding:"12px 14px",
              borderTop:`2px solid ${k.cor}` }}>
              <div style={{ fontSize:10, color:"#64748B", fontWeight:700, marginBottom:4 }}>{k.icon} {k.label}</div>
              <div style={{ fontSize:22, fontWeight:900, color:k.cor }}>{lH ? "…" : k.val}</div>
              {k.sub && <div style={{ fontSize:10, color:"#475569", marginTop:2 }}>{k.sub}</div>}
            </div>
          ))}
        </div>

        {/* Produção hoje + Previsão */}
        {!lH && (
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:12, marginBottom:14 }}>
            {/* Produção dos agendados — clicável */}
            <div onClick={abrirCnvModal}
              style={{ background:"#0F172A", borderRadius:10, padding:"12px 16px",
              border:"1px solid #134E4A", display:"flex", justifyContent:"space-between",
              alignItems:"center", cursor:"pointer", transition:"border 0.2s" }}
              onMouseEnter={e=>e.currentTarget.style.border="1px solid #10B981"}
              onMouseLeave={e=>e.currentTarget.style.border="1px solid #134E4A"}>
              <div>
                <div style={{ fontSize:10, color:"#10B981", fontWeight:700, textTransform:"uppercase",
                  letterSpacing:"0.07em", marginBottom:2 }}>📊 Produção dos Agendados</div>
                <div style={{ fontSize:11, color:"#64748B" }}>
                  {num(sh.atendidos)} atendidos · clique para ver por convênio
                </div>
              </div>
              <div style={{ textAlign:"right" }}>
                <div style={{ fontSize:24, fontWeight:900, color:"#10B981" }}>
                  {brl(sh.producao_hoje||0)}
                </div>
                <div style={{ fontSize:10, color:"#334155" }}>🔍 ver convênios</div>
              </div>
            </div>
            {/* Previsão: produção atual + faltantes × ticket */}
            <div style={{ background:"#0F172A", borderRadius:10, padding:"12px 16px",
              border:"1px solid #1E3A5F" }}>
              <div style={{ display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:6 }}>
                <div>
                  <div style={{ fontSize:10, color:"#8B1A1A", fontWeight:700, textTransform:"uppercase",
                    letterSpacing:"0.07em", marginBottom:2 }}>💡 Previsão Final do Dia</div>
                  <div style={{ fontSize:11, color:"#64748B" }}>
                    Atual + {num(sh.faltantes)} pendentes × ticket 30d
                  </div>
                </div>
                <div style={{ textAlign:"right" }}>
                  <div style={{ fontSize:24, fontWeight:900, color:"#8B1A1A" }}>
                    {brl((sh.producao_hoje||0) + (sh.faltantes||0) * (sh.ticket_medio_30d||0))}
                  </div>
                  <div style={{ fontSize:10, color:"#475569" }}>
                    ticket médio: {brl(sh.ticket_medio_30d||0)}
                  </div>
                </div>
              </div>
              {/* Barra: atual vs previsão */}
              {(() => {
                const total = (sh.producao_hoje||0) + (sh.faltantes||0) * (sh.ticket_medio_30d||0);
                const pctAtual = total > 0 ? ((sh.producao_hoje||0) / total * 100) : 0;
                return (
                  <div style={{ height:5, background:"#1E293B", borderRadius:3, overflow:"hidden" }}>
                    <div style={{ height:"100%", background:"#10B981", borderRadius:3,
                      width:`${pctAtual}%`, transition:"width 0.5s" }}/>
                  </div>
                );
              })()}
            </div>
          </div>
        )}

        {/* Barra de progresso do dia + absenteísmo */}
        <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16 }}>
          {/* Progresso atendimentos */}
          <div>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6 }}>
              <span style={{ fontSize:11, color:"#94A3B8" }}>Progresso do dia</span>
              <span style={{ fontSize:11, fontWeight:700, color:"#10B981" }}>
                {lH ? "…" : `${pctAtendH.toFixed(1)}% atendidos`}
              </span>
            </div>
            <div style={{ height:8, background:"#1E293B", borderRadius:4, overflow:"hidden" }}>
              <div style={{ height:"100%", background:"#10B981", borderRadius:4,
                width:`${Math.min(100,pctAtendH)}%`, transition:"width 0.5s" }}/>
            </div>
          </div>
          {/* Absenteísmo */}
          <div>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:6 }}>
              <span style={{ fontSize:11, color:"#94A3B8" }}>Absenteísmo hoje</span>
              <span style={{ fontSize:11, fontWeight:700, color:taxaCorH }}>
                {lH ? "…" : `${taxaHoje.toFixed(1)}%`}
              </span>
            </div>
            <div style={{ height:8, background:"#1E293B", borderRadius:4, overflow:"hidden" }}>
              <div style={{ height:"100%", background:taxaCorH, borderRadius:4,
                width:`${Math.min(100,taxaHoje)}%`, transition:"width 0.5s" }}/>
            </div>
          </div>
        </div>

        {/* Gráfico por hora */}
        {!lH && hoje?.por_hora?.length > 0 && (
          <div style={{ marginTop:16 }}>
            <div style={{ fontSize:10, color:"#475569", marginBottom:6, textTransform:"uppercase", letterSpacing:"0.06em" }}>
              Distribuição por hora
            </div>
            <ResponsiveContainer width="100%" height={60}>
              <ComposedChart data={hoje?.por_hora||[]} margin={{top:0,right:0,bottom:0,left:0}}>
                <XAxis dataKey="hora" tick={{fontSize:9,fill:"#475569"}} axisLine={false} tickLine={false}
                  tickFormatter={v=>`${v}h`}/>
                <Tooltip formatter={(v,n)=>[v, n==="marcacoes"?"Marcações":"Atendidos"]}
                  contentStyle={{background:"#1E293B",border:"none",borderRadius:8,fontSize:11}}
                  labelStyle={{color:"#94A3B8"}} itemStyle={{color:"#EEEEEE"}}/>
                <Bar dataKey="marcacoes" fill="#7C3AED" opacity={0.4} radius={[2,2,0,0]} barSize={14}/>
                <Bar dataKey="atendidos" fill="#10B981" opacity={0.9} radius={[2,2,0,0]} barSize={10}/>
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}

        {/* Médicos hoje — divididos por turno */}
        {!lH && hoje?.medicos_hoje?.length > 0 && (
          <div style={{ marginTop:14 }}>
            {["manha","tarde"].map(turno => {
              const lista = (hoje?.medicos_hoje||[]).filter(m => m.turno === turno);
              if (!lista.length) return null;
              return (
                <div key={turno} style={{ marginBottom:10 }}>
                  <div style={{ fontSize:10, color:"#64748B", fontWeight:700,
                    textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:6 }}>
                    {turno === "manha" ? "☀ Manhã" : "🌙 Tarde"}
                  </div>
                  <div style={{ display:"flex", flexWrap:"wrap", gap:6 }}>
                    {lista.map((m,i) => {
                      const abs = m.marcacoes > 0 ? (m.faltantes/m.marcacoes*100) : 0;
                      const cor = abs <= 10 ? "#10B981" : abs <= 25 ? "#F59E0B" : "#EF4444";
                      return (
                        <div key={i} style={{ background:"#0F172A", borderRadius:8, padding:"6px 12px",
                          border:`1px solid ${cor}30`, display:"flex", gap:8, alignItems:"center" }}>
                          <div style={{ width:6, height:6, borderRadius:"50%", background:cor, flexShrink:0 }}/>
                          <span style={{ fontSize:11, fontWeight:700, color:"#EEEEEE" }}>{m.medico}</span>
                          <span style={{ fontSize:10, color:"#64748B" }}>{m.atendidos}/{m.marcacoes}</span>
                          {m.faltantes > 0 && (
                            <span style={{ fontSize:10, color:cor, fontWeight:700 }}>{abs.toFixed(0)}%</span>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Modal Fullscreen — Agenda de Hoje */}
      {fullscreen && (
        <div style={{ position:"fixed", inset:0, background:"#0F172A", zIndex:9999,
          overflowY:"auto", padding:"24px" }}>
          <div style={{ maxWidth:1200, margin:"0 auto" }}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:20 }}>
              <div>
                <div style={{ fontSize:20, fontWeight:900, color:"#EEEEEE" }}>📅 Agenda de Hoje — Tela Cheia</div>
                <div style={{ fontSize:12, color:"#64748B" }}>
                  {new Date().toLocaleDateString("pt-BR",{weekday:"long",day:"numeric",month:"long",year:"numeric"})}
                </div>
              </div>
              <button onClick={()=>setFullscreen(false)}
                style={{ background:"#1E293B", border:"1px solid #EF4444", borderRadius:8,
                  color:"#EF4444", padding:"8px 16px", cursor:"pointer", fontSize:13, fontWeight:700 }}>
                ✕ Fechar
              </button>
            </div>

            {/* KPIs */}
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))", gap:12, marginBottom:20 }}>
              {[
                { label:"Total Horários",  val:num(sh.total_horarios), sub:`${num(sh.vagas_disp)} disponíveis`, cor:"#64748B" },
                { label:"Marcações",       val:num(sh.marcacoes),      cor:"#7C3AED" },
                { label:"Atendidos",       val:num(sh.atendidos),      cor:"#10B981" },
                { label:"Faltantes",       val:num(sh.faltantes),      cor:"#F59E0B" },
                { label:"Cancelados",      val:num(sh.cancelados),     cor:"#EF4444" },
              ].map((k,i)=>(
                <div key={i} style={{ background:"#1E293B", borderRadius:10, padding:"14px 16px",
                  borderTop:`2px solid ${k.cor}` }}>
                  <div style={{ fontSize:10, color:"#64748B", fontWeight:700, marginBottom:4 }}>{k.label}</div>
                  <div style={{ fontSize:28, fontWeight:900, color:k.cor }}>{k.val}</div>
                  {k.sub && <div style={{ fontSize:10, color:"#475569" }}>{k.sub}</div>}
                </div>
              ))}
            </div>

            {/* Produção + Previsão */}
            <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:12, marginBottom:20 }}>
              <div style={{ background:"#1E293B", borderRadius:10, padding:"14px 16px",
                border:"1px solid #134E4A", display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                <div>
                  <div style={{ fontSize:10, color:"#10B981", fontWeight:700, textTransform:"uppercase", marginBottom:4 }}>📊 Produção dos Agendados</div>
                  <div style={{ fontSize:12, color:"#64748B" }}>{num(sh.atendidos)} atendidos</div>
                </div>
                <div style={{ fontSize:28, fontWeight:900, color:"#10B981" }}>{brl(sh.producao_hoje||0)}</div>
              </div>
              <div style={{ background:"#1E293B", borderRadius:10, padding:"14px 16px", border:"1px solid #1E3A5F" }}>
                <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:8 }}>
                  <div>
                    <div style={{ fontSize:10, color:"#8B1A1A", fontWeight:700, textTransform:"uppercase", marginBottom:4 }}>💡 Previsão Final</div>
                    <div style={{ fontSize:12, color:"#64748B" }}>Atual + {num(sh.faltantes)} pendentes × ticket</div>
                  </div>
                  <div style={{ fontSize:28, fontWeight:900, color:"#8B1A1A" }}>
                    {brl((sh.producao_hoje||0) + (sh.faltantes||0)*(sh.ticket_medio_30d||0))}
                  </div>
                </div>
              </div>
            </div>

            {/* Gráfico por hora maior */}
            {hoje?.por_hora?.length > 0 && (
              <div style={{ background:"#1E293B", borderRadius:12, padding:"16px", marginBottom:20 }}>
                <div style={{ fontSize:12, color:"#94A3B8", fontWeight:700, marginBottom:12 }}>Distribuição por Hora</div>
                <ResponsiveContainer width="100%" height={120}>
                  <ComposedChart data={hoje?.por_hora||[]} margin={{top:0,right:0,bottom:0,left:0}}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false}/>
                    <XAxis dataKey="hora" tick={{fontSize:10,fill:"#475569"}} axisLine={false} tickLine={false} tickFormatter={v=>`${v}h`}/>
                    <YAxis tick={{fontSize:10,fill:"#475569"}} axisLine={false} tickLine={false} width={24}/>
                    <Tooltip formatter={(v,n)=>[v, n==="marcacoes"?"Marcações":"Atendidos"]}
                      contentStyle={{background:"#0F172A",border:"none",borderRadius:8,fontSize:12}}/>
                    <Bar dataKey="marcacoes" fill="#7C3AED" opacity={0.4} radius={[3,3,0,0]} barSize={20} name="Marcações"/>
                    <Bar dataKey="atendidos" fill="#10B981" opacity={0.9} radius={[3,3,0,0]} barSize={14} name="Atendidos"/>
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            )}

            {/* Médicos */}
            <div style={{ background:"#1E293B", borderRadius:12, padding:"16px" }}>
              <div style={{ fontSize:12, color:"#94A3B8", fontWeight:700, marginBottom:12 }}>Médicos com Agenda Hoje</div>
              <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))", gap:8 }}>
                {(hoje?.medicos_hoje||[]).map((m,i)=>{
                  const abs = m.marcacoes>0?(m.faltantes/m.marcacoes*100):0;
                  const cor = abs<=10?"#10B981":abs<=25?"#F59E0B":"#EF4444";
                  return (
                    <div key={i} style={{ background:"#0F172A", borderRadius:8, padding:"10px 14px",
                      border:`1px solid ${cor}30` }}>
                      <div style={{ fontSize:12, fontWeight:700, color:"#EEEEEE", marginBottom:6 }}>{m.medico}</div>
                      <div style={{ display:"flex", justifyContent:"space-between" }}>
                        <span style={{ fontSize:11, color:"#64748B" }}>{m.atendidos}/{m.marcacoes} atendidos</span>
                        <span style={{ fontSize:11, fontWeight:700, color:cor }}>{abs.toFixed(0)}% abs.</span>
                      </div>
                      <div style={{ marginTop:6, height:4, background:"#1E293B", borderRadius:2 }}>
                        <div style={{ height:"100%", background:"#10B981", borderRadius:2,
                          width:`${m.marcacoes>0?(m.atendidos/m.marcacoes*100):0}%` }}/>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Modal Convênios da Produção */}
      {showCnvModal && (
        <div style={{ position:"fixed", inset:0, background:"rgba(0,0,0,0.7)", zIndex:9998,
          display:"flex", alignItems:"center", justifyContent:"center" }}
          onClick={()=>setShowCnvModal(false)}>
          <div style={{ background:"#1E293B", borderRadius:16, padding:"24px", width:500,
            maxHeight:"80vh", overflowY:"auto" }} onClick={e=>e.stopPropagation()}>
            <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16 }}>
              <div style={{ fontSize:15, fontWeight:800, color:"#EEEEEE" }}>
                📊 Produção por Convênio — Hoje
              </div>
              <button onClick={()=>setShowCnvModal(false)}
                style={{ background:"none", border:"none", color:"#64748B", fontSize:18, cursor:"pointer" }}>✕</button>
            </div>
            {loadCnv ? <div style={{ color:"#64748B", textAlign:"center", padding:20 }}>Carregando...</div> : (
              <div style={{ display:"flex", flexDirection:"column", gap:8 }}>
                {cnvData.map((d,i)=>{
                  const maxV = cnvData[0]?.producao||1;
                  return (
                    <div key={i}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3 }}>
                        <span style={{ fontSize:13, fontWeight:600, color:"#EEEEEE" }}>{d.convenio}</span>
                        <div style={{ textAlign:"right" }}>
                          <span style={{ fontSize:13, fontWeight:700, color:"#10B981" }}>{brl(d.producao)}</span>
                          <span style={{ fontSize:11, color:"#64748B", marginLeft:8 }}>{num(d.atendimentos)} guias · {num(d.pacientes)} pac.</span>
                        </div>
                      </div>
                      <div style={{ height:5, background:"#0F172A", borderRadius:3 }}>
                        <div style={{ height:"100%", background:"#10B981", borderRadius:3,
                          width:`${Math.max(3,(d.producao/maxV)*100)}%` }}/>
                      </div>
                    </div>
                  );
                })}
                <div style={{ marginTop:12, paddingTop:12, borderTop:"1px solid #334155",
                  display:"flex", justifyContent:"space-between" }}>
                  <span style={{ fontSize:13, fontWeight:700, color:"#94A3B8" }}>Total</span>
                  <span style={{ fontSize:15, fontWeight:900, color:"#10B981" }}>
                    {brl(cnvData.reduce((s,d)=>s+(d.producao||0),0))}
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Aviso sobre metodologia */}
      <div style={{ background:"#FDF2F2", borderRadius:10, padding:"10px 16px", marginBottom:16,
        border:"1px solid #BFDBFE", display:"flex", gap:10, alignItems:"flex-start" }}>
        <span style={{ fontSize:16, flexShrink:0 }}>ℹ️</span>
        <div style={{ fontSize:12, color:"#6B1010" }}>
          <strong>Metodologia de comparecimento:</strong> Paciente considerado <strong>atendido</strong> quando
          possui OS gerada no mesmo dia pelo mesmo médico do agendamento — independente de o status da agenda
          ter sido atualizado. <strong>Não compareceu</strong> = agendado mas sem OS no dia pelo médico agendado.
        </div>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(160px,1fr))", gap:14, marginBottom:20 }}>
        <ModuloCard label="Marcações"         value={num(s.marcacoes||s.total)} color="#7C3AED" loading={loading} icon="calendar"
          sub={`de ${num(s.total)} slots com paciente`}/>
        <ModuloCard label="Compareceram"      value={num(s.executados)}      color="#10B981" loading={loading} icon="check"
          sub={`${pct(s.taxa_exec)} de comparecimento`}/>
        <ModuloCard label="Via Agenda"  value={num(s.com_os_vinculada)} color="#8B1A1A" loading={loading} icon="bar"
          sub="Recepcionados pela agenda"/>
        {(() => {
          const base = (s.marcacoes||s.total||0) - (s.cancelados||0) - (s.bloqueados||0);
          const taxa = base > 0 ? ((s.abertos||0) / base * 100) : 0;
          const cor = taxa <= 10 ? "#059669" : taxa <= 25 ? "#D97706" : "#DC2626";
          return (
            <div style={{
              background: `linear-gradient(135deg, ${cor}3A 0%, ${cor}14 100%)`,
              borderRadius: 16, padding: "18px 20px",
              border: `1.5px solid ${cor}55`,
              boxShadow: `0 6px 18px ${cor}22, 0 1px 4px rgba(0,0,0,0.05)`,
              position:"relative", overflow:"hidden",
            }}>
              <div style={{ position:"absolute", right:-14, top:-14, width:80, height:80, borderRadius:"50%", background:`${cor}20`, pointerEvents:"none" }}/>
              <div style={{ fontSize:10, color:cor, fontWeight:800, textTransform:"uppercase",
                letterSpacing:"0.08em", marginBottom:8 }}>⚠ Absenteísmo</div>
              {loading ? <Skeleton h={60}/> : (
                <>
                  <div style={{ fontSize:fitFontSize(`${taxa.toFixed(1)}%`,26,14), fontWeight:900, color:"#111827", lineHeight:1.15 }}>
                    {taxa.toFixed(1)}%
                  </div>
                  <div style={{ fontSize:11, color:"#6B7280", marginTop:3 }}>
                    {num(s.abertos)} pacientes · de {num(base)} marcações
                  </div>
                  <div style={{ marginTop:8, height:6, background:"#fff", borderRadius:3, overflow:"hidden" }}>
                    <div style={{ height:"100%", background:cor, borderRadius:3,
                      width:`${Math.min(100,taxa)}%`, transition:"width 0.5s" }}/>
                  </div>
                </>
              )}
            </div>
          );
        })()}
        <ModuloCard label="Cancelados"        value={num(s.cancelados)}      color="#EF4444" loading={loading} icon="activity"/>
      </div>

      <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginBottom:16 }}>
        <Card title="Volume Diário" subtitle="Agendamentos · Atendidos · Não compareceu">
          {loading ? <Skeleton h={160}/> : (
            <ResponsiveContainer width="100%" height={160}>
              <ComposedChart data={data?.por_dia||[]} barSize={10} margin={{top:4,right:8,bottom:0,left:0}}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false}/>
                <XAxis dataKey="data" tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false}
                  tickFormatter={v=>v?.slice(5)} interval="preserveStartEnd"/>
                <YAxis tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} width={28}/>
                <Tooltip content={<CTip fmt={v=>v?.toLocaleString("pt-BR")}/>}/>
                <Legend iconSize={10} wrapperStyle={{fontSize:11,paddingTop:6}}/>
                <Bar dataKey="total"           fill="#7C3AED" radius={[3,3,0,0]} name="Agendados"       opacity={0.4}/>
                <Bar dataKey="executados"      fill="#10B981" radius={[3,3,0,0]} name="Atendidos"       opacity={0.9}/>
                <Bar dataKey="nao_compareceu"  fill="#F59E0B" radius={[3,3,0,0]} name="Não compareceu"  opacity={0.8}/>
                <Bar dataKey="cancelados"      fill="#EF4444" radius={[3,3,0,0]} name="Cancelados"      opacity={0.8}/>
              </ComposedChart>
            </ResponsiveContainer>
          )}
        </Card>
        <Card title="Taxa de Execução Diária" subtitle="% executados por dia">
          {loading ? <Skeleton h={160}/> : (
            <ResponsiveContainer width="100%" height={160}>
              <LineChart data={(data?.por_dia||[]).map(d=>({ ...d, taxa:d.total>0?(d.executados/d.total*100):0 }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false}/>
                <XAxis dataKey="data" tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} tickFormatter={v=>v?.slice(5)}/>
                <YAxis tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} unit="%" domain={[0,100]}/>
                <Tooltip formatter={v=>[`${v.toFixed(1)}%`,"Taxa"]}/>
                <Line type="monotone" dataKey="taxa" stroke="#10B981" strokeWidth={2.5} dot={false}/>
              </LineChart>
            </ResponsiveContainer>
          )}
        </Card>
      </div>

      <Card title="Top Médicos por Agenda" subtitle="Vagas · Agendados · Atendidos · Faltantes · Cancelados">
        {loading ? <Skeleton h={280}/> : (
          <TabelaMedicosAgenda medicos={data?.top_medicos||[]} periodo={periodo}/>
        )}
      </Card>


    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MÓDULO CLÍNICA — agrupa Assistencial, Ocupacional, Serviços e Laboratório
// ══════════════════════════════════════════════════════════════════════════════
const ABAS_CLINICA = [
  { id: "assistencial", label: "Assistencial",    cor: "#8B1A1A" },
  { id: "ocupacional",  label: "Ocupacional",     cor: "#D97706" },
  { id: "servicos",     label: "Serviços Espec.", cor: "#8B5CF6" },
  { id: "agendamentos", label: "Agendamentos",    cor: "#7C3AED" },
];

function SecaoClinica({ periodo }) {
  const [aba, setAba] = useState("assistencial");
  const abaAtual = ABAS_CLINICA.find(a => a.id === aba);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Tabs visuais */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {ABAS_CLINICA.map(a => {
          const ativo = aba === a.id;
          return (
            <button key={a.id} onClick={() => setAba(a.id)} style={{
              padding: "9px 20px", borderRadius: 12, fontSize: 13, fontWeight: 700,
              cursor: "pointer", border: "none", transition: "all 0.15s",
              background: ativo ? a.cor : "#fff",
              color: ativo ? "#fff" : "#64748B",
              boxShadow: ativo
                ? `0 4px 16px ${a.cor}40`
                : "0 1px 3px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.05)",
              transform: ativo ? "translateY(-1px)" : "none",
            }}>{a.label}</button>
          );
        })}
      </div>
      {/* Conteúdo com animação */}
      <div key={aba} style={{ animation:"fadeIn 0.25s ease" }}>
        {aba === "assistencial" && <SecaoModuloAssistencial periodo={periodo} />}
        {aba === "ocupacional"  && <SecaoModuloOcupacional  periodo={periodo} />}
        {aba === "servicos"     && <SecaoModuloServicos     periodo={periodo} />}
        {aba === "agendamentos" && <SecaoModuloAgendamentos periodo={periodo} />}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// NAVEGAÇÃO
// ══════════════════════════════════════════════════════════════════════════════
const NAV = [
  { id: "home",       label: "Home",            icon: "home",         color: "#8B1A1A" },
  { id: "contratos",  label: "Contratos",       icon: "document",     color: "#0D9488", desc: "Gestão de contratos" },
  { id: "clinica",    label: "Clínica",         icon: "stethoscope",  color: "#8B1A1A", desc: "Assistencial · Ocupacional · Serviços · Agenda" },
  { id: "laboratorio",label: "Laboratório",     icon: "flask",        color: "#10B981", desc: "Exames · Diagnóstico · Ocupacional" },
  { id: "recepcao",   label: "Recepção",        icon: "users",        color: "#D97706", desc: "Métricas por recepcionista" },
  { id: "producao",   label: "Produção Mensal", icon: "money-trend",  color: "#0891B2", desc: "Meta e provisionamento mensal" },
  { id: "pacientesdb",label: "Pacientes DB",    icon: "users",        color: "#0891B2", desc: "Base · logradouros · ranking · aniversários" },
  { id: "estoque",    label: "Estoque",         icon: "package",      color: "#0D9488", desc: "Posição, giro e validade" },
  { id: "painel_tv",  label: "Painel TV",       icon: "monitor",      color: "#7C3AED", desc: "Tempo real · para telão" },
  { id: "admin",      label: "Permissões",      icon: "settings",     color: "#374151", desc: "Gerenciar acessos" },
];

const IconLayers = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="12 2 2 7 12 12 22 7 12 2"/>
    <polyline points="2 17 12 22 22 17"/>
    <polyline points="2 12 12 17 22 12"/>
  </svg>
);

const IconUsers = ({ size=18, color="currentColor" }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/>
    <circle cx="9" cy="7" r="4"/>
    <path d="M23 21v-2a4 4 0 00-3-3.87"/>
    <path d="M16 3.13a4 4 0 010 7.75"/>
  </svg>
);
const RENDER_MAP = {
  home:        (p) => <Home periodoGlobal={p}/>,
  admin:       ()  => <AdminPermissoes/>,
  contratos:   ()  => <ModuloContratos/>,
  clinica:     (p) => <SecaoClinica     periodo={p}/>,
  recepcao:    (p) => <Recepcao         periodo={p}/>,
  pacientesdb: (p) => <PacientesDB      periodo={p}/>,
  producao:    (p) => <SecaoProducaoMensal modulo={{}} periodoEfetivo={p}/>,
  laboratorio: (p) => <SecaoModuloLaboratorio periodo={p}/>,
  estoque:     (p) => <SecaoEstoque     periodo={p}/>,
  painel_tv:   ()  => <PainelTV/>,
};


const PERIODS = [
  { id:"hoje", label:"Hoje"      },
  { id:"30d",  label:"Mês atual" },
  { id:"ano",  label:"Ano atual" },
];

const MESES_FULL = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];

function MiniCal({ ano, mes, selecionadoIni, selecionadoFim, hover, onDayClick, onDayHover, titulo, onPrev, onNext, showPrev=true, showNext=true }) {
  const DIAS_SEM = ["D","S","T","Q","Q","S","S"];
  const hoje = new Date();
  const primeiroDia = new Date(ano, mes, 1).getDay();
  const diasNoMes = new Date(ano, mes+1, 0).getDate();
  const cells = [];
  for(let i=0; i<primeiroDia; i++) cells.push(null);
  for(let d=1; d<=diasNoMes; d++) cells.push(d);
  while(cells.length % 7 !== 0) cells.push(null);

  const toStr = (a,m,d) => `${a}-${String(m+1).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
  const isToday = (d) => d && hoje.getFullYear()===ano && hoje.getMonth()===mes && hoje.getDate()===d;
  const isIni   = (d) => d && toStr(ano,mes,d) === selecionadoIni;
  const isFim   = (d) => d && toStr(ano,mes,d) === selecionadoFim;
  const isRange = (d) => {
    if(!d || !selecionadoIni) return false;
    const s = toStr(ano,mes,d);
    const fim = selecionadoFim || hover;
    if(!fim) return false;
    const [a,b] = selecionadoIni < fim ? [selecionadoIni,fim] : [fim,selecionadoIni];
    return s > a && s < b;
  };

  return (
    <div style={{ flex:1, minWidth:200 }}>
      {/* Header */}
      <div style={{ display:"flex", alignItems:"center", justifyContent:"space-between", marginBottom:10 }}>
        {showPrev
          ? <button onClick={onPrev} style={{ width:26,height:26,borderRadius:6,border:"1px solid #E5E7EB",background:"#F9F9F9",cursor:"pointer",fontSize:13,display:"flex",alignItems:"center",justifyContent:"center" }}>‹</button>
          : <span style={{ width:26 }}/>}
        <span style={{ fontSize:13, fontWeight:700, color:"#2D1B1B" }}>
          {MESES_FULL[mes].slice(0,3)} {ano}
        </span>
        {showNext
          ? <button onClick={onNext} style={{ width:26,height:26,borderRadius:6,border:"1px solid #E5E7EB",background:"#F9F9F9",cursor:"pointer",fontSize:13,display:"flex",alignItems:"center",justifyContent:"center" }}>›</button>
          : <span style={{ width:26 }}/>}
      </div>
      {/* Dias semana */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(7,1fr)", gap:2, marginBottom:4 }}>
        {DIAS_SEM.map((d,i) => (
          <div key={i} style={{ textAlign:"center", fontSize:10, fontWeight:700, color:"#9CA3AF", padding:"2px 0" }}>{d}</div>
        ))}
      </div>
      {/* Dias */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(7,1fr)", gap:2 }}>
        {cells.map((d,i) => {
          const ini   = isIni(d);
          const fim   = isFim(d);
          const range = isRange(d);
          const today = isToday(d);
          const ds    = d ? toStr(ano,mes,d) : null;
          return (
            <div key={i}
              onClick={()=> d && onDayClick(ds)}
              onMouseEnter={()=> d && onDayHover(ds)}
              style={{
                height:30, display:"flex", alignItems:"center", justifyContent:"center",
                borderRadius: ini||fim ? 8 : range ? 0 : 6,
                borderTopLeftRadius:  ini ? 8 : range ? 0 : 6,
                borderBottomLeftRadius: ini ? 8 : range ? 0 : 6,
                borderTopRightRadius: fim ? 8 : range ? 0 : 6,
                borderBottomRightRadius: fim ? 8 : range ? 0 : 6,
                background: ini||fim ? "#8B1A1A" : range ? "#F5EAEA" : "transparent",
                color: ini||fim ? "#fff" : today ? "#8B1A1A" : d ? "#2D1B1B" : "transparent",
                fontWeight: ini||fim||today ? 700 : 400,
                fontSize:12,
                cursor: d ? "pointer" : "default",
                border: today && !ini && !fim ? "1px solid #8B1A1A" : "1px solid transparent",
                transition:"background 0.08s",
              }}>
              {d}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function SeletorPeriodo({ period, setPeriod }) {
  const now = new Date();
  const [showCustom, setShowCustom] = useState(false);
  const [mesE, setMesE] = useState(now.getMonth());
  const [anoE, setAnoE] = useState(now.getFullYear());
  const [sIni, setSIni] = useState("");
  const [sFim, setSFim] = useState("");
  const [hover, setHover] = useState("");
  const ref = useRef(null);

  // Mês direito = mês seguinte ao esquerdo
  const mesD = mesE === 11 ? 0 : mesE + 1;
  const anoD = mesE === 11 ? anoE + 1 : anoE;

  const prevMes = () => { if(mesE===0){setMesE(11);setAnoE(a=>a-1);}else setMesE(m=>m-1); };
  const nextMes = () => { if(mesE===11){setMesE(0);setAnoE(a=>a+1);}else setMesE(m=>m+1); };

  const handleDay = (ds) => {
    if(!sIni || (sIni && sFim)) { setSIni(ds); setSFim(""); setHover(""); }
    else {
      const [a,b] = sIni < ds ? [sIni,ds] : [ds,sIni];
      setSIni(a); setSFim(b); setHover("");
    }
  };

  const getLabel = () => {
    if(!period) return "Mês atual";
    if(period.startsWith("custom:")) {
      const [ini,fim] = period.slice(7).split(":");
      return `${ini.slice(5)} → ${fim.slice(5)}`;
    }
    return PERIODS.find(p=>p.id===period)?.label || "Personalizado";
  };

  const isCustomActive = period?.startsWith("custom:");

  // Close on outside click
  useEffect(() => {
    const h = (e) => { if(ref.current && !ref.current.contains(e.target)) setShowCustom(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  return (
    <div ref={ref} style={{ position:"relative" }}>
      {/* Pills */}
      <div style={{ display:"flex", background:"#ECECEC", borderRadius:8, padding:3, gap:1, border:"1px solid #E5E7EB" }}>
        {PERIODS.map(p => (
          <button key={p.id} onClick={()=>{ setPeriod(p.id); setShowCustom(false); }} style={{
            padding:"5px 11px", borderRadius:6, border:"none", cursor:"pointer", fontSize:12, fontWeight:600,
            background: period===p.id && !showCustom ? "#fff":"transparent",
            color:       period===p.id && !showCustom ? "#8B1A1A":"#9CA3AF",
            boxShadow:   period===p.id && !showCustom ? "0 1px 3px rgba(0,0,0,0.08)":"none",
            whiteSpace:"nowrap", transition:"all 0.12s",
          }}>{p.label}</button>
        ))}
        <button onClick={()=>setShowCustom(v=>!v)} style={{
          padding:"5px 11px", borderRadius:6, border:"none", cursor:"pointer", fontSize:12, fontWeight:600,
          background: showCustom || isCustomActive ? "#8B1A1A":"transparent",
          color:       showCustom || isCustomActive ? "#fff":"#9CA3AF",
          boxShadow:   showCustom || isCustomActive ? "0 1px 3px rgba(0,0,0,0.08)":"none",
          whiteSpace:"nowrap", transition:"all 0.12s", display:"flex", alignItems:"center", gap:5,
        }}>
          <span>📅</span>
          {isCustomActive ? getLabel() : "Personalizado"}
        </button>
      </div>

      {/* Dropdown calendário duplo */}
      {showCustom && (
        <div style={{
          position:"absolute", right:0, top:"calc(100% + 8px)", zIndex:9999,
          background:"#fff", borderRadius:14, boxShadow:"0 12px 40px rgba(139,26,26,0.15)",
          border:"1px solid #EDD8D8", padding:"16px 18px", minWidth:460,
        }}>
          {/* Título */}
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:14 }}>
            <span style={{ fontSize:12, fontWeight:800, color:"#8B1A1A", textTransform:"uppercase", letterSpacing:"0.08em" }}>
              Selecione o intervalo
            </span>
            {sIni && sFim && (
              <span style={{ fontSize:11, color:"#6B7280", fontWeight:600 }}>
                {sIni.slice(5)} → {sFim.slice(5)}
              </span>
            )}
          </div>

          {/* Calendários duplos */}
          <div style={{ display:"flex", gap:20, marginBottom:14 }}>
            <MiniCal
              ano={anoE} mes={mesE}
              selecionadoIni={sIni} selecionadoFim={sFim} hover={hover}
              onDayClick={handleDay} onDayHover={setHover}
              onPrev={prevMes} onNext={nextMes}
              showPrev={true} showNext={false}
            />
            <div style={{ width:1, background:"#F0E8E8", flexShrink:0 }}/>
            <MiniCal
              ano={anoD} mes={mesD}
              selecionadoIni={sIni} selecionadoFim={sFim} hover={hover}
              onDayClick={handleDay} onDayHover={setHover}
              onPrev={prevMes} onNext={nextMes}
              showPrev={false} showNext={true}
            />
          </div>

          {/* Rodapé */}
          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center",
            paddingTop:12, borderTop:"1px solid #F0E8E8" }}>
            <button onClick={()=>{ setSIni(""); setSFim(""); setHover(""); }} style={{
              background:"none", border:"none", cursor:"pointer", fontSize:12,
              color:"#9CA3AF", fontWeight:600, padding:"0 4px",
            }}>Limpar</button>
            <button
              disabled={!sIni || !sFim}
              onClick={()=>{ if(sIni&&sFim){ setPeriod(`custom:${sIni}:${sFim}`); setShowCustom(false); }}}
              style={{
                padding:"8px 24px", borderRadius:8, fontSize:13, fontWeight:700, border:"none",
                background: sIni&&sFim ? "#8B1A1A":"#E5E7EB",
                color:       sIni&&sFim ? "#fff":"#9CA3AF",
                cursor:      sIni&&sFim ? "pointer":"not-allowed",
                transition:"all 0.15s",
              }}>
              Aplicar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MÓDULO ESTOQUE
// ══════════════════════════════════════════════════════════════════════════════

function BadgeStatus({ status }) {
  const MAP = {
    ZERADO:  { bg:"#FEE2E2", color:"#DC2626", label:"Zerado"   },
    CRITICO: { bg:"#FEE2E2", color:"#DC2626", label:"Crítico"  },
    ATENCAO: { bg:"#FEF3C7", color:"#D97706", label:"Atenção"  },
    EXCESSO: { bg:"#EDE9FE", color:"#7C3AED", label:"Excesso"  },
    NORMAL:  { bg:"#D1FAE5", color:"#059669", label:"Normal"   },
    VENCIDO: { bg:"#FEE2E2", color:"#DC2626", label:"Vencido"  },
    OK:      { bg:"#D1FAE5", color:"#059669", label:"OK"       },
  };
  const s = MAP[status] || MAP.NORMAL;
  return (
    <span style={{ padding:"2px 8px", borderRadius:12, fontSize:10, fontWeight:700,
      background:s.bg, color:s.color, whiteSpace:"nowrap" }}>{s.label}</span>
  );
}

// ── TABELA POSIÇÃO ESTOQUE ────────────────────────────────────────────────────
function TabelaPosicaoEstoque({ posicao, loading, curva, setCurva, busca, setBusca }) {
  const [sortP, setSortP] = useState("valor_total");
  const [dirP,  setDirP]  = useState("desc");
  const brl = v => v!=null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";
  const num = v => v!=null ? Number(v).toLocaleString("pt-BR") : "—";
  const ABC_COR = { A:"#EF4444", B:"#F59E0B", C:"#10B981" };

  const toggleP = col => {
    if (sortP===col) setDirP(d=>d==="desc"?"asc":"desc");
    else { setSortP(col); setDirP("desc"); }
  };

  const dados = [...(posicao||[])].sort((a,b)=>{
    const va = a[sortP]??-Infinity, vb = b[sortP]??-Infinity;
    if (typeof va==="string") return dirP==="desc"?String(vb).localeCompare(String(va)):String(va).localeCompare(String(vb));
    return dirP==="desc"?(vb??-Infinity)-(va??-Infinity):(va??-Infinity)-(vb??-Infinity);
  });

  const TH = ({ col, label, tip, align="right" }) => {
    const active = sortP===col;
    return (
      <th onClick={()=>toggleP(col)} title={tip||label} style={{
        padding:"10px 12px", fontWeight:700, cursor:"pointer", userSelect:"none",
        color:active?"#111827":C.faint, textAlign:align, fontSize:11,
        textTransform:"uppercase", letterSpacing:"0.05em", whiteSpace:"nowrap",
        background:active?"#FDF2F2":"#F2F2F2", borderBottom:`1px solid ${C.border}`,
      }}>
        {label} <span style={{ opacity:active?1:0.25, fontSize:10 }}>{active?(dirP==="desc"?"↓":"↑"):"↕"}</span>
      </th>
    );
  };

  return (
    <div>
      {/* Filtros */}
      <div style={{ display:"flex", gap:10, marginBottom:16, alignItems:"center", flexWrap:"wrap" }}>
        <div style={{ display:"flex", gap:4, alignItems:"center" }}>
          <span style={{ fontSize:12, color:C.faint, fontWeight:600 }}>Curva ABC:</span>
          {["","A","B","C"].map(c=>(
            <button key={c} onClick={()=>setCurva(c)} style={{
              padding:"5px 12px", borderRadius:7, border:`1.5px solid ${curva===c?(ABC_COR[c]||C.blue):C.border}`,
              background:curva===c?(ABC_COR[c]||C.blue)+"18":"#fff",
              color:curva===c?(ABC_COR[c]||C.blue):C.faint,
              fontSize:12, fontWeight:700, cursor:"pointer",
            }}>{c||"Todos"}</button>
          ))}
        </div>
        <input placeholder="🔍 Buscar material..." value={busca} onChange={e=>setBusca(e.target.value)}
          style={{ padding:"7px 12px", borderRadius:8, border:`1px solid ${C.border}`,
            fontSize:12, outline:"none", width:240 }}/>
        <span style={{ fontSize:12, color:C.faint, marginLeft:"auto" }}>
          {dados.length} itens · clique na coluna para ordenar
        </span>
      </div>

      {loading ? <Skeleton h={400}/> : (
        <div style={{ background:"#fff", borderRadius:14, overflow:"hidden", boxShadow:"0 1px 3px rgba(0,0,0,0.06)" }}>
          <div style={{ overflowX:"auto" }}>
            <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
              <thead>
                <tr>
                  <TH col="descricao"          label="Material"          align="left" tip="Nome do material"/>
                  <TH col="curva_abc"           label="Curva"             tip="ABC: A=alto valor, B=médio, C=baixo"/>
                  <TH col="status_estoque"      label="Status"            tip="Normal / Crítico / Zerado / Excesso"/>
                  <TH col="qtd_atual"           label="Qtd. Atual"        tip="Quantidade em estoque agora"/>
                  <TH col="valor_total"         label="Valor Estoque"     tip="Qtd × Preço médio"/>
                  <TH col="preco_medio"         label="Preço Médio"       tip="Custo médio ponderado unitário"/>
                  <TH col="cobertura_dias"      label="Cobertura"         tip="Dias de estoque pelo consumo médio"/>
                  <TH col="consumo_medio"       label="Cons. Médio"       tip="Consumo médio histórico"/>
                  <TH col="ponto_ressuprimento" label="Pt. Resuprimento"  tip="Quantidade mínima para disparar recompra"/>
                  <TH col="dt_ult_entrada"      label="Últ. Entrada"      tip="Data da última entrada no estoque"/>
                  <TH col="dt_ult_saida"        label="Últ. Saída"        tip="Data da última saída do estoque"/>
                </tr>
              </thead>
              <tbody>
                {dados.map((m,i)=>{
                  const corCob = !m.cobertura_dias?"#9CA3AF":m.cobertura_dias<7?"#DC2626":m.cobertura_dias<30?"#D97706":"#059669";
                  return (
                    <tr key={i} style={{ borderBottom:`1px solid ${C.border}` }}
                      onMouseEnter={e=>e.currentTarget.style.background="#F2F2F2"}
                      onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                      <td style={{ padding:"10px 12px", fontWeight:600, color:"#111827",
                        maxWidth:220, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}
                        title={m.descricao}>{m.descricao}</td>
                      <td style={{ padding:"10px 12px", textAlign:"right" }}>
                        <span style={{ padding:"3px 9px", borderRadius:6, fontSize:11, fontWeight:800,
                          background:(ABC_COR[m.curva_abc]||"#94A3B8")+"20",
                          color:ABC_COR[m.curva_abc]||"#94A3B8" }}>{m.curva_abc||"—"}</span>
                      </td>
                      <td style={{ padding:"10px 12px", textAlign:"right" }}>
                        <BadgeStatus status={m.status_estoque}/>
                      </td>
                      <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:700,
                        color:m.qtd_atual===0?"#DC2626":"#111827" }}>{num(m.qtd_atual)}</td>
                      <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:sortP==="valor_total"?800:600,
                        color:sortP==="valor_total"?"#111827":C.sub }}>{brl(m.valor_total)}</td>
                      <td style={{ padding:"10px 12px", textAlign:"right", color:C.sub }}>{brl(m.preco_medio)}</td>
                      <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:700, color:corCob }}>
                        {m.cobertura_dias!=null?`${Number(m.cobertura_dias).toFixed(0)}d`:<span style={{color:"#D1D5DB"}}>—</span>}
                      </td>
                      <td style={{ padding:"10px 12px", textAlign:"right", color:C.sub }}>{num(m.consumo_medio)}</td>
                      <td style={{ padding:"10px 12px", textAlign:"right",
                        color:m.ponto_ressuprimento>0&&m.qtd_atual<=m.ponto_ressuprimento?"#DC2626":C.sub }}>
                        {m.ponto_ressuprimento>0?num(m.ponto_ressuprimento):<span style={{color:"#D1D5DB"}}>—</span>}
                      </td>
                      <td style={{ padding:"10px 12px", textAlign:"right", color:C.faint, fontSize:11 }}>{m.dt_ult_entrada||"—"}</td>
                      <td style={{ padding:"10px 12px", textAlign:"right", color:C.faint, fontSize:11 }}>{m.dt_ult_saida||"—"}</td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr style={{ background:"#FDF2F2", borderTop:`2px solid ${C.blue}` }}>
                  <td colSpan={3} style={{ padding:"10px 12px", fontWeight:800, color:"#111827", fontSize:12 }}>
                    TOTAL — {dados.length} itens
                  </td>
                  <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:700, color:"#111827" }}>
                    {num(dados.reduce((s,m)=>s+(m.qtd_atual||0),0))}
                  </td>
                  <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:800, color:C.blue }}>
                    {brl(dados.reduce((s,m)=>s+(m.valor_total||0),0))}
                  </td>
                  <td colSpan={6}/>
                </tr>
              </tfoot>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}


function SecaoEstoque({ periodo }) {
  const [aba,       setAba]       = useState("dashboard");
  const [curva,     setCurva]     = useState("");
  const [busca,     setBusca]     = useState("");
  const [tipoMov,   setTipoMov]   = useState("");
  const [setorSel,  setSetorSel]  = useState("");
  const [diasVenc,  setDiasVenc]  = useState(90);
  const [dataIni,   setDataIni]   = useState("2026-01-02");
  const { data: ultimoInv } = useFetch("/api/estoque/ultimo-inventario", {});
  useEffect(() => {
    if (ultimoInv?.data_inventario) setDataIni(ultimoInv.data_inventario);
  }, [ultimoInv?.data_inventario]);
  const [dataFim,   setDataFim]   = useState("");
  const [grupoCod,  setGrupoCod]  = useState("");
  const [buscaAnal, setBuscaAnal] = useState("");

  const { data: resumo,    loading: lR }   = useFetch("/api/estoque/resumo",          { periodo, data_inicio:dataIni, data_fim_est:dataFim });
  const { data: posicao,   loading: lP }   = useFetch("/api/estoque/posicao",          { curva, busca, limite:100, data_inicio:dataIni });
  const { data: giro,      loading: lG }   = useFetch("/api/estoque/giro",             { periodo, limite:100, data_inicio:dataIni });
  const { data: lotes,     loading: lL }   = useFetch("/api/estoque/lotes-vencimento", { dias:diasVenc });
  const { data: movs,      loading: lM }   = useFetch("/api/estoque/movimentacoes",    { periodo, tipo:tipoMov, data_inicio:dataIni });
  const { data: abc,       loading: lABC } = useFetch("/api/estoque/curva-abc",        { data_inicio:dataIni });
  const { data: movDia,    loading: lMD }  = useFetch("/api/estoque/mov-por-dia",      { periodo, data_inicio:dataIni });
  const { data: grupos,    loading: lGR }  = useFetch("/api/estoque/por-grupo",        { periodo, data_inicio:dataIni });
  const { data: setores,   loading: lST }  = useFetch("/api/estoque/por-setor",        { periodo, data_inicio:dataIni });
  const { data: sintetico, loading: lSIN } = useFetch("/api/estoque/sintetico", { data_inicio:dataIni, data_fim:dataFim, skip: aba!=="sintetico" && aba!=="analitico" });
  const { data: analitico, loading: lANL } = useFetch("/api/estoque/analitico", { data_inicio:dataIni, data_fim:dataFim, grupo_cod:grupoCod, busca:buscaAnal, limite:200, skip: aba!=="analitico" });

  const brl = v => v!=null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(v) : "—";
  const num = v => v!=null ? Number(v).toLocaleString("pt-BR") : "—";
  const pct = v => v!=null ? `${Number(v).toFixed(1)}%` : "—";

  const ABAS_EST = [
    { id:"dashboard",  label:"Dashboard"      },
    { id:"posicao",    label:"Posição"        },
    { id:"sintetico",  label:"Sintético"      },
    { id:"analitico",  label:"Analítico"      },
    { id:"giro",       label:"Giro"           },
    { id:"lotes",      label:"Validade/Lotes" },
    { id:"movimentos", label:"Movimentações"  },
    { id:"grupos",     label:"Por Grupo"      },
    { id:"setores",    label:"Por Setor"      },
  ];

  // Filtro de data do módulo estoque
  const FiltroDataEstoque = () => (
    <div style={{ display:"flex", alignItems:"center", gap:10, background:"#fff",
      border:`1px solid ${C.border}`, borderRadius:10, padding:"8px 14px",
      marginBottom:16, flexWrap:"wrap" }}>
      <span style={{ fontSize:12, fontWeight:700, color:"#8B1A1A" }}>📦 Período do Estoque:</span>
      <div style={{ display:"flex", alignItems:"center", gap:6 }}>
        <label style={{ fontSize:11, color:C.sub }}>De</label>
        <input type="date" value={dataIni} onChange={e=>setDataIni(e.target.value)}
          style={{ padding:"5px 10px", borderRadius:7, border:`1px solid ${C.border}`,
            fontSize:12, color:C.text, outline:"none" }}/>
      </div>
      <div style={{ display:"flex", alignItems:"center", gap:6 }}>
        <label style={{ fontSize:11, color:C.sub }}>Até</label>
        <input type="date" value={dataFim} onChange={e=>setDataFim(e.target.value)}
          style={{ padding:"5px 10px", borderRadius:7, border:`1px solid ${C.border}`,
            fontSize:12, color:C.text, outline:"none" }}/>
      </div>
      <span style={{ fontSize:11, color:C.faint }}>{dataFim ? "" : "(até hoje)"}</span>
      <div style={{ display:"flex", gap:6, marginLeft:"auto" }}>
        {[
          { label:"Jan/26", ini:"2026-01-02", fim:"2026-01-31" },
          { label:"Fev/26", ini:"2026-02-01", fim:"2026-02-28" },
          { label:"Mar/26", ini:"2026-03-01", fim:"2026-03-31" },
          { label:"Abr/26", ini:"2026-04-01", fim:"2026-04-30" },
          { label:"Mai/26", ini:"2026-05-01", fim:"2026-05-31" },
          { label:"Desde Inv.", ini:"2026-01-02", fim:"" },
        ].map(p => (
          <button key={p.label}
            onClick={()=>{ setDataIni(p.ini); setDataFim(p.fim); }}
            style={{
              padding:"4px 10px", borderRadius:6, fontSize:11, fontWeight:600,
              border:`1px solid ${C.border}`, cursor:"pointer",
              background: dataIni===p.ini && dataFim===p.fim ? "#8B1A1A" : "#F5F5F5",
              color: dataIni===p.ini && dataFim===p.fim ? "#fff" : C.sub,
            }}>{p.label}</button>
        ))}
      </div>
    </div>
  );

  const ABC_COR = { A:"#EF4444", B:"#F59E0B", C:"#10B981" };

  return (
    <div>
      {/* Filtro de data do estoque */}
      <FiltroDataEstoque/>

      {/* Sub-tabs */}
      {/* Hero Estoque */}
      <ModuleHero
        title="Gestão de Estoque"
        subtitle="Posição · Movimentações · Curva ABC · Validades"
        cor="#0D9488"
        loading={lR}
        stats={[
          { label:"Valor em Estoque",  value: brl(resumo?.valor_total),   sub:"saldo atual" },
          { label:"Itens Ativos",      value: num(resumo?.com_estoque),   sub:`de ${num(resumo?.total_itens)} cadastrados` },
          { label:"Itens Zerados",     value: num(resumo?.zerados),       sub:"sem estoque" },
          { label:"Abaixo do Mínimo",  value: num(resumo?.abaixo_minimo), sub:"precisam reposição" },
        ]}
      />

      {/* Tabs redesenhadas */}
      <div style={{ display:"flex", gap:6, marginBottom:20, flexWrap:"wrap" }}>
        {ABAS_EST.map(a => {
          const ativo = aba===a.id;
          return (
            <button key={a.id} onClick={()=>setAba(a.id)} style={{
              padding:"7px 16px", borderRadius:10, border:"none", cursor:"pointer", fontSize:12, fontWeight:700,
              background: ativo ? "#0D9488" : "#fff",
              color: ativo ? "#fff" : "#64748B",
              boxShadow: ativo ? "0 4px 12px #0D948840" : "0 1px 3px rgba(0,0,0,0.07), 0 0 0 1px rgba(0,0,0,0.05)",
              transition:"all 0.15s",
              transform: ativo ? "translateY(-1px)" : "none",
            }}>{a.label}</button>
          );
        })}
      </div>

      {/* ── DASHBOARD ── */}
      {aba==="dashboard" && (
        <div key="dashboard" style={{ animation:"fadeIn 0.25s ease" }}>
          {/* KPIs posição */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:14, marginBottom:16 }}>
            <ModuloCard label="Valor Total em Estoque" value={brl(resumo?.valor_total)}   color="#0D9488" loading={lR} icon="dollar"/>
            <ModuloCard label="Itens com Estoque"      value={num(resumo?.com_estoque)}   color="#10B981" loading={lR} icon="bar"
              sub={`de ${num(resumo?.total_itens)} cadastrados`}/>
            <ModuloCard label="Itens Zerados"          value={num(resumo?.zerados)}       color="#EF4444" loading={lR} icon="activity"
              sub="sem estoque"/>
            <ModuloCard label="Abaixo do Mínimo"       value={num(resumo?.abaixo_minimo)} color="#F59E0B" loading={lR} icon="trending"
              sub="precisam reposição"/>
          </div>

          {/* KPIs movimentação */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:14, marginBottom:20 }}>
            <ModuloCard label="Entradas no Período"    value={brl(resumo?.valor_entradas)} color="#10B981" loading={lR} icon="dollar"
              sub={`${num(resumo?.qtd_entradas)} unidades`}/>
            <ModuloCard label="Saídas no Período"      value={brl(resumo?.valor_saidas)}   color="#EF4444" loading={lR} icon="dollar"
              sub={`${num(resumo?.qtd_saidas)} unidades`}/>
            <ModuloCard label="Lotes Vencendo (30d)"   value={num(resumo?.vence_30d)}      color="#DC2626" loading={lR} icon="calendar"/>
            <ModuloCard label="Lotes Vencidos c/ Saldo" value={num(resumo?.vencidos)}      color="#7C3AED" loading={lR} icon="activity"/>
          </div>

          {/* Gráfico movimentações + Curva ABC */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:16, marginBottom:16 }}>
            <Card title="Entradas e Saídas por Dia" subtitle="Valor movimentado no período">
              {lMD ? <Skeleton h={200}/> : (
                <ResponsiveContainer width="100%" height={200}>
                  <ComposedChart data={movDia||[]} barSize={12} margin={{top:4,right:16,bottom:0,left:0}}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#E5E7EB" vertical={false}/>
                    <XAxis dataKey="data" tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} tickFormatter={v=>v?.slice(5)} interval="preserveStartEnd"/>
                    <YAxis tickFormatter={v=>`R$${(v/1000).toFixed(0)}k`} tick={{fontSize:10,fill:"#9CA3AF"}} axisLine={false} tickLine={false} width={52}/>
                    <Tooltip content={<CTip fmt={v=>brl(v)}/>}/>
                    <Legend iconSize={10} wrapperStyle={{fontSize:11,paddingTop:8}}/>
                    <Bar dataKey="valor_entradas" fill="#10B981" radius={[3,3,0,0]} name="Entradas" opacity={0.85}/>
                    <Bar dataKey="valor_saidas"   fill="#EF4444" radius={[3,3,0,0]} name="Saídas"   opacity={0.85}/>
                  </ComposedChart>
                </ResponsiveContainer>
              )}
            </Card>

            <Card title="Curva ABC" subtitle="Distribuição por valor" accent="#0D9488">
              {lABC ? <Skeleton h={200}/> : (
                <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
                  {(abc||[]).filter(r=>r.curva).map((r,i) => {
                    const cor = ABC_COR[r.curva] || "#94A3B8";
                    return (
                    <div key={i} style={{
                      background:`linear-gradient(135deg, ${cor}12 0%, ${cor}04 100%)`,
                      borderRadius:12, padding:"14px 16px", border:`1.5px solid ${cor}25`,
                    }}>
                      <div style={{ display:"flex", justifyContent:"space-between", marginBottom:8, alignItems:"center" }}>
                        <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                          <span style={{ width:32, height:32, borderRadius:10, background:cor,
                            display:"flex", alignItems:"center", justifyContent:"center",
                            fontSize:14, fontWeight:900, color:"#fff", boxShadow:`0 4px 8px ${cor}40` }}>{r.curva}</span>
                          <div>
                            <div style={{ fontSize:13, color:"#111827", fontWeight:700 }}>{num(r.qtd_itens)} itens</div>
                            <div style={{ fontSize:10, color:"#64748B" }}>curva {r.curva}</div>
                          </div>
                        </div>
                        <div style={{ textAlign:"right" }}>
                          <div style={{ fontSize:14, fontWeight:900, color:cor }}>{brl(r.valor_total)}</div>
                          <div style={{ fontSize:11, color:"#64748B", fontWeight:600 }}>{pct(r.pct_valor)} do total</div>
                        </div>
                      </div>
                      <div style={{ height:6, background:`${cor}18`, borderRadius:4, overflow:"hidden" }}>
                        <div style={{ height:"100%", width:`${r.pct_valor||0}%`,
                          background:`linear-gradient(90deg, ${cor}70, ${cor})`,
                          borderRadius:4, transition:"width 0.8s" }}/>
                      </div>
                    </div>
                    );
                  })}
                  <div style={{ padding:"10px 0", borderTop:`1px solid #F1F5F9` }}>
                    <div style={{ fontSize:11, color:"#94A3B8", fontWeight:600 }}>VALOR TOTAL DO ESTOQUE</div>
                    <div style={{ fontSize:18, fontWeight:900, color:"#111827" }}>{brl(resumo?.valor_total)}</div>
                  </div>
                </div>
              )}
            </Card>
          </div>

          {/* Alertas de vencimento */}
          <Card title="Alertas de Validade" subtitle="Lotes com vencimento próximo ou vencidos">
            {lL ? <Skeleton h={160}/> : !(lotes?.length) ? (
              <div style={{ padding:"24px", textAlign:"center", color:C.faint, fontSize:13 }}>✓ Nenhum lote vencendo em 90 dias</div>
            ) : (
              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                  <thead>
                    <tr style={{ background:"#F2F2F2", borderBottom:`1px solid ${C.border}` }}>
                      {["Material","Lote","Validade","Dias","Saldo","Valor em Risco","Status"].map(h=>(
                        <th key={h} style={{ padding:"8px 12px", fontWeight:700, color:C.faint, textAlign:h==="Material"?"left":"right", fontSize:11, textTransform:"uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(lotes||[]).slice(0,8).map((l,i)=>(
                      <tr key={i} style={{ borderBottom:`1px solid ${C.border}` }}
                        onMouseEnter={e=>e.currentTarget.style.background="#F2F2F2"}
                        onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                        <td style={{ padding:"8px 12px", fontWeight:600, color:"#111827" }}>{l.material}</td>
                        <td style={{ padding:"8px 12px", textAlign:"right", color:C.sub, fontFamily:"monospace", fontSize:11 }}>{l.lote}</td>
                        <td style={{ padding:"8px 12px", textAlign:"right", color:C.sub }}>{l.dt_validade}</td>
                        <td style={{ padding:"8px 12px", textAlign:"right", fontWeight:700,
                          color: l.dias_para_vencer<0?"#DC2626":l.dias_para_vencer<=30?"#DC2626":l.dias_para_vencer<=60?"#D97706":"#059669" }}>
                          {l.dias_para_vencer<0 ? `${Math.abs(l.dias_para_vencer)}d atrás` : `${l.dias_para_vencer}d`}
                        </td>
                        <td style={{ padding:"8px 12px", textAlign:"right" }}>{num(l.saldo)}</td>
                        <td style={{ padding:"8px 12px", textAlign:"right", fontWeight:700, color:"#111827" }}>{brl(l.valor_em_risco)}</td>
                        <td style={{ padding:"8px 12px", textAlign:"right" }}><BadgeStatus status={l.status_validade}/></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ── POSIÇÃO DE ESTOQUE ── */}
      {aba==="posicao" && (
        <TabelaPosicaoEstoque posicao={posicao} loading={lP} curva={curva} setCurva={setCurva} busca={busca} setBusca={setBusca}/>
      )}

            {/* ── GIRO DE ESTOQUE ── */}
      {aba==="giro" && (
        <div>
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))", gap:14, marginBottom:20 }}>
            <ModuloCard label="Materiais com Saída"     value={num((giro||[]).filter(g=>g.saidas_periodo>0).length)} color="#8B1A1A" loading={lG} icon="bar"/>
            <ModuloCard label="Valor Total de Saídas"   value={brl((giro||[]).reduce((s,g)=>s+(g.valor_saidas||0),0))} color="#EF4444" loading={lG} icon="dollar"/>
            <ModuloCard label="Valor Total de Entradas" value={brl((giro||[]).reduce((s,g)=>s+(g.valor_entradas||0),0))} color="#10B981" loading={lG} icon="dollar"/>
          </div>

          <Card title="Relatório de Giro de Estoque" subtitle="Giro = saídas ÷ estoque atual · Cobertura = dias de estoque disponível">
            {lG ? <Skeleton h={400}/> : (
              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                  <thead>
                    <tr style={{ background:"#F2F2F2", borderBottom:`1px solid ${C.border}` }}>
                      {["#","Material","Curva","Estoque Atual","Valor Estoque","Saídas (qtd)","Valor Saídas","Giro","Cobertura (dias)"].map(h=>(
                        <th key={h} style={{ padding:"10px 12px", fontWeight:700, color:C.faint,
                          textAlign:h==="#"||h==="Material"?"left":"right", fontSize:11, textTransform:"uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(giro||[]).map((g,i)=>{
                      const corGiro = g.giro_estoque===0?"#9CA3AF":g.giro_estoque>=2?"#EF4444":g.giro_estoque>=0.5?"#10B981":"#F59E0B";
                      const corCob  = !g.cobertura_dias?"#9CA3AF":g.cobertura_dias<7?"#DC2626":g.cobertura_dias<30?"#D97706":"#10B981";
                      return (
                        <tr key={i} style={{ borderBottom:`1px solid ${C.border}` }}
                          onMouseEnter={e=>e.currentTarget.style.background="#F2F2F2"}
                          onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                          <td style={{ padding:"10px 12px", color:C.faint, fontWeight:700 }}>{i+1}</td>
                          <td style={{ padding:"10px 12px", fontWeight:600, color:"#111827", maxWidth:200, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{g.descricao}</td>
                          <td style={{ padding:"10px 12px", textAlign:"right" }}>
                            <span style={{ padding:"2px 7px", borderRadius:6, fontSize:11, fontWeight:800,
                              background:(ABC_COR[g.curva_abc]||"#94A3B8")+"20",
                              color:ABC_COR[g.curva_abc]||"#94A3B8" }}>{g.curva_abc||"—"}</span>
                          </td>
                          <td style={{ padding:"10px 12px", textAlign:"right", color:C.sub }}>{num(g.estoque_atual)}</td>
                          <td style={{ padding:"10px 12px", textAlign:"right", color:"#111827", fontWeight:600 }}>{brl(g.valor_estoque)}</td>
                          <td style={{ padding:"10px 12px", textAlign:"right", color:"#EF4444", fontWeight:600 }}>{num(g.saidas_periodo)}</td>
                          <td style={{ padding:"10px 12px", textAlign:"right", color:"#EF4444", fontWeight:700 }}>{brl(g.valor_saidas)}</td>
                          <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:800, color:corGiro, fontSize:13 }}>
                            {g.giro_estoque>0 ? Number(g.giro_estoque).toFixed(2)+"x" : "—"}
                          </td>
                          <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:700, color:corCob }}>
                            {g.cobertura_dias ? `${Number(g.cobertura_dias).toFixed(0)}d` : "∞"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                  <tfoot>
                    <tr style={{ background:"#FDF2F2", borderTop:`2px solid ${C.blue}` }}>
                      <td colSpan={4} style={{ padding:"10px 12px", fontWeight:800, color:"#111827" }}>TOTAIS</td>
                      <td style={{ padding:"10px 12px", textAlign:"right", fontWeight:800, color:"#111827" }}>
                        {brl((giro||[]).reduce((s,g)=>s+(g.valor_estoque||0),0))}
                      </td>
                      <td style={{ padding:"10px 12px", textAlign:"right", color:"#EF4444", fontWeight:700 }}>
                        {num((giro||[]).reduce((s,g)=>s+(g.saidas_periodo||0),0))}
                      </td>
                      <td style={{ padding:"10px 12px", textAlign:"right", color:"#EF4444", fontWeight:800 }}>
                        {brl((giro||[]).reduce((s,g)=>s+(g.valor_saidas||0),0))}
                      </td>
                      <td colSpan={2}/>
                    </tr>
                  </tfoot>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ── VALIDADE / LOTES ── */}
      {aba==="lotes" && (
        <div>
          <div style={{ display:"flex", gap:8, marginBottom:16, alignItems:"center" }}>
            <span style={{ fontSize:12, color:C.faint, fontWeight:600 }}>Ver lotes vencendo em:</span>
            {[30,60,90,180,365].map(d=>(
              <button key={d} onClick={()=>setDiasVenc(d)} style={{
                padding:"5px 12px", borderRadius:7, fontSize:12, fontWeight:700, cursor:"pointer",
                border:`1.5px solid ${diasVenc===d?C.blue:C.border}`,
                background: diasVenc===d?C.blueLight:"#fff",
                color: diasVenc===d?C.blue:C.faint,
              }}>{d}d</button>
            ))}
          </div>

          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(180px,1fr))", gap:14, marginBottom:16 }}>
            <ModuloCard label="Vencendo em 30d" value={num(resumo?.vence_30d)} color="#DC2626" loading={lR} icon="calendar"/>
            <ModuloCard label="Vencendo em 60d" value={num(resumo?.vence_60d)} color="#F59E0B" loading={lR} icon="calendar"/>
            <ModuloCard label="Vencendo em 90d" value={num(resumo?.vence_90d)} color="#D97706" loading={lR} icon="calendar"/>
            <ModuloCard label="Vencidos c/ Saldo" value={num(resumo?.vencidos)} color="#7C3AED" loading={lR} icon="activity"/>
          </div>

          <Card title={`Lotes com Vencimento nos próximos ${diasVenc} dias`} subtitle="Ordenado por data de vencimento">
            {lL ? <Skeleton h={300}/> : !(lotes?.length) ? (
              <div style={{ padding:"40px", textAlign:"center", color:"#10B981", fontSize:14, fontWeight:600 }}>
                ✓ Nenhum lote vencendo nos próximos {diasVenc} dias
              </div>
            ) : (
              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                  <thead>
                    <tr style={{ background:"#F2F2F2", borderBottom:`1px solid ${C.border}` }}>
                      {["Material","Curva","Lote","Dt. Entrada","Dt. Validade","Dias","Saldo","Valor em Risco","Almox.","Status"].map(h=>(
                        <th key={h} style={{ padding:"9px 12px", fontWeight:700, color:C.faint,
                          textAlign:h==="Material"?"left":"right", fontSize:10, textTransform:"uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(lotes||[]).map((l,i)=>(
                      <tr key={i} style={{ borderBottom:`1px solid ${C.border}`,
                        background: l.status_validade==="VENCIDO"?"#FFF5F5":l.status_validade==="CRITICO"?"#FFFBEB":"transparent" }}
                        onMouseEnter={e=>e.currentTarget.style.opacity="0.85"}
                        onMouseLeave={e=>e.currentTarget.style.opacity="1"}>
                        <td style={{ padding:"9px 12px", fontWeight:600, color:"#111827", maxWidth:220, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{l.material}</td>
                        <td style={{ padding:"9px 12px", textAlign:"right" }}>
                          <span style={{ padding:"1px 6px", borderRadius:5, fontSize:10, fontWeight:800,
                            background:(ABC_COR[l.curva_abc]||"#94A3B8")+"20",
                            color:ABC_COR[l.curva_abc]||"#94A3B8" }}>{l.curva_abc||"—"}</span>
                        </td>
                        <td style={{ padding:"9px 12px", textAlign:"right", fontFamily:"monospace", fontSize:11, color:C.sub }}>{l.lote}</td>
                        <td style={{ padding:"9px 12px", textAlign:"right", color:C.faint, fontSize:11 }}>{l.dt_entrada}</td>
                        <td style={{ padding:"9px 12px", textAlign:"right", fontWeight:600, color:"#111827" }}>{l.dt_validade}</td>
                        <td style={{ padding:"9px 12px", textAlign:"right", fontWeight:700,
                          color: l.dias_para_vencer<0?"#DC2626":l.dias_para_vencer<=30?"#DC2626":l.dias_para_vencer<=60?"#D97706":"#059669" }}>
                          {l.dias_para_vencer<0?`${Math.abs(l.dias_para_vencer)}d atrás`:`${l.dias_para_vencer}d`}
                        </td>
                        <td style={{ padding:"9px 12px", textAlign:"right" }}>{num(l.saldo)}</td>
                        <td style={{ padding:"9px 12px", textAlign:"right", fontWeight:700, color:"#DC2626" }}>{brl(l.valor_em_risco)}</td>
                        <td style={{ padding:"9px 12px", textAlign:"right", color:C.faint, fontSize:11 }}>{l.almoxarifado}</td>
                        <td style={{ padding:"9px 12px", textAlign:"right" }}><BadgeStatus status={l.status_validade}/></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ── POR GRUPO ── */}
      {aba==="grupos" && (
        <div>
          {/* Cards por grupo */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))", gap:14, marginBottom:20 }}>
            {lGR ? [0,1,2,3,4,5].map(i=><Skeleton key={i} h={140}/>) :
              (grupos?.por_grupo||[]).map((g,i) => {
                const CORES_G = ["#8B1A1A","#10B981","#F59E0B","#8B5CF6","#EF4444","#0891B2","#D97706","#EC4899"];
                const cor = CORES_G[i % CORES_G.length];
                const pctCrit = g.total_itens > 0 ? ((g.itens_criticos||0)/g.total_itens*100).toFixed(0) : 0;
                return (
                  <div key={i} style={{ background:"#fff", borderRadius:14, padding:"18px 20px",
                    borderTop:`3px solid ${cor}`, boxShadow:"0 1px 3px rgba(0,0,0,0.06)",
                    cursor:"pointer", transition:"box-shadow 0.15s" }}
                    onMouseEnter={e=>e.currentTarget.style.boxShadow="0 4px 12px rgba(0,0,0,0.1)"}
                    onMouseLeave={e=>e.currentTarget.style.boxShadow="0 1px 3px rgba(0,0,0,0.06)"}>
                    <div style={{ fontSize:11, color:cor, fontWeight:800, textTransform:"uppercase",
                      letterSpacing:"0.06em", marginBottom:6 }}>{g.grupo_nome}</div>
                    <div style={{ fontSize:24, fontWeight:800, color:"#111827", marginBottom:4 }}>
                      {new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(g.valor_estoque||0)}
                    </div>
                    <div style={{ fontSize:11, color:C.sub, marginBottom:10 }}>
                      {Number(g.total_itens).toLocaleString("pt-BR")} itens · {Number(g.itens_com_estoque).toLocaleString("pt-BR")} c/ estoque
                    </div>
                    {/* Mini barra: estoque vs zerados */}
                    <div style={{ display:"flex", gap:3, height:6, borderRadius:4, overflow:"hidden", marginBottom:8 }}>
                      <div style={{ flex:g.itens_com_estoque||0, background:cor, borderRadius:4 }}/>
                      <div style={{ flex:g.itens_zerados||0, background:"#FEE2E2", borderRadius:4 }}/>
                    </div>
                    <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(280px,1fr))", gap:8, marginTop:8, paddingTop:8, borderTop:`1px solid ${C.border}` }}>
                      <div>
                        <div style={{ fontSize:10, color:C.faint, fontWeight:600 }}>Saídas</div>
                        <div style={{ fontSize:12, fontWeight:700, color:"#EF4444" }}>
                          {new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(g.valor_saidas||0)}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize:10, color:C.faint, fontWeight:600 }}>Críticos</div>
                        <div style={{ fontSize:12, fontWeight:700, color:g.itens_criticos>0?"#EF4444":"#10B981" }}>
                          {g.itens_criticos||0} ({pctCrit}%)
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })
            }
          </div>

          {/* Top linhas de material — largura total */}
          <Card title="Top Linhas de Material" subtitle="Sub-grupos com maior valor em estoque" style={{ marginBottom:16 }}>
              {lGR ? <Skeleton h={280}/> : (
                <div style={{ display:"flex", flexDirection:"column", gap:10 }}>
                  {(grupos?.por_linha||[]).map((l,i) => {
                    const max = grupos.por_linha[0]?.valor_estoque || 1;
                    const pBar = Math.max(4,(l.valor_estoque/max)*100);
                    const cor = ["#8B1A1A","#10B981","#F59E0B","#8B5CF6","#EF4444","#0891B2"][i%6];
                    return (
                      <div key={i}>
                        <div style={{ display:"flex", justifyContent:"space-between", marginBottom:3, alignItems:"center" }}>
                          <div style={{ minWidth:0 }}>
                            <div style={{ fontSize:12, fontWeight:600, color:"#111827", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", maxWidth:200 }}>{l.linha_nome}</div>
                            <div style={{ fontSize:10, color:C.faint }}>{l.grupo_nome} · {l.total_itens} itens</div>
                          </div>
                          <div style={{ textAlign:"right", flexShrink:0, marginLeft:8 }}>
                            <div style={{ fontSize:12, fontWeight:700, color:cor }}>
                              {new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(l.valor_estoque||0)}
                            </div>
                          </div>
                        </div>
                        <div style={{ height:5, background:"#EEEEEE", borderRadius:3, overflow:"hidden" }}>
                          <div style={{ height:"100%", width:`${pBar}%`, background:cor, borderRadius:3 }}/>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
          </Card>

          {/* Distribuição por Grupo — barras horizontais com valor */}
          <Card title="Distribuição por Grupo" subtitle="Valor em estoque por grupo de material" style={{ marginBottom:16 }}>
            {lGR ? <Skeleton h={320}/> : (() => {
              const dados = (grupos?.por_grupo||[]).filter(g=>g.valor_estoque>0).sort((a,b)=>(b.valor_estoque||0)-(a.valor_estoque||0));
              const total = dados.reduce((s,g)=>s+(g.valor_estoque||0),0);
              const CORES = ["#8B1A1A","#10B981","#F59E0B","#8B5CF6","#EF4444","#0891B2","#D97706","#EC4899","#14B8A6","#F97316"];
              const maxVal = dados[0]?.valor_estoque || 1;
              const brl = v => new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v||0);
              return (
                <div>
                  {/* Barra empilhada no topo */}
                  <div style={{ display:"flex", height:14, borderRadius:8, overflow:"hidden", marginBottom:20, gap:1 }}>
                    {dados.map((g,i) => (
                      <div key={i} title={`${g.grupo_nome}: ${((g.valor_estoque/total)*100).toFixed(1)}%`}
                        style={{ flex:g.valor_estoque, background:CORES[i%CORES.length], transition:"flex 0.5s" }}/>
                    ))}
                  </div>
                  {/* Lista com barras */}
                  <div style={{ display:"flex", flexDirection:"column", gap:14 }}>
                    {dados.map((g,i) => {
                      const pct = total>0?((g.valor_estoque/total)*100).toFixed(1):0;
                      const pBar = Math.max(2,(g.valor_estoque/maxVal)*100);
                      const cor  = CORES[i%CORES.length];
                      return (
                        <div key={i}>
                          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:5 }}>
                            <div style={{ display:"flex", alignItems:"center", gap:8, minWidth:0, flex:1 }}>
                              <div style={{ width:12, height:12, borderRadius:3, background:cor, flexShrink:0 }}/>
                              <span style={{ fontSize:13, fontWeight:600, color:"#111827", overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>
                                {g.grupo_nome}
                              </span>
                            </div>
                            <div style={{ display:"flex", alignItems:"center", gap:16, flexShrink:0, marginLeft:12 }}>
                              <span style={{ fontSize:12, color:C.faint, fontWeight:500 }}>{g.total_itens} itens</span>
                              <span style={{ fontSize:13, fontWeight:800, color:cor, minWidth:90, textAlign:"right" }}>{brl(g.valor_estoque)}</span>
                              <span style={{ fontSize:12, fontWeight:700, color:"#111827", minWidth:42, textAlign:"right" }}>{pct}%</span>
                            </div>
                          </div>
                          <div style={{ height:8, background:"#EEEEEE", borderRadius:4, overflow:"hidden" }}>
                            <div style={{ height:"100%", width:`${pBar}%`, background:cor, borderRadius:4, transition:"width 0.6s ease" }}/>
                          </div>
                          {/* Saídas no período */}
                          {g.valor_saidas>0 && (
                            <div style={{ fontSize:11, color:"#EF4444", marginTop:3 }}>
                              ↓ saídas: {brl(g.valor_saidas)}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                  {/* Total */}
                  <div style={{ marginTop:16, paddingTop:14, borderTop:`1px solid ${C.border}`,
                    display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                    <span style={{ fontSize:13, fontWeight:700, color:C.sub }}>Valor total em estoque</span>
                    <span style={{ fontSize:18, fontWeight:800, color:"#111827" }}>{brl(total)}</span>
                  </div>
                </div>
              );
            })()}
          </Card>

          {/* Tabela detalhada por grupo expandível */}
          <Card title="Itens por Grupo" subtitle="Todos os materiais organizados por grupo">
            {lGR ? <Skeleton h={300}/> : (
              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                  <thead>
                    <tr style={{ background:"#F2F2F2", borderBottom:`1px solid ${C.border}` }}>
                      {["Grupo","Material","Curva","Qtd Atual","Valor Estoque","Saídas Período","Status"].map(h=>(
                        <th key={h} style={{ padding:"9px 12px", fontWeight:700, color:C.faint,
                          textAlign:h==="Grupo"||h==="Material"?"left":"right", fontSize:10, textTransform:"uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(grupos?.top_por_grupo||[]).map((m,i) => {
                      const CORES_G = ["#8B1A1A","#10B981","#F59E0B","#8B5CF6","#EF4444","#0891B2","#D97706","#EC4899"];
                      const grupoObj = (grupos?.por_grupo||[]).find(g=>g.grupo_cod===m.grupo_cod);
                      const grupoIdx = (grupos?.por_grupo||[]).findIndex(g=>g.grupo_cod===m.grupo_cod);
                      const cor = CORES_G[grupoIdx % CORES_G.length];
                      return (
                        <tr key={i} style={{ borderBottom:`1px solid ${C.border}` }}
                          onMouseEnter={e=>e.currentTarget.style.background="#F2F2F2"}
                          onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                          <td style={{ padding:"9px 12px" }}>
                            <span style={{ fontSize:10, fontWeight:700, color:cor, background:cor+"15",
                              padding:"2px 7px", borderRadius:6, whiteSpace:"nowrap" }}>
                              {grupoObj?.grupo_nome||m.grupo_cod}
                            </span>
                          </td>
                          <td style={{ padding:"9px 12px", fontWeight:600, color:"#111827", maxWidth:220, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{m.descricao}</td>
                          <td style={{ padding:"9px 12px", textAlign:"right" }}>
                            <span style={{ fontSize:10, fontWeight:800, color:ABC_COR[m.curva_abc]||"#94A3B8" }}>{m.curva_abc||"—"}</span>
                          </td>
                          <td style={{ padding:"9px 12px", textAlign:"right", fontWeight:600, color:"#111827" }}>{Number(m.qtd_atual).toLocaleString("pt-BR")}</td>
                          <td style={{ padding:"9px 12px", textAlign:"right", fontWeight:700, color:"#111827" }}>
                            {new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(m.valor_estoque||0)}
                          </td>
                          <td style={{ padding:"9px 12px", textAlign:"right", color:"#EF4444", fontWeight:600 }}>
                            {new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL"}).format(m.valor_saidas||0)}
                          </td>
                          <td style={{ padding:"9px 12px", textAlign:"right" }}><BadgeStatus status={m.status_estoque}/></td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ── POR SETOR ── */}
      {aba==="setores" && (
        <div>
          {/* Cards top setores */}
          <div style={{ display:"grid", gridTemplateColumns:"repeat(auto-fit,minmax(220px,1fr))", gap:14, marginBottom:20 }}>
            {lST ? [0,1,2,3,4,5].map(i=><Skeleton key={i} h={100}/>) :
              (setores?.por_setor||[]).slice(0,6).map((s,i) => {
                const CORES_S = ["#8B1A1A","#10B981","#F59E0B","#8B5CF6","#EF4444","#0891B2"];
                const cor = CORES_S[i%CORES_S.length];
                const brl = v => new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v||0);
                return (
                  <div key={i} style={{ background:"#fff", borderRadius:14, padding:"16px 18px",
                    borderLeft:`4px solid ${cor}`, boxShadow:"0 1px 3px rgba(0,0,0,0.06)",
                    display:"flex", gap:12, alignItems:"center" }}>
                    <div style={{ width:40, height:40, borderRadius:10, background:cor+"15",
                      display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0,
                      fontSize:13, fontWeight:900, color:cor }}>{(s.setor_cod||"?").slice(0,3)}</div>
                    <div style={{ minWidth:0, flex:1 }}>
                      <div style={{ fontSize:11, color:cor, fontWeight:700, textTransform:"uppercase",
                        overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{s.setor_nome||s.setor_cod}</div>
                      <div style={{ fontSize:20, fontWeight:800, color:"#111827" }}>{brl(s.valor_total)}</div>
                      <div style={{ fontSize:11, color:C.sub }}>{Number(s.materiais_distintos||0).toLocaleString("pt-BR")} materiais · {Number(s.qtd_total||0).toLocaleString("pt-BR")} unid.</div>
                    </div>
                  </div>
                );
              })}
          </div>

          {/* Barra comparativa */}
          <Card title="Consumo por Setor" subtitle="Valor total de saídas no período" style={{ marginBottom:16 }}>
            {lST ? <Skeleton h={300}/> : (() => {
              const dados = setores?.por_setor||[];
              const max   = dados[0]?.valor_total||1;
              const total = dados.reduce((s,r)=>s+(r.valor_total||0),0);
              const CORES_S = ["#8B1A1A","#10B981","#F59E0B","#8B5CF6","#EF4444","#0891B2","#D97706","#EC4899","#14B8A6","#F97316"];
              const brl = v => new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v||0);
              return (
                <div>
                  {/* Barra empilhada */}
                  <div style={{ display:"flex", height:12, borderRadius:6, overflow:"hidden", marginBottom:20, gap:1 }}>
                    {dados.map((s,i)=>(
                      <div key={i} style={{ flex:s.valor_total||0, background:CORES_S[i%CORES_S.length] }}
                        title={`${s.setor_nome}: ${brl(s.valor_total)}`}/>
                    ))}
                  </div>
                  <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
                    {dados.map((s,i) => {
                      const cor  = CORES_S[i%CORES_S.length];
                      const pBar = Math.max(2,(s.valor_total/max)*100);
                      const pct  = total>0?((s.valor_total/total)*100).toFixed(1):0;
                      return (
                        <div key={i}>
                          <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:5 }}>
                            <div style={{ display:"flex", alignItems:"center", gap:8, minWidth:0, flex:1 }}>
                              <span style={{ fontSize:11, fontWeight:800, color:"#fff", background:cor,
                                padding:"2px 7px", borderRadius:5, flexShrink:0 }}>{s.setor_cod}</span>
                              <span style={{ fontSize:13, fontWeight:600, color:"#111827",
                                overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{s.setor_nome||s.setor_cod}</span>
                            </div>
                            <div style={{ display:"flex", gap:14, flexShrink:0, marginLeft:8, alignItems:"center" }}>
                              <span style={{ fontSize:11, color:C.faint }}>{Number(s.qtd_total||0).toLocaleString("pt-BR")} un.</span>
                              <span style={{ fontSize:13, fontWeight:800, color:cor, minWidth:80, textAlign:"right" }}>{brl(s.valor_total)}</span>
                              <span style={{ fontSize:11, fontWeight:600, color:C.sub, minWidth:36, textAlign:"right" }}>{pct}%</span>
                            </div>
                          </div>
                          <div style={{ height:8, background:"#EEEEEE", borderRadius:4, overflow:"hidden" }}>
                            <div style={{ height:"100%", width:`${pBar}%`, background:cor, borderRadius:4, transition:"width 0.6s" }}/>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div style={{ marginTop:16, paddingTop:12, borderTop:`1px solid ${C.border}`,
                    display:"flex", justifyContent:"space-between" }}>
                    <span style={{ fontSize:13, fontWeight:600, color:C.sub }}>Total de saídas no período</span>
                    <span style={{ fontSize:16, fontWeight:800, color:"#111827" }}>{brl(total)}</span>
                  </div>
                </div>
              );
            })()}
          </Card>

          {/* Top 5 materiais por setor */}
          {/* Dropdown seletor de setor */}
          <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:16 }}>
            <span style={{ fontSize:12, color:C.faint, fontWeight:600, flexShrink:0 }}>Setor:</span>
            <select value={setorSel} onChange={e=>setSetorSel(e.target.value)} style={{
              padding:"7px 12px", borderRadius:8, border:`1px solid ${C.border}`,
              background:"#fff", color:"#111827", fontSize:13, fontWeight:600,
              cursor:"pointer", outline:"none", minWidth:280,
            }}>
              <option value="">Todos os setores</option>
              {[...(setores?.por_setor||[])]
                .sort((a,b)=>(b.valor_total||0)-(a.valor_total||0))
                .map(s => (
                  <option key={s.setor_cod} value={s.setor_cod}>
                    {s.setor_nome || s.setor_cod} ({s.setor_cod}) — {new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(s.valor_total||0)}
                  </option>
                ))
              }
            </select>
            {setorSel && (
              <button onClick={()=>setSetorSel("")} style={{
                padding:"6px 12px", borderRadius:8, border:`1px solid ${C.border}`,
                background:"#fff", color:C.faint, fontSize:12, fontWeight:600, cursor:"pointer",
              }}>✕ Limpar</button>
            )}
          </div>

          <Card title="Top Materiais por Setor" subtitle="Materiais mais consumidos · ordenados por maior saída">
            {lST ? <Skeleton h={400}/> : (() => {
              const CORES_S = ["#8B1A1A","#10B981","#F59E0B","#8B5CF6","#EF4444","#0891B2","#D97706","#EC4899","#14B8A6","#F97316"];
              const brl  = v => new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v||0);
              const num  = v => Number(v||0).toLocaleString("pt-BR");

              // Agrupa materiais por setor — normaliza cod com trim
              const porSetor = {};
              (setores?.top_materiais||[]).forEach(m => {
                const cod = (m.setor_cod||"").trim();
                if (!porSetor[cod]) porSetor[cod] = [];
                if (porSetor[cod].length < 10) porSetor[cod].push(m);
              });

              // Ordena setores por valor_total desc; filtra pelo selecionado
              const setoresOrdenados = [...(setores?.por_setor||[])]
                .sort((a,b)=>(b.valor_total||0)-(a.valor_total||0))
                .filter(s => porSetor[(s.setor_cod||"").trim()])
                .filter(s => setorSel==="" || (s.setor_cod||"").trim()===setorSel.trim());

              const totalGeral = setoresOrdenados.reduce((s,r)=>s+(r.valor_total||0),0);

              return (
                <div style={{ display:"flex", flexDirection:"column", gap:16 }}>
                  {setoresOrdenados.map((setor, si) => {
                    const cod  = setor.setor_cod;
                    const mats = porSetor[(cod||"").trim()]||[];
                    const cor  = CORES_S[si%CORES_S.length];
                    const maxV = mats[0]?.valor||1;
                    const pct  = totalGeral>0?((setor.valor_total/totalGeral)*100).toFixed(1):0;

                    return (
                      <div key={cod} style={{ background:"#fff", borderRadius:14,
                        border:`1px solid ${C.border}`, overflow:"hidden",
                        boxShadow:"0 1px 3px rgba(0,0,0,0.05)" }}>

                        {/* Header do setor */}
                        <div style={{ background:cor+"0E", borderBottom:`1px solid ${cor}25`,
                          padding:"12px 18px", display:"flex", alignItems:"center", justifyContent:"space-between" }}>
                          <div style={{ display:"flex", alignItems:"center", gap:10 }}>
                            {/* Ranking */}
                            <div style={{ width:28, height:28, borderRadius:8, background:cor,
                              display:"flex", alignItems:"center", justifyContent:"center",
                              fontSize:13, fontWeight:900, color:"#fff", flexShrink:0 }}>
                              {si+1}
                            </div>
                            <div>
                              <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                                <span style={{ fontSize:12, fontWeight:800, color:"#fff", background:cor,
                                  padding:"2px 8px", borderRadius:5 }}>{cod}</span>
                                <span style={{ fontSize:14, fontWeight:700, color:"#111827" }}>
                                  {setor.setor_nome||cod}
                                </span>
                              </div>
                              <div style={{ fontSize:11, color:C.faint, marginTop:2 }}>
                                {num(setor.materiais_distintos)} materiais · {num(setor.qtd_total)} unidades · {num(setor.dias_com_retirada)} dias com retirada
                              </div>
                            </div>
                          </div>
                          {/* Valor e % */}
                          <div style={{ textAlign:"right", flexShrink:0 }}>
                            <div style={{ fontSize:18, fontWeight:900, color:cor }}>{brl(setor.valor_total)}</div>
                            <div style={{ fontSize:12, fontWeight:600, color:C.faint }}>{pct}% do total</div>
                          </div>
                        </div>

                        {/* Barra de progresso do setor */}
                        <div style={{ height:4, background:"#EEEEEE" }}>
                          <div style={{ height:"100%", background:cor,
                            width:`${Math.max(2,(setor.valor_total/(setoresOrdenados[0]?.valor_total||1))*100)}%`,
                            transition:"width 0.6s" }}/>
                        </div>

                        {/* Top 5 materiais em grid */}
                        <div style={{ padding:"14px 18px" }}>
                          <div style={{ fontSize:11, color:C.faint, fontWeight:700,
                            textTransform:"uppercase", letterSpacing:"0.06em", marginBottom:10 }}>
                            Top 5 materiais
                          </div>
                          <div style={{ display:"grid", gridTemplateColumns: setorSel ? "repeat(5,1fr)" : "repeat(5,1fr)", gap:8 }}>
                            {(setorSel ? mats : mats.slice(0,5)).map((m,i)=>{
                              const pBar = Math.max(6,(m.valor/maxV)*100);
                              return (
                                <div key={i} style={{ background:"#F2F2F2", borderRadius:9,
                                  padding:"10px 12px", borderTop:`2px solid ${cor}` }}>
                                  <div style={{ fontSize:10, color:C.faint, fontWeight:700,
                                    textTransform:"uppercase", marginBottom:4 }}>#{i+1}</div>
                                  <div style={{ fontSize:11, fontWeight:600, color:"#111827",
                                    lineHeight:1.3, marginBottom:8, minHeight:30,
                                    overflow:"hidden", display:"-webkit-box",
                                    WebkitLineClamp:2, WebkitBoxOrient:"vertical" }}>
                                    {m.material}
                                  </div>
                                  <div style={{ fontSize:13, fontWeight:800, color:cor, marginBottom:6 }}>
                                    {brl(m.valor)}
                                  </div>
                                  <div style={{ fontSize:10, color:C.faint, marginBottom:6 }}>
                                    {num(m.qtd)} unid.
                                  </div>
                                  <div style={{ height:4, background:"#E2E8F0", borderRadius:3 }}>
                                    <div style={{ height:"100%", width:`${pBar}%`,
                                      background:cor, borderRadius:3, opacity:.8 }}/>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })()}
          </Card>
        </div>
      )}

      {/* ── MOVIMENTAÇÕES ── */}
      {aba==="movimentos" && (
        <div>
          <div style={{ display:"flex", gap:8, marginBottom:16, alignItems:"center" }}>
            <span style={{ fontSize:12, color:C.faint, fontWeight:600 }}>Tipo:</span>
            {[{id:"",l:"Todas"},{id:"E",l:"Entradas"},{id:"S",l:"Saídas"}].map(t=>(
              <button key={t.id} onClick={()=>setTipoMov(t.id)} style={{
                padding:"5px 14px", borderRadius:7, fontSize:12, fontWeight:700, cursor:"pointer",
                border:`1.5px solid ${tipoMov===t.id?C.blue:C.border}`,
                background: tipoMov===t.id?C.blueLight:"#fff",
                color: tipoMov===t.id?C.blue:C.faint,
              }}>{t.l}</button>
            ))}
          </div>

          <Card title="Movimentações de Estoque" subtitle="Últimas 200 movimentações no período">
            {lM ? <Skeleton h={400}/> : !(movs?.length) ? (
              <div style={{ padding:"40px", textAlign:"center", color:C.faint, fontSize:13 }}>Sem movimentações no período</div>
            ) : (
              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                  <thead>
                    <tr style={{ background:"#F2F2F2", borderBottom:`1px solid ${C.border}` }}>
                      {["Data","Material","Curva","Tipo","Qtd","Preço Unit.","Valor Total","Setor","Usuário"].map(h=>(
                        <th key={h} style={{ padding:"9px 12px", fontWeight:700, color:C.faint,
                          textAlign:h==="Data"||h==="Material"?"left":"right", fontSize:10, textTransform:"uppercase" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(movs||[]).map((m,i)=>{
                      const isEntrada = m.tipo_es==="E";
                      const setorLabel = m.setor_nome || m.setor_cod || "—";
                      return (
                        <tr key={i} style={{ borderBottom:`1px solid ${C.border}` }}
                          onMouseEnter={e=>e.currentTarget.style.background="#F2F2F2"}
                          onMouseLeave={e=>e.currentTarget.style.background="transparent"}>
                          <td style={{ padding:"9px 12px", color:C.sub, fontSize:11, whiteSpace:"nowrap" }}>{m.data}</td>
                          <td style={{ padding:"9px 12px", fontWeight:600, color:"#111827", maxWidth:200, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{m.material}</td>
                          <td style={{ padding:"9px 12px", textAlign:"right" }}>
                            <span style={{ fontSize:10, fontWeight:800, color:ABC_COR[m.curva_abc]||"#94A3B8" }}>{m.curva_abc||"—"}</span>
                          </td>
                          <td style={{ padding:"9px 12px", textAlign:"right" }}>
                            <span style={{ padding:"2px 8px", borderRadius:12, fontSize:10, fontWeight:700,
                              background:isEntrada?"#D1FAE5":"#FEE2E2",
                              color:isEntrada?"#059669":"#DC2626" }}>
                              {isEntrada?"↑ Entrada":"↓ Saída"}
                            </span>
                          </td>
                          <td style={{ padding:"9px 12px", textAlign:"right", fontWeight:700, color:isEntrada?"#059669":"#DC2626" }}>
                            {isEntrada?"+":"-"}{num(m.qtd)}
                          </td>
                          <td style={{ padding:"9px 12px", textAlign:"right", color:C.sub }}>{brl(m.preco_unitario)}</td>
                          <td style={{ padding:"9px 12px", textAlign:"right", fontWeight:700, color:"#111827" }}>{brl(m.valor_total)}</td>
                          <td style={{ padding:"9px 12px", textAlign:"right", color:C.sub, fontSize:11, maxWidth:140, overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }} title={m.setor_nome}>{setorLabel}</td>
                          <td style={{ padding:"9px 12px", textAlign:"right", color:C.faint, fontSize:11 }}>{m.usuario?.trim()}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ── SINTÉTICO ── */}
      {aba==="sintetico" && (
        <div>
          <Card title="Saldos por Grupo (Sintético)" subtitle="Baseado nas movimentações do período selecionado">
            {lSIN ? <Skeleton h={300}/> : (
              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                  <thead>
                    <tr style={{ background:"#F5EAEA" }}>
                      {["Grupo","Itens","Entradas","Saídas","Saldo Atual"].map(h => (
                        <th key={h} style={{ padding:"10px 12px", textAlign:"left", fontWeight:700,
                          color:"#8B1A1A", fontSize:11, textTransform:"uppercase", whiteSpace:"nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(sintetico?.grupos||[]).map((g,i) => (
                      <tr key={i}
                        onClick={() => { setGrupoCod(g.grupo_cod); setAba("analitico"); }}
                        style={{ borderBottom:`1px solid ${C.border}`, cursor:"pointer",
                          background: i%2===0 ? "#fff" : "#FDF9F9" }}
                        onMouseEnter={e=>e.currentTarget.style.background="#F5EAEA"}
                        onMouseLeave={e=>e.currentTarget.style.background=i%2===0?"#fff":"#FDF9F9"}>
                        <td style={{ padding:"10px 12px", fontWeight:600, color:C.text }}>
                          <span style={{ marginRight:6, fontSize:10, color:"#8B1A1A" }}>▶</span>
                          {g.grupo_nome}
                        </td>
                        <td style={{ padding:"10px 12px", color:C.sub, textAlign:"center" }}>{g.total_itens}</td>
                        <td style={{ padding:"10px 12px", color:"#10B981", fontWeight:600 }}>{brl(g.entradas)}</td>
                        <td style={{ padding:"10px 12px", color:"#EF4444", fontWeight:600 }}>{brl(g.saidas)}</td>
                        <td style={{ padding:"10px 12px", color:"#8B1A1A", fontWeight:700 }}>{brl(g.saldo_atual)}</td>
                      </tr>
                    ))}
                    {sintetico?.totais && (
                      <tr style={{ borderTop:`2px solid #8B1A1A`, background:"#F5EAEA", fontWeight:700 }}>
                        <td style={{ padding:"10px 12px", color:"#8B1A1A" }}>TOTAL GERAL</td>
                        <td/>
                        <td style={{ padding:"10px 12px", color:"#10B981" }}>{brl(sintetico.totais.entradas)}</td>
                        <td style={{ padding:"10px 12px", color:"#EF4444" }}>{brl(sintetico.totais.saidas)}</td>
                        <td style={{ padding:"10px 12px", color:"#8B1A1A" }}>{brl(sintetico.totais.saldo_atual)}</td>
                      </tr>
                    )}
                  </tbody>
                </table>
                <div style={{ fontSize:11, color:C.faint, padding:"8px 12px", textAlign:"right" }}>
                  Clique em um grupo para ver o analítico detalhado
                </div>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* ── ANALÍTICO ── */}
      {aba==="analitico" && (
        <div>
          <div style={{ display:"flex", gap:10, marginBottom:14, flexWrap:"wrap" }}>
            <input placeholder="🔍 Buscar material..." value={buscaAnal} onChange={e=>setBuscaAnal(e.target.value)}
              style={{ padding:"7px 12px", borderRadius:8, border:`1px solid ${C.border}`,
                fontSize:12, outline:"none", minWidth:220, flex:1 }}/>
            {grupoCod && (
              <button onClick={()=>setGrupoCod("")} style={{
                padding:"7px 12px", borderRadius:8, background:"#F5EAEA",
                border:"1px solid #8B1A1A", color:"#8B1A1A", fontSize:11, fontWeight:700, cursor:"pointer" }}>
                ✕ {grupoCod}
              </button>
            )}
          </div>
          <Card title="Saldos por Material (Analítico)" subtitle="Item a item com movimentações do período">
            {lANL ? <Skeleton h={400}/> : (
              <div style={{ overflowX:"auto" }}>
                <table style={{ width:"100%", borderCollapse:"collapse", fontSize:12 }}>
                  <thead>
                    <tr style={{ background:"#F5EAEA" }}>
                      {["Cód","Material","Grupo","PM","Qtd","Saldo","Ent.Qtd","Ent.R$","Saí.Qtd","Saí.R$","Status"].map(h => (
                        <th key={h} style={{ padding:"9px 10px", textAlign:"left", fontWeight:700,
                          color:"#8B1A1A", fontSize:10, textTransform:"uppercase", whiteSpace:"nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(analitico||[]).map((m,i) => {
                      const stCor = m.status_estoque==="ZERADO" ? "#EF4444"
                        : m.status_estoque==="CRITICO" ? "#F59E0B" : "#10B981";
                      return (
                        <tr key={i} style={{ borderBottom:`1px solid ${C.border}`,
                          background: i%2===0 ? "#fff" : "#FDF9F9" }}>
                          <td style={{ padding:"8px 10px", color:C.faint, fontSize:11 }}>{m.cod}</td>
                          <td style={{ padding:"8px 10px", fontWeight:600, color:C.text, maxWidth:180,
                            overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{m.descricao}</td>
                          <td style={{ padding:"8px 10px", color:C.sub, fontSize:11, whiteSpace:"nowrap" }}>{m.grupo_nome}</td>
                          <td style={{ padding:"8px 10px", color:C.sub }}>{brl(m.pm_atual)}</td>
                          <td style={{ padding:"8px 10px", color:C.text, textAlign:"right" }}>{num(m.qtd_atual)}</td>
                          <td style={{ padding:"8px 10px", fontWeight:700, color:"#8B1A1A" }}>{brl(m.saldo_atual)}</td>
                          <td style={{ padding:"8px 10px", color:"#10B981", textAlign:"right" }}>{num(m.qtd_entradas)}</td>
                          <td style={{ padding:"8px 10px", color:"#10B981" }}>{brl(m.val_entradas)}</td>
                          <td style={{ padding:"8px 10px", color:"#EF4444", textAlign:"right" }}>{num(m.qtd_saidas)}</td>
                          <td style={{ padding:"8px 10px", color:"#EF4444" }}>{brl(m.val_saidas)}</td>
                          <td style={{ padding:"8px 10px" }}>
                            <span style={{ fontSize:10, fontWeight:700, padding:"2px 8px", borderRadius:10,
                              background:stCor+"20", color:stCor }}>{m.status_estoque}</span>
                          </td>
                        </tr>
                      );
                    })}
                    {(analitico||[]).length === 0 && (
                      <tr><td colSpan={11} style={{ padding:"32px", textAlign:"center", color:C.faint }}>
                        Sem itens no período selecionado
                      </td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  );
}

function AppWithLogin() {
  const { user, login } = useAuth();
  if (!user) return <Login onLogin={login} />;
  return <AppInner />;
}
export default function App() {
  return <AuthProvider><AppWithLogin /></AuthProvider>;
}

function AppInner() {
  const { user, logout, podeVer } = useAuth();
  const [page,           setPage]           = useState("home");
  const [period,         setPeriod]         = useState("30d");
  const [online,         setOnline]         = useState(null);
  const [collapsed,      setCollapsed]      = useState(true);
  const [showDatePicker, setShowDatePicker] = useState(false);
  const [dateIni,        setDateIni]        = useState("");
  const [dateFim,        setDateFim]        = useState("");
  const [customLabel,    setCustomLabel]    = useState("");
  const isMobile = useIsMobile();
  const SW = isMobile ? 0 : 60; // rail sempre compacto — o menu aberto flutua por cima, sem alterar o layout

  // Find current group + item for breadcrumb
  const currentItem = NAV.find(n => n.id === page);

  useEffect(() => {
    fetch(`${API}/api/health`).then(r=>r.json())
      .then(d=>setOnline(d.status==="ok")).catch(()=>setOnline(false));
  }, []);

  return (
    <MobileCtx.Provider value={isMobile}>
    <div style={{ height:"100vh", display:"flex", flexDirection:"column", background:"#E5CACA", fontFamily:"'DM Sans','Helvetica Neue',sans-serif", color:"#111827", overflow:"hidden" }}>

      {/* ── TOPBAR ── */}
      <div style={{ background:"linear-gradient(135deg, #8B1A1A 0%, #6B1414 100%)", minHeight:68, display:"flex", alignItems:"center", padding:isMobile?"0 12px":"0 20px", gap:isMobile?8:16, flexShrink:0, boxShadow:"0 2px 12px rgba(0,0,0,0.25)", flexWrap:"wrap" }}>
        <div style={{ display:"flex", alignItems:"center", gap:10, flexShrink:0 }}>
          <div style={{ background:"#fff", borderRadius:10, padding:"6px 12px", display:"flex", alignItems:"center" }}>
          <img src="data:image/png;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/4gHYSUNDX1BST0ZJTEUAAQEAAAHIAAAAAAQwAABtbnRyUkdCIFhZWiAH4AABAAEAAAAAAABhY3NwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAA9tYAAQAAAADTLQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAlkZXNjAAAA8AAAACRyWFlaAAABFAAAABRnWFlaAAABKAAAABRiWFlaAAABPAAAABR3dHB0AAABUAAAABRyVFJDAAABZAAAAChnVFJDAAABZAAAAChiVFJDAAABZAAAAChjcHJ0AAABjAAAADxtbHVjAAAAAAAAAAEAAAAMZW5VUwAAAAgAAAAcAHMAUgBHAEJYWVogAAAAAAAAb6IAADj1AAADkFhZWiAAAAAAAABimQAAt4UAABjaWFlaIAAAAAAAACSgAAAPhAAAts9YWVogAAAAAAAA9tYAAQAAAADTLXBhcmEAAAAAAAQAAAACZmYAAPKnAAANWQAAE9AAAApbAAAAAAAAAABtbHVjAAAAAAAAAAEAAAAMZW5VUwAAACAAAAAcAEcAbwBvAGcAbABlACAASQBuAGMALgAgADIAMAAxADb/2wBDAAUDBAQEAwUEBAQFBQUGBwwIBwcHBw8LCwkMEQ8SEhEPERETFhwXExQaFRERGCEYGh0dHx8fExciJCIeJBweHx7/2wBDAQUFBQcGBw4ICA4eFBEUHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh7/wAARCAC1ARYDASIAAhEBAxEB/8QAHQABAAMBAQEBAQEAAAAAAAAAAAYHCAUECQIDAf/EAE8QAAEDAwIEBAIFBgcNCQEAAAECAwQABREGBwgSITETQVFhInEUFTKBkRZCUnKSsiNidIKhsbMYMzU2N0dTdYOGosHDJjhDRGNzwsTRk//EABsBAQACAwEBAAAAAAAAAAAAAAADBQECBAYH/8QANhEAAgEDAwEDCwMEAwEAAAAAAAECAwQRBRIhMRNBUQYiMmFxgZGhsdHwFBXhIzNCwTRDUvH/2gAMAwEAAhEDEQA/ANl0pSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFKUoBSlKAUpSgFK4+o9Uac04ls329wbcXAS2l94JUsDuUp7n7hXutFyt93t7Vwtc2PNiOglt5hwLQrBweo9D0PoaDJ6qUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAV7upunatuNQ2CJf4rxtl3Q/mYyCtUZTRb6qQBlSSHPzeox2Oek1sd3td9tjVzs1wi3CE8Mtvx3AtCvvHmPMeVZ747GAdP6VlYHMia+3n2U2D/APAVm7SGrdTaQnKm6Zvcu1vL+34SgUOenO2oFC/5wOK4al06VVxa4PS2uiQvLONWm8T5zno+X8Pzg+kVKyjpDiqu8dCGdWaajzwOipNvdLK8e7a8gn5KSParK0/xI7b3Z5iOs3qBJfcS02y/AUtSlKOEgeEVjqSPPzqeFzSl0ZXVtGvaPWDfs5+hclKUqcqxSohunr61aBsaJs1BkzJBKIcNCuVTyh3JP5qRkZVg4yOhJANORNX7+ayb+tdNW4w7erJa8CNHQ2tPkQqSSV/NPT5dqyo5NXNJ4NJVDd3dcxdB6VXcVJQ9cHyWoMdR/vjmPtHHXkSOp+4ZyRUG2q3G15I103onWlgV9LW0pz6QGvBcaSkE86h9haCQEhScDJ86rfcjU9n1dvSXNQTFNaZtLpjhKUKWXENklYSlIOS64OXPT4eUkjlrKjyaynxwdnTu3X5QaUue5e5l4nJ+kRlymUpWErUgJJStWQeh6cjaQBjl9eUdfhcun1Dt7qm93d4tWeI+l3/aJbBc5R5qI8IAeZwK513uerd9Ls3aLDDcs+kYro8V91PwkjzXjotYH2WkkgEgk9iJdq/TGkrrp+HtPYNaQrJJgPJU5DcSHHJbnLzgK+JPMolXOQnPXBwOUCtm+5mqXeic7Z6/s+vrdIl2qNPjmMpKH25LPLyqIzgKBKVds9DkAjIGRUtqjdx7tcdldD6as+k0wll0uiU7JYKi84AkqX0UOpJPrgYHYCv4zNxdxtayDb9tLY19HioQiZdFNo5S9ygqCC6eQAE9sKURg9ARnXb4G+/HD6l8VEN2bnq+1aaZk6KtqbhclS0IW0pkuANFKiVYCh5hPn51Ui9zN0dvb1Fjbh25u4QZBJDqENpWtIxktrbwgkZzyqAJ6dUg5qwd5dezdO7dW7U+lnYcgTpLKWnHmytC2nG1rBAyDnoKY5G5NMmGh5V5m6St0vUMYRbq6yFSmQjkCF5PTGTj8TXZqJ6I1R9N2xgas1DIjxuaGZMt1KSltAGckDJPl26mqhue7+v9Z3l+27a2NbUdr/xiwlx7HXCllf8ABtg4OAc9u/lWMZMuSSNFUrNz+4O9Wg1NS9aWcToCl4Wp9poD2SHY/wAKCfLmBz16GrS3D3OgaO0jBus23SE3S4tBca1vKCHUnAKvEIyEhOQCRnqQPlnazCmif0rP1muPEHq9hN5tsiDZILyQthDjDTaXE+RSFoccwfIkgEdRXqf3X1tpFqfZtf2RiNc1QX3LVPab5mX3koJQlYScKBVyglJBHMkFIzzBtG9F70qs+H/XF71zZLnMviYaXYspLTf0ZooHKUA9cqPXJqzKw1g2TysilKVgyKUpQClKUApSlAK8AvdnN8VYvrSGLqloPGGXkh7wznCwjOSnoevavfWEeKO6/WO+17cZWR9XliM0tJwUqQ0lRIPkQtSuo9KguK3ZR3YLLS9P/XVXTzjCzn4G7qVi7afiJ1TpdxqBqhT2o7OMArcUDMZHqlwkBwd+i+p/SHatd6S1HZdV2Ji92Ce1Ngvj4XEdCkjulQPVKh5g4IrNGvCquDF/pleyfnrK8V0KM46CPyN02PP60X/YrrJdam47ZQTbtIwcnLj8p/8AYS2n/qVlmqy8f9VnsdAWLGHv+rFXNwkaIXqbcdu/Smea2WApkEqHwrknPhJ+aTlz2KU+oqsdG6avOr9RRbBYYpkTpJ6Z6IbSPtOLP5qE56n5AZJAO/drtFWzQGjYmnbb/CeH/CSZBTyqkvEDncV88AAdcJCR5Vm0ouctz6Ij13UFbUXSi/Ol8l3v7fwSilKVcHgTM+uY6da8UkbTt0yu3x3G2A0T0U02wZC0n9ZXMCR5EelaXbQhttLbaEoQkAJSkYAA7ACs47+W26aK3Wtu5Frj+JHecbU6fzQ8hPIptRx8IW2AAf1vvuHSm5OjNR2xuZEv0KOsp5nI0p9LTzR8wpKj5eoyD5E1tLoiODw2me3cSe3ZNH3nULbTX06Dbn/ozpSOZJKQQkHuAVpRkfxR6CqQ4att9O6h0/J1BqK2ieUTCxEbdWrw+VCUkqKQcLyVEYVkfD2qytwL3Zta7a6vt2l7mxdZEKJl1MU84zjnASR0VkIIHLnqCO4xUK4ctwtJ2jQCrNerxFtsqJIdcAkK5Q6hZ5gpJ7E5JGB16duorKzgPDksltayvVt0PoebdUx2GY0BjEeO2kIQpZ+FtsAdgVEDp2qnOFjT711u943Au6jIlKeWww4sdVOr+N5z8FJSCPVYqOb6a/XuE6bTpeNKfslpSqZKf8Mp8QgcviEHqlCQogc2CSrt0FTHYbcTRuntqW4V3uzMOZBdfU8woHxHuZalpKEjqroQOnmOtMNIxuTkfw4xji26bPo9I/dRVs7X2iNY9vrHboqEpCITa3CkY53FJClqPuVEmqH4htQnVe3mjtQfRvoyZj0xSGs5KUhQSkE+uAM++a0VpT/Fe0/yJn9wVh9EZjzJsr3iliMyNp35DiAXIkxh1okdQSrkP9CzVY6odce4TdKqdUVFN1WgE+SUuSUpH3AAVa3E5/keuX/vxv7ZFVLqL/ul6X/1w7/bSqzHoaz9J+w9O5F0kReG7RVrZWpLc4gv47LQ2FKCT/OKVfzRV3bOaehab27tESK0gOvxkSZTie7ry0hSlE+ffA9AAPKquv2kpeqeGXTjltZU/OtjKZbbSBlTqPiStAHmcHmAHUlIA7119h92LDL0tB09qC5R7dcoDSY7TklwIaktpGEELPTnxgEE5JGRnJAPoZjxLkuZ9lp9otPtIdbV3QtIUD59jWbNTR0ax4rGbPdUh2BFdQ0GldQW2o5e5SPMKXzZHoqrg1runovS0MuybuxOknHJEguJedVnzIBwkY65UR26ZOBVP7vF3Se6tl3VsgTPtNx8J4PNqyha/D8NaAew52uoPrzelImZtGlqgm/dliXrau9/SG0lyBHVOjrx1QtoFXT0ykKSfZRqRaS1RYtVWtu42O4MymlJBWgKHiNH9Fae6T7H+qqw4itw7axpqXpCySkTrrOQpEoRzziMwAVOcxGfiKUkY7hJKjgAZ1SeTaTW08vB9/ivfv5en+zTV5VRvB9/ivfv5en+zTV5VmXUxT9FClKVqbilKUApSlAKUpQHg1FdodhsE+93Bzw4kCM5JeV3IQhJUcep6dq+bl5uMm8XmdeJgAkz5Lsp4DsFuLK1Ae2Sa1Dxoa+RFtUfb63PZkzOSVcik/YZCsttn3UpPMR6IGeihWU6qr6pultXce48nLN0qDrS6y6exfcVO9ltybnttqlM9guyLTIUE3KEk9HkfppB6eInuD0z2JwekEpXHGTi8ov61GFaDpzWUzSvFrCv2t9QaVe0nYrvfLX9VmSzMgwXHmFeOsY+NKSAeVtJwcdFD1qDaQ4e9wLwTJvUZnTNtQkrdkTVBxwIAySlpBJJHooo+dXdwW6geum18qzSHCtVmnKZZyeoZcSHEj7lKWB7ACrtnR0y4T8VZIS82ptRHoRj/nVnG3hW/qPvPG1dVr6fmzppLbxnv8c+Hf6yoNmLhsfoyyfRNM6ysKpMnlMmXNnNtyZKvIEL5SAM9EAADJ6ZJJtSLfbHKAVFvNufB7FuShWfwNfNibBkWybItk1vkkw3Vx30forQopUPxBrzllo92kfsioY3rgsbSxr+TkK8nU7Vtvvaz9j6cGdCAyZkcD18Uf8A7Xkl6i0/ESVS77a44Hcuy204/E180vBZ/wBE3+yK7WhtLS9Xautum7W2hMqc8Gw5yAhpGMrcI8wlIUrHnjHnWyv23hR+Zzy8mKcE5TrcL1fyfQ6NL01rGySG4sq1361uksveC6iQyojBKSQSMjIPt0qs7vw76Nly1PQbhd7c2o58BDqHEJ/VK0lX4k1aGkrBbNL6bgafs8cMQYLQaaT5nzKj6qUSVE+ZJPnVVbqcROldIzHrTZY69R3VlRQ6GXQ3GZUO6VO4OVD0SFdQQSk13uqqccyeDzVOzldVXChFy+3r7kTTbfbLTWhHXpNp+mvzXm/DckyXuZRRkHl5UgJAyB5Z964192M0Ddbo5cBGmwFOLK3GYb/I0onvhJB5R7JwKoOZxR7huvlca2abjtZ+FsxnlnHoVeKM/cBUm0ZxVSg+hnWOmmVNE4VKtayCn/ZOE5/b+41Cr2m31LCfk7eRjnan6kzQ2mdHaa03ZXrPaLRHZhvpKZCVDxC+CCD4ilZK+hIwemDjtUJXsHt6q4mV9HuSWSc/RBMUGvln7eP51T/Seo7JquyM3rT9xZnwXuiXG85SR3SpJ6pUPNJAIr86t1LYtJ2V28aiuTFvhNnBccPVSvJKUjqpRwcJSCTiunfxnJUdjJy2beemO84erds9KaltFstMyK7Gg2wKTFZiOeElAUAD5de39dS2DGbhwmIjOfCYbS2jJycJGB/VWbtU8VsNqQprTGk3pbQOBIuEkM83uG0hRwfdQPtXMtPFhckvpF20VFcZJ+JUWepKkj2CkEE+2R8653d0s4yWkdBvnHcqfzX3NI6z03bdW6fesd3DxiPKQpfhL5FZSoKHX5gVwpe1+l5WhIWi3RN+qoUhUhkB/DnOVLUcqx1GXFf0U2x3S0fuGwoWKepuc2jnet8oBuQ2PXlyQpPUfEkkdR1zU2qeM1JZiysq0ZUpuNSOH6znaas0PT1hh2W3hwRIjfhteIrmVj3PnUH1zstozVM524+FJtU51XM67BUlKXVeZUhQKcnuSACT3JquP7qJz8qvqP8AIRGPrD6F431x/wCr4fNy+B9+M/fU13p3zsG3spVmiRTer+EhS4qHeRuOCMjxV4OCQchIBOMZ5QQTErmnhyz0O2WkXanGm4cy6dPvx7z8ad4fdF22YiTPkXG78hyGH1pQyT5ZShIJ+ROD5irPuNltNwsi7JNt0V62rbDRiqbHhhI7ADyxgYx2wMdqyK5xSbiGQpTdr0uhvJ5W1RX1EDyyfGGT74HyqxdteJyyXiezbdZW1NhddUEInNulyLzH9PICmhnzPMkdyQOtaxvKc3jJPV0C8ow3bM+zk7t04ctFyphejXG8RGif7wHG3EpHokrQVfiTUq0ztJovT9kuFthQnnF3CI5DkzHnAqQppaSlQSrACMg/mgZwM5xU9BBAIIIPYioruZr/AE3t7Y03TUMpSS6oojRWUhT8lQGSEJyO3TJJAGRkjIrolPCy2VNKg6k1GEctn9Nv9EWTQ8KVDsYkhqU6HXPHd5zzBIHTp6CpNWRNScVGrJMkjT2n7RbY2SB9MK5LpHkcpUhKflhXzrlROJ7cppwKdjackIz1SqE4np7FLorld7Sz1LuPk7euOcJerJtClULtXxJ2fU95hWHUVles1wmvIjxnmFmQw66shKUnoFIJUQB0I9VCr6qenUjUWYsrLm0rWstlWOGKVy9VahsulrG/er/cGYEBgZW65nqfJKQOqlHySASfKs36y4q5RkrZ0dplgMpOEyrotRK/fwmyMD5rz7CtalaFP0mSWmnXF3/ajlePcakpWO7dxTa9akhU+y6clsfnNtNPMqPyUXFAfsmrv2j300nr6Q3a1pcsl8WPhhSVhSXj5hpwYC/kQlXc8uATWkLmnN4TJ7nRru3jvlHK9XP8lq0pSugqyrLpsJt5eL3MvV8j3W6z5rxefekXF1JUo+yCkAAYAA6AAAdBX+o4e9ok4P5KLJHrdJZ/6tWlSo+xp/8AlHZ+4XaWFVl8WVYvh72iVn/sotJPpdJY/wCrXNuPDTtfJQpMeLdoCiOimLgtRH/9OYfiKuWs28U+8si1vP6D0nLUzM5QLpOaVhTIIz4LZHZZBypQ+yCAOpPLFVjRpxzKKOyxrahdVVTp1ZfF4SPNG1dt1w+uXqxaZnXPVl0luoU9HU62ERloBHK48lIAPU5CUqII6gVEp3FBuNKmctttOnY6VrCWWTHddWSegSVeIAST6AVRQASAAAAOwFd3buOmXuJpiIsZS9eoTZ+Sn0D/AJ1XfqJtqMeEet/araCdSqt8u9vv93QuXi921k2m9HcC2s89vnlCLmG09I8nokOY8kOdB7L7nKxWfa+m8+JFnwn4M6O1JiyG1NPMuoCkOIUMFKgehBHTFZI3r4dbpY3X71oJh+6WokrXbgSuTGHfCM9XUeg6rHT7XUie6tXnfArNF1mDgqFd4a6Pua8Pz/7n+tQcD2lEFq963kt5WV/VsIkdkgJW8oeuSW058uRQ8zWYFApWpCgUrQopWlQwUkdwR5H2rfnDnaUWfZLS0dA6yIKZqz6qfJeP7+PkBUdlDdUy+46/KK4dK02r/J493Ur7i83OladtrGirDJUxcbkyXZz7ZIWxGJKQlJ8lLIUM9wlJ/SBFNbB7MztyHnLjOkO2zTkZfhrkNJHiyFjuhrIIGPNRBA6AAnPLH+IO8OXfePVs1aioMTlxUA9khgBrA9soJ+8nzrdG3en4uldDWbT0RCUtwoiG1EDHO5jK1n3UsqUfcmpYR/UVm5dEcNeq9KsKcaXE58t/X4ZSRF7VsdtXb4YjI0fBk9OrktS33Fe/Mskj7sCq83a4arJLtj9y2/C7bcmklYt7rylsSfPlSpZJbUfLry+WB3GiaV2yoU5LDR5+jqd3SnvVRv2vKZWmzeh7TtHtw+/cnmkTVMfTb3MzlIKEElI/iIGQPXqe5rJmvdUan3l3JZEaPIfXIeMezW0HAjtnr18gogcy1n0PXlSANOcYd3ctmy0mK0soVdJrEMkHBKclxQ+RS0QfUE1V/BnBsdsOodc36fAgtxuS3xn5b6WkN5AcdOVEDqPCGfn61yV47pxorhF7p1R06FXUKi3Tbwvz3/BYJroDhi0nb7e27rKRIvlwUkF1pl9bEZs+ieTlWr9YkZ/RT2ruah4b9sLlDW3b7dNs0gj4ZEWa4spP6jqlJI9eg+Y717NS8QW11l8RDd9cu76BnwrbHU6FewcOG/8AiqstTcWBAWjTmkAlOPhfucoDB922wf363btoLDx9Tlpx1m4nvi5L34XweEVDuHovVmz+toijMW26hZftd1igpS6E9DgHPKoZAUg5GFfnJPXYuxmv2txdBR7wpCGriwr6NcWUAhKH0gElIP5qgQod8ZxkkGso6n1hu1vLFZgmzPXK3pfDrbVttP8AAocAI5vGUFFOASOqwOuDV0cJu3+vND3C9PaltrVvt9xjtcrSpSHHQ6hRweVBIAKVqz1z0HSorZ4q+YntZ36vBVLNO4lHtY+D6+75+0y1eZDkPW1wmNBJcj3Z55AUMjmS+VDPtkVoDYPZFjV0P8v9xVPzvrR1UqPDUso+kBZKi+8U4JCySQkYGME5BwM/XqKqdra4QUq5VSbu6wFehW+U5/pr6RQozEOGxDjNpaYYbS00hIwEpSMAD5AVraUlOTcuiJddvZ21GEaTw5d/fhY+pGDtnt0Yf0P8hNNeD+j9WM98Yznlzn371kzic2vhbe6ihzbGlxNjuoX4TS1Ff0Z1OOZvmPUpIIKcknooeVbfqh+N2MHdq7ZIwOZi9NHOOuCy8kj8SPwrquqUXTbx0KXRb2tC7jFybUuGj0cHGr5F/wBuX7DOeLsmwOpjtlRyr6MpOWgflyrQPZAqh+KW7Tr5vldYTro8K3lmDEQtWEtpLaFEn0ytaiT6Y9Kn/Aio/XGr056GPDJ/af8A/wBry8YG2d0a1K/r+0w3ZdtmMpFzDaeYxnEICPEUP9GUJTk9gUknGa5p7p2yZbW/Y2+s1IvjK49rw/v9C4tCbD7daatjTUyxRL9P5B48u5NB7nV58rasoQM9gBnGMknrXbum0m2NyjKjv6EsDSVDBVFhojrHyW0EqHzBrO22/E5fbJa41s1PaU35hhAbRNaf8KTyAdOcEFLiuwzlOe5yck2xYeJfbO4YTOeu1nWemJcIrH4slYx88VPTq27jhYRWXVlqtOo5PdL1p5+nK+BGrtw5N2PXendS6KmuOQod5hyJdvmOZU20h9ClKbc/OwBnlV1wDhROEnRhIAyTgCuPpfVOm9URVSdO3y33RpP2zFfSso9lAHKT7HFcfe25vWfaLVVxjrU2+3a30tLT3QpSSkKHuCoH7qnjCFNOUehX1q9xd1IUqz5XHPXnxMfb8a/uO5m4Ko9uLsi0xpH0SzxGcq8Yk8viAfnLcV2/ilI9c3ZtVw02CDbWZ2vgu63NwBaoTbykR4578pKCC4oeZJ5fLB7mruDewxrru6JsloLbs9vcksg9QHlFLaTj2Stwj0IBra1cltSVXNSfOS71i9lZ7bO2e1JctdfzvfjkrK+7DbWXWEqOnTDVuXjCH4DimXEH16HlV/OBHtWU969r7ztfqBjMhyXapK+e3XFA5FcyevIvH2HE9wR0UBkYwoJ3zVd8SFijX7ZfUjb6R4kGIu4sLx1QtgFzp80pUk+yjUtxbxlFtLDRw6Xq1elXjCcnKLeHnnr3o5HDDuS/r3RjkS7uhy+2gpalL7F9tQPhu/M8qgr3ST0yBSsu7D60f0NrCXdGjlD9vXHWg9QT4jagSPUcp/E+tKxQuU4Lc+SXU9HqK5k6MfNfJv2lKV2HniEb4a3Rt/t1cL6goM5WI1vbWMhchYPLkeYSApZHog18/ZDz8mQ7JkvOPvvLU4664rmU4tRypRPmSSST71uffraibugi1NNaoFoj2/xF+AYRfS64vA5ifETggAgdD9pXrVC6k4Ydf25K3bRNtF7bSMhCHTHeUfQJWOT8V1W3lOrOXC4R6/Qbmyt6OJTSnLrn5LPT1+8o6pfsogObwaRSoZH1vHV+CwR/SK4up9N6g0xOELUVmnWt9RIQJLRSlzHfkV9lY90k11tnnvo+7WkHCM5vURH7TqU//KuGCams+J6SvJTt5uLzlP6H0SpSlegPlhCdwtqtC665nr9ZGjNKcCdGJZkDpgZWn7QHkFcw9qldmt7Fps8K1xSosQ47cdrmxnlQkJGcADOB6V66VqopPKRLKtUlBQlJtLovA+f/ABGWRyzby6piLQUIlSjMaVjopL6Q4SPX4lLHzBrbW1epY+r9vbJqCOtJMmIjx0pOfDeSOVxH3LCh91VrxW7WytZ2VjU2n4yn77amlIXHQMrlx88xQn1Wk5UkefMsdSRWeNkd2r1tncXm2mPrCyy3OaZAWrkIWOniNn81eAAQRhQABxgEV6l+nrPd0Z6qpS/drCDpvz4cY/PHGV8De9KqC18R+1UuGl6Vdp9tdIyWJFueUtJ9MtJWn8DUA3W4m471vete3sWSl91JQq6y2wgNgju02ckq914wR9lVdcrmlFZyUVLSLypPZ2bXrawviTzjCtDlz2WlSWkFarZNYmEAZITktqP3JdJPsDWW9nNtn9zNRSbVFvNvtjsVgPqMhtS3Fo5uUltIwDykjOVDHMnvk42BtFrG2bt7YOG4RkreW0q33mMUkILhRhfL/FUlXMMHoFYPUVkrWOn9V7KbmtLiSHWXY7inrVP5colM9sEdicHlWjyJ9CknkuYxco1esS/0erVp0qlmntqLLWfz8TyX5pvhZ0fDCF36+Xe7uj7SGymMyr7kgrH7dWZpnarbrThbXatIWpDzfVD77PjvA+occ5lf01Xu33Evoy7wmmtVpd09cgAHD4a3ozh9UrSCUjzwsDGcZPepDqLiB2ttERTrWoDdXsZRHt7C3FL9uYgIT/OUK6IO3isxwVNzHVqk9lRSfs6fLgtLKEciMpTnolPby7D7q/VYK3P3J1XunrSAqExKihl3w7Pb4Tii4hxR+1zDBU4enUYAAwMdSdnbW2rUVl0JbIGq7y7d7yhvMl9wg8pJyGwoDKuUYHMclRBPngbUq6qyaiuF3kF9pcrKlCVSS3Pu71+fmTBX+dD/AHh/+1X0cr5x/wCdD/eH/wC1X0cqCx/yLXyl/wCn2P8A0KpDjU/yQR/9bsfuOVd9Uhxqf5II/wDrdj9xyum4/tS9hTaV/wA2l7UQTgS/w1q/+TQ/3nq1VWVeBL/DWr/5ND/eeqU7tbz3bbbes21+L9Z6fft0d12KCEusrKnAVtKPTOAMpPQ4HVPUmC3qRp0E5FjqtpUutSqQp9cJ/JFhas2a211M8uRcdKxGpKyVKfhlUZalHzUWykKP6wNVvqHhU0zIQtVg1Nd7e6eqUykNyWx7YAQr8VGrL0jvBtxqdltUHVMCM+v/AMrOcEZ4HGccq8c3zTke9d+76y0jaIxk3PU9mhtD852a2nPsOvU+wqV06NRZwjip3Wo20tick/B5+jMPa60ZrXZrV0GSuaI0lXM5b7nAcIS6EkcyTkAgjKeZCgQQcfEK1Am9St1+F+5T0Rki5zrTJacYaHRUlrmBCQT0ClIBAJ6BQzVFcUe69o1/Ot9p06lblpti1vGa6goMh1Qx8CTghCRnqcEk9gACrQ3C/Ypdg2WsrE9pTMmV4sxTahgpS6sqRn0PIUkjyJxXNbpdpKEH5uC61Oc/0dG4rxxVT+XP8ewzfwgajjWTd5mNKdDbF5hrhIUogDxSpK28/PkUke6xW3awvxF7bzNvNbKuNtadbsNxfL9ukNfCIzuSosZH2Sk9UeqQMElKsWftVxNwk21m2bhR5KJTSQn60itc6HgPNxtPVKvUpBBPXCe1LaqqWac+DXV7GV8o3dstya5Xf+dzNM1W3ExqGNp7Zi/+M4A9co6rbGRnqtbwKTj5I51H2Sa4184ktroMFT0C4XC7v/mx41vdbUT7qeShIH3/AI1l7dbcTUe6ep4z0qKptpC/Bttri8zvIVkDAwMuOKOBnAz0AAqW4uYRi1F5bOLS9HuJ1ozqxcYp5546eo6HDxoleuNZToJGGI1vU8twj4UqLjYSD7kc/wCyaVqPhv22Xt5oki5IR9e3RSX5/KQrwsD4GQR3CATk9RzKVg4xSs0LaKgty5Manq9SdzLsZeauC0KUpXWUIpSlAeO82q2Xq3O2672+LcIbow4xJaS4hXzBGKoLWHDqxbNVWrVW37ym0wrjHlvWmQ5kcrbqVnwXD1B+H7Kye/RQwBWiaVHOlGfpI6ra9rWzfZy4fVdzFKUqQ5RSlKAVVu6Wxmi9dy3Lmtt6z3dzquZBwPGPq4ggpUf43RR6fFgYq0qVrOEZrEkTULirQlvpSwzJ0zhQv6HsRNZ2x5r9J2CttX4Bav66kujuFayRJKJGq9RSbshJB+ixGvozavZSuZSyP1Sg1oylQq0pJ5wWM9dvpx2ufwSX+jxWO02yx2pi1WeDHgQY6eVphhAQhI+Q8yepPmTk14tZaV0/rCyrs+o7YxPiKPMlKxhTavJaFDqhXU9QQepHnXapU+E1gq1Umpb0+fHvMv6q4UlmQt3SurEpZP2Y9yYypP8AtUd/2PvNcm0cKepnXx9b6rtERrPUxWXH1EfzuQCtbUrndnSbzgto69fKO3f8kV/tVtFo/btJkWqM7Mui08rlxmELewe6U4AShPskAnpknFWBSlTxiorCRV1q1StNzqPLKI/uZdL/AJRfXf5SXzxfpv0zw8M8nP4nPj7GcZ96velKxCnGHoo3uLutcY7WWcdBUQ3Z0Fb9xdLosFynS4TKJSJIcjcvPzJCgB8QIx8RqX0raUVJYZFTqSpTU4PDRXGze0Vn2xlXORa7rcZ6rihpDglcnwhsqIxypH6Z71595tltO7kPJuT0qTa720yGW5rPxpUgElKXGycKAKiehSrr3x0qz6Vp2UNuzHB0K+uFW7fd53iYyvnC/uFFdWm3zLDdGM/AfHWytQ90KSQP2jXOgcNO57r3KqDZYY7c7s4Y/wCBKj/RW3qVzuypFovKS9Sxx8P5M+bW8M9psc9i7ayuDV8kskLbgtNlMVKh+nn4ncHyISPUGtB0pXRTpRprEUVN1eVrqe+rLJ4r7aLZfbTItN4gx58GSnleYfQFIUO/b1BwQe4IBFZ61lwq26TLXI0lqV23NKJP0ScyX0p9kuBQUB+sFH3rSVKVKUKnpI2tb+4tH/Rlj6fBmTbfwo6gW+BcNYWuOznqWIjjqvwKkirt2q2b0dt6sTLfHdn3YpKVXCYQpxII6hAACWx3+yMkdCTVi0rSFvTg8pE9zq13cx2Tnx4Lj6ClKVOVopSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUApSlAKUpQClKUB//9k=" alt="Clínica Censo" style={{ height:46, width:"auto", objectFit:"contain" }}/>
          </div>
          {!isMobile && <>
            <div style={{ width:1, height:28, background:"rgba(255,255,255,0.25)", margin:"0 4px" }}/>
            <div>
              <div style={{ fontSize:12, fontWeight:700, color:"#fff" }}>Dashboard</div>
              <div style={{ fontSize:10, color:"rgba(255,255,255,0.65)" }}>Smart Pixeon · Parauapebas</div>
            </div>
          </>}
        </div>

        {/* Breadcrumb */}
        <div style={{ flex:1, display:"flex", alignItems:"center", gap:6, fontSize:13, minWidth:0, overflow:"hidden" }}>
          {currentItem && (
            <span style={{ color:"#fff", fontWeight:600 }}>{currentItem.label}</span>
          )}
        </div>

        {/* Status */}
        <div style={{ display:"flex", alignItems:"center", gap:5, flexShrink:0 }}>
          <span style={{ width:7, height:7, borderRadius:"50%", background:online===null?"#D1D5DB":online?"#6EE7B7":"#FCA5A5", display:"inline-block" }}/>
          {!isMobile && <span style={{ fontSize:12, fontWeight:600, color:online===null?"rgba(255,255,255,0.6)":online?"#6EE7B7":"#FCA5A5" }}>{online===null?"…":online?"Online":"Offline"}</span>}
        </div>
        {!isMobile && <div style={{ width:1, height:22, background:"rgba(255,255,255,0.25)", flexShrink:0 }}/>}

        {/* Usuário logado */}
        <div style={{ display:"flex", alignItems:"center", gap:8, flexShrink:0 }}>
          {!isMobile && <div style={{ textAlign:"right" }}>
            <div style={{ fontSize:12, fontWeight:700, color:"#fff", lineHeight:1.2 }}>
              {user?.nome?.split(" ").slice(0,2).join(" ") || user?.login}
            </div>
            {user?.admin && (
              <div style={{ fontSize:10, color:"#FCD34D", fontWeight:700 }}>Admin</div>
            )}
          </div>}
          <button onClick={logout} style={{
            padding:isMobile?"6px 10px":"5px 12px", borderRadius:8,
            border:"1px solid rgba(255,255,255,0.3)", background:"rgba(255,255,255,0.1)",
            color:"#fff", fontSize:isMobile?15:11, fontWeight:700,
            cursor:"pointer", transition:"all 0.12s", lineHeight:1,
          }}
            onMouseEnter={e => { e.target.style.background="rgba(255,255,255,0.25)"; e.target.style.borderColor="#fff"; }}
            onMouseLeave={e => { e.target.style.background="rgba(255,255,255,0.1)"; e.target.style.borderColor="rgba(255,255,255,0.3)"; }}>
            {isMobile ? "↩" : "Sair"}
          </button>
        </div>

        {!isMobile && <div style={{ display:"flex", alignItems:"center", gap:6, flexShrink:0, position:"relative" }}>
          <div style={{ display:"flex", background:"rgba(255,255,255,0.12)", borderRadius:8, padding:3, gap:1, border:"1px solid rgba(255,255,255,0.25)" }}>
            {PERIODS.map(p => (
              <button key={p.id} onClick={()=>{ setPeriod(p.id); setShowDatePicker(false); }} style={{
                padding:"5px 13px", borderRadius:6, border:"none", cursor:"pointer", fontSize:12, fontWeight:600,
                background: period===p.id && !showDatePicker?"#fff":"transparent",
                color: period===p.id && !showDatePicker?"#8B1A1A":"rgba(255,255,255,0.8)",
                boxShadow: period===p.id && !showDatePicker?"0 1px 3px rgba(0,0,0,0.08)":"none",
                whiteSpace:"nowrap", transition:"all 0.12s",
              }}>{p.label}</button>
            ))}
            <button onClick={()=>setShowDatePicker(v=>!v)} style={{
              padding:"5px 13px", borderRadius:6, border:"none", cursor:"pointer", fontSize:12, fontWeight:600,
              background: showDatePicker?"#fff":"transparent",
              color: showDatePicker?"#8B1A1A":"rgba(255,255,255,0.8)",
              boxShadow: showDatePicker?"0 1px 3px rgba(0,0,0,0.08)":"none",
              whiteSpace:"nowrap", transition:"all 0.12s",
            }}>
              📅 {customLabel || "Personalizado"}
            </button>
          </div>

          {/* Date picker dropdown */}
          {showDatePicker && (
            <div style={{
              position:"absolute", top:"calc(100% + 8px)", right:0, zIndex:9999,
              background:"#fff", borderRadius:12, boxShadow:"0 8px 32px rgba(0,0,0,0.15)",
              border:"1px solid #E5E7EB", padding:16, minWidth:280,
            }}>
              <div style={{ fontSize:12, color:"#6B7280", fontWeight:700, textTransform:"uppercase",
                letterSpacing:"0.07em", marginBottom:10 }}>Intervalo personalizado</div>
              <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:12 }}>
                <div>
                  <label style={{ fontSize:11, color:"#9CA3AF", display:"block", marginBottom:4 }}>De</label>
                  <input type="date" value={dateIni} onChange={e=>setDateIni(e.target.value)} style={{
                    width:"100%", padding:"7px 10px", borderRadius:8, border:"1px solid #E5E7EB",
                    fontSize:12, color:"#111827", outline:"none",
                  }}/>
                </div>
                <div>
                  <label style={{ fontSize:11, color:"#9CA3AF", display:"block", marginBottom:4 }}>Até</label>
                  <input type="date" value={dateFim} onChange={e=>setDateFim(e.target.value)} style={{
                    width:"100%", padding:"7px 10px", borderRadius:8, border:"1px solid #E5E7EB",
                    fontSize:12, color:"#111827", outline:"none",
                  }}/>
                </div>
              </div>
              <button
                disabled={!dateIni || !dateFim}
                onClick={()=>{
                  if(dateIni && dateFim){
                    setPeriod(`custom:${dateIni}:${dateFim}`);
                    setCustomLabel(`${dateIni.slice(5)} → ${dateFim.slice(5)}`);
                    setShowDatePicker(false);
                  }
                }}
                style={{
                  width:"100%", padding:"8px", borderRadius:8,
                  background: dateIni&&dateFim?"#8B1A1A":"#E5E7EB",
                  color: dateIni&&dateFim?"#fff":"#9CA3AF",
                  border:"none", cursor:dateIni&&dateFim?"pointer":"not-allowed",
                  fontSize:13, fontWeight:700,
                }}>
                Aplicar
              </button>
            </div>
          )}
        </div>}

        {/* Período mobile — strip abaixo do topbar */}
        {isMobile && (
          <div style={{ width:"100%", borderTop:"1px solid rgba(255,255,255,0.15)", padding:"4px 10px 6px", background:"linear-gradient(135deg, #8B1A1A 0%, #6B1414 100%)" }}>
            <div style={{ display:"flex", overflowX:"auto", gap:4, WebkitOverflowScrolling:"touch", scrollbarWidth:"none" }}
              className="hide-scrollbar">
              {PERIODS.map(p => (
                <button key={p.id} onClick={()=>{ setPeriod(p.id); setShowDatePicker(false); }} style={{
                  padding:"5px 14px", borderRadius:6, border:"none", cursor:"pointer", fontSize:12, fontWeight:600,
                  background: period===p.id && !showDatePicker?"#fff":"rgba(255,255,255,0.12)",
                  color: period===p.id && !showDatePicker?"#8B1A1A":"rgba(255,255,255,0.85)",
                  whiteSpace:"nowrap", flexShrink:0, transition:"all 0.12s",
                }}>{p.label}</button>
              ))}
              <button onClick={()=>setShowDatePicker(v=>!v)} style={{
                padding:"5px 14px", borderRadius:6, border:"none", cursor:"pointer", fontSize:12, fontWeight:600,
                background: showDatePicker?"#fff":"rgba(255,255,255,0.12)",
                color: showDatePicker?"#8B1A1A":"rgba(255,255,255,0.85)",
                whiteSpace:"nowrap", flexShrink:0, transition:"all 0.12s",
              }}>📅 {customLabel || "Período"}</button>
            </div>
            {showDatePicker && (
              <div style={{
                position:"fixed", top:0, left:0, right:0, bottom:0, zIndex:9999,
                background:"rgba(0,0,0,0.45)", display:"flex", alignItems:"center",
                justifyContent:"center", padding:16,
              }} onClick={()=>setShowDatePicker(false)}>
                <div style={{
                  background:"#fff", borderRadius:16, padding:20, width:"100%", maxWidth:340,
                  boxShadow:"0 8px 40px rgba(0,0,0,0.25)",
                }} onClick={e=>e.stopPropagation()}>
                  <div style={{ fontSize:14, fontWeight:700, color:"#111827", marginBottom:14 }}>Intervalo personalizado</div>
                  <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10, marginBottom:12 }}>
                    <div>
                      <label style={{ fontSize:11, color:"#9CA3AF", display:"block", marginBottom:4 }}>De</label>
                      <input type="date" value={dateIni} onChange={e=>setDateIni(e.target.value)} style={{
                        width:"100%", padding:"8px 10px", borderRadius:8, border:"1px solid #E5E7EB",
                        fontSize:13, color:"#111827", outline:"none",
                      }}/>
                    </div>
                    <div>
                      <label style={{ fontSize:11, color:"#9CA3AF", display:"block", marginBottom:4 }}>Até</label>
                      <input type="date" value={dateFim} onChange={e=>setDateFim(e.target.value)} style={{
                        width:"100%", padding:"8px 10px", borderRadius:8, border:"1px solid #E5E7EB",
                        fontSize:13, color:"#111827", outline:"none",
                      }}/>
                    </div>
                  </div>
                  <button disabled={!dateIni||!dateFim}
                    onClick={()=>{ if(dateIni&&dateFim){ setPeriod(`custom:${dateIni}:${dateFim}`); setCustomLabel(`${dateIni.slice(5)} → ${dateFim.slice(5)}`); setShowDatePicker(false); } }}
                    style={{
                      width:"100%", padding:"10px", borderRadius:8,
                      background:dateIni&&dateFim?"#8B1A1A":"#E5E7EB",
                      color:dateIni&&dateFim?"#fff":"#9CA3AF",
                      border:"none", cursor:dateIni&&dateFim?"pointer":"not-allowed",
                      fontSize:14, fontWeight:700,
                    }}>Aplicar</button>
                  <button onClick={()=>setShowDatePicker(false)} style={{
                    width:"100%", padding:"8px", borderRadius:8, border:"1px solid #E5E7EB",
                    background:"transparent", color:"#9CA3AF", fontSize:13, fontWeight:600,
                    cursor:"pointer", marginTop:8,
                  }}>Cancelar</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── BODY ── */}
      <div style={{ flex:1, display:"flex", overflow:"hidden", position:"relative" }}>

        {/* Backdrop — fecha o menu flutuante ao clicar fora */}
        {!isMobile && !collapsed && (
          <div onClick={()=>setCollapsed(true)} style={{ position:"absolute", inset:0, zIndex:400 }}/>
        )}

        {/* SIDEBAR — rail sempre compacto (não altera o layout) */}
        <aside style={{ width:SW, flexShrink:0, background:"linear-gradient(180deg, #8B1A1A 0%, #6B1414 100%)", borderRight:"1px solid rgba(255,255,255,0.12)",
          overflow:isMobile?"hidden":"visible", display:"flex", flexDirection:"column", overflow:"hidden", position:"relative", zIndex:401 }}>
          {/* Toggle */}
          <div style={{ padding:"10px 10px", borderBottom:"1px solid rgba(255,255,255,0.15)", display:"flex", justifyContent:"center" }}>
            <button onClick={()=>setCollapsed(v=>!v)} title={collapsed?"Abrir menu":"Fechar menu"} style={{ width:28, height:28, borderRadius:7, border:"1px solid rgba(255,255,255,0.3)", background:collapsed?"rgba(255,255,255,0.12)":"#fff", cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center" }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke={collapsed?"#fff":"#8B1A1A"} strokeWidth="2.5" strokeLinecap="round">
                {collapsed?<><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></>:<polyline points="15 18 9 12 15 6"/>}
              </svg>
            </button>
          </div>

          <div style={{ flex:1, overflowY:"auto", padding:"6px" }}>
            {NAV.filter(n => n.id === "admin" ? user?.admin : podeVer(n.id)).map(n => {
              const active = page === n.id;
              return (
                <button key={n.id} onClick={()=>{ setPage(n.id); setCollapsed(true); }} title={n.label}
                  style={{ width:44, height:44, borderRadius:10, border:"none", cursor:"pointer",
                    background:active?"rgba(255,255,255,0.15)":"transparent",
                    display:"flex", alignItems:"center", justifyContent:"center",
                    margin:"0 auto 4px", position:"relative", transition:"all 0.15s" }}>
                  <div style={{ width:30, height:30, borderRadius:8, background:active?"#fff":"rgba(255,255,255,0.15)",
                    display:"flex", alignItems:"center", justifyContent:"center",
                    boxShadow:active?"0 3px 8px rgba(0,0,0,0.3)":"none" }}>
                    <Icon name={n.icon} size={15} color={active?n.color:"#fff"}/>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>

        {/* PAINEL FLUTUANTE — abre por cima do conteúdo, sem empurrar o layout */}
        {!isMobile && !collapsed && (
          <div style={{
            position:"absolute", top:0, left:SW, bottom:0, width:230, zIndex:402,
            background:"linear-gradient(180deg, #8B1A1A 0%, #6B1414 100%)", borderRight:"1px solid rgba(255,255,255,0.12)",
            boxShadow:"4px 0 24px rgba(0,0,0,0.25)",
            display:"flex", flexDirection:"column", animation:"fadeIn 0.15s ease",
          }}>
            <div style={{ flex:1, overflowY:"auto", padding:"10px" }}>
              {NAV.filter(n => n.id === "admin" ? user?.admin : podeVer(n.id)).map(n => {
                const active = page === n.id;
                return (
                  <button key={n.id} onClick={()=>{ setPage(n.id); setCollapsed(true); }}
                    style={{ width:"100%", display:"flex", alignItems:"center", gap:10,
                      padding:"9px 12px", borderRadius:10, border:"none", cursor:"pointer",
                      background:active?"rgba(255,255,255,0.15)":"transparent",
                      borderLeft:active?"3px solid #fff":"3px solid transparent",
                      color:active?"#fff":"rgba(255,255,255,0.8)",
                      fontSize:13, fontWeight:active?700:500,
                      textAlign:"left", transition:"all 0.12s", marginBottom:2 }}>
                    <div style={{ width:28, height:28, borderRadius:8, background:active?"#fff":"rgba(255,255,255,0.15)",
                      display:"flex", alignItems:"center", justifyContent:"center", flexShrink:0,
                      boxShadow:active?"0 3px 8px rgba(0,0,0,0.3)":"none" }}>
                      <Icon name={n.icon} size={14} color={active?n.color:"#fff"}/>
                    </div>
                    <div style={{ minWidth:0 }}>
                      <div style={{ fontSize:13, fontWeight:active?700:500, lineHeight:1.2, whiteSpace:"nowrap", overflow:"hidden", textOverflow:"ellipsis" }}>{n.label}</div>
                      {active && <div style={{ fontSize:10, color:"rgba(255,255,255,0.75)", marginTop:1, opacity:.9 }}>{n.desc}</div>}
                    </div>
                  </button>
                );
              })}
            </div>
            <div style={{ padding:"10px 14px", borderTop:"1px solid rgba(255,255,255,0.15)", fontSize:11, color:"rgba(255,255,255,0.6)" }}>
              Parauapebas · PA · v2.0
            </div>
          </div>
        )}

        {/* MAIN */}
        <main style={{ flex:1, overflowY:"auto", padding:isMobile?"12px":"32px 40px", minWidth:0, paddingBottom:isMobile?70:undefined }}>
          <div style={{ marginBottom:24 }}>
            <h1 style={{ fontSize:22, fontWeight:700, color:"#2D1B1B", letterSpacing:"-0.3px", margin:0, borderLeft:"3px solid #8B1A1A", paddingLeft:12 }}>
              {currentItem?.label}
            </h1>
            {currentItem?.desc && (
              <p style={{ fontSize:13, color:"#6B7280", marginTop:4 }}>{currentItem.desc}</p>
            )}
          </div>
          {(RENDER_MAP[page] || (() => <div>Página não encontrada</div>))(period)}
        </main>
      </div>

      {/* ── MOBILE BOTTOM NAV ── */}
      {isMobile && (
        <div style={{
          position:"fixed", bottom:0, left:0, right:0, zIndex:1000,
          background:"linear-gradient(135deg, #8B1A1A 0%, #6B1414 100%)", borderTop:"1px solid rgba(255,255,255,0.15)",
          display:"flex", alignItems:"center", height:60,
        }}>
          {[
            { id:"clinica",   icon:"🩺", label:"Clínica" },
            { id:"recepcao",  icon:"🪟", label:"Recepção" },
            { id:"producao",  icon:"📈", label:"Prod." },
            { id:"painel_tv", icon:"📺", label:"Painel" },
          ].map(item => (
            <button key={item.id} onClick={() => setPage(item.id)} style={{
              flex:1, display:"flex", flexDirection:"column", alignItems:"center",
              justifyContent:"center", background:"none", border:"none", cursor:"pointer",
              padding:"4px 0", gap:2, color: page===item.id ? "#fff" : "rgba(255,255,255,0.6)",
            }}>
              <span style={{ fontSize:18 }}>{item.icon}</span>
              <span style={{ fontSize:9, fontWeight:page===item.id?700:400 }}>{item.label}</span>
            </button>
          ))}
          <button onClick={() => setPage(page==="menu_mobile"?"clinica":"menu_mobile")} style={{
            flex:1, display:"flex", flexDirection:"column", alignItems:"center",
            justifyContent:"center", background:"none", border:"none", cursor:"pointer",
            gap:2, color: page==="menu_mobile"?"#fff":"rgba(255,255,255,0.6)",
          }}>
            <span style={{ fontSize:18 }}>☰</span>
            <span style={{ fontSize:9, fontWeight:page==="menu_mobile"?700:400 }}>Mais</span>
          </button>
        </div>
      )}

      {/* ── MOBILE FULL MENU ── */}
      {isMobile && page==="menu_mobile" && (
        <div style={{ position:"fixed", inset:0, zIndex:999, background:"linear-gradient(180deg, #8B1A1A 0%, #6B1414 100%)", overflowY:"auto", paddingBottom:70 }}>
          <div style={{ padding:"16px 16px 12px", borderBottom:"1px solid rgba(255,255,255,0.15)",
            display:"flex", justifyContent:"space-between", alignItems:"center" }}>
            <span style={{ fontSize:16, fontWeight:700, color:"#fff" }}>Menu</span>
            <button onClick={() => setPage("clinica")}
              style={{ background:"none", border:"none", fontSize:22, cursor:"pointer", color:"#fff" }}>✕</button>
          </div>
          <div style={{ display:"flex", flexDirection:"column" }}>
            {NAV.map(item => (
              <button key={item.id} onClick={() => setPage(item.id)} style={{
                display:"flex", alignItems:"center", gap:14, width:"100%",
                padding:"14px 20px", background:page===item.id?"rgba(255,255,255,0.15)":"none",
                border:"none", borderBottom:"1px solid rgba(255,255,255,0.12)", cursor:"pointer",
                textAlign:"left", color:page===item.id?"#fff":"rgba(255,255,255,0.8)",
                borderLeft:page===item.id?"3px solid #fff":"3px solid transparent",
              }}>
                <div style={{ width:36, height:36, borderRadius:10, flexShrink:0,
                  background:page===item.id?"#fff":"rgba(255,255,255,0.15)",
                  boxShadow:page===item.id?"0 3px 8px rgba(0,0,0,0.3)":"none",
                  display:"flex", alignItems:"center", justifyContent:"center" }}>
                  <Icon name={item.icon} size={18} color={page===item.id?item.color:"#fff"}/>
                </div>
                <span style={{ fontSize:15, fontWeight:page===item.id?700:500 }}>{item.label}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700;800&display=swap');
        * { box-sizing:border-box; margin:0; padding:0; }
        html,body,#root { height:100%; background:#E5CACA; overflow:hidden; }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.45} }
        @keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
        @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
        @keyframes scaleIn { from{transform:scale(0.97);opacity:0} to{transform:scale(1);opacity:1} }
        ::-webkit-scrollbar { width:5px; height:5px; }
        ::-webkit-scrollbar-track { background:transparent; }
        ::-webkit-scrollbar-thumb { background:#D1D5DB; border-radius:10px; }
        button:focus { outline:none; }
        input,select,textarea { font-family:inherit; }
        @media (max-width: 767px) {
          main { padding: 12px !important; }
          table { display:block; overflow-x:auto; -webkit-overflow-scrolling:touch; }
        }
        .hide-scrollbar::-webkit-scrollbar { display:none; }
        .hide-scrollbar { -ms-overflow-style:none; scrollbar-width:none; }
      `}</style>
    </div>
    </MobileCtx.Provider>
  );
}
