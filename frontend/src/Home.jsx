import { useState, useEffect, useCallback } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";

const API = import.meta.env.VITE_API_URL || (
  window.location.hostname === "localhost" || window.location.hostname.startsWith("192.168.")
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "https://gestao.clinicacenso.com.br"
);

const brl = v => v != null ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v) : "--";
const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "--";

const SETORES = [
  { id: "todos",        label: "Visão Geral",       cor: "#8B1A1A", emoji: "🏥" },
  { id: "assistencial", label: "Assistencial",       cor: "#0891B2", emoji: "🩺" },
  { id: "ocupacional",  label: "Ocupacional",        cor: "#D97706", emoji: "🏭" },
  { id: "diagnostico",  label: "Diagnóstico",        cor: "#7C3AED", emoji: "🔬" },
  { id: "rci",          label: "Rec. Censo Imagem",  cor: "#059669", emoji: "🧪" },
];

const COR_SETOR = { "Assistencial": "#0891B2", "Ocupacional": "#D97706", "Diagnóstico": "#7C3AED" };

function Variacao({ val }) {
  if (val == null) return null;
  const up = val >= 0;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 2,
      fontSize: 11, fontWeight: 700,
      color: up ? "#059669" : "#DC2626",
      background: up ? "#ECFDF5" : "#FEF2F2",
      padding: "2px 7px", borderRadius: 99,
    }}>
      {up ? "↑" : "↓"} {Math.abs(val)}%
    </span>
  );
}

function BriefingIA({ dados, setor, loading: loadingDados }) {
  const [texto,   setTexto]   = useState("");
  const [loading, setLoading] = useState(false);
  const [gerado,  setGerado]  = useState(false);

  useEffect(() => {
    const salvo = sessionStorage.getItem(`briefing_${setor}`);
    if (salvo) { setTexto(salvo); setGerado(true); }
    else { setTexto(""); setGerado(false); }
  }, [setor]);

  const gerar = async () => {
    if (!dados || loading) return;
    setLoading(true); setTexto(""); setGerado(false);

    const k    = dados.kpis || {};
    const v    = dados.variacoes || {};
    const abs  = dados.absenteismo || {};
    const proj = dados.projecao || {};
    const top1 = dados.top_profissionais?.[0];
    const top_cnv = dados.top_convenios?.[0];
    const setorLabel = SETORES.find(s => s.id === setor)?.label || "Geral";
    const taxa_abs = abs.marcacoes > 0 ? ((abs.faltantes / abs.marcacoes) * 100).toFixed(1) : null;

    const prompt = `Você é um analista de gestão clínica. Analise os dados abaixo e gere um briefing executivo em português brasileiro, direto e profissional, com no máximo 4 frases curtas. Inclua destaques positivos, alertas se necessário, e uma perspectiva para o restante do período. Não use markdown, apenas texto corrido.

DADOS DO PERÍODO — ${setorLabel}:
- Produção: ${brl(k.producao)} (variação vs período anterior: ${v.producao != null ? v.producao + "%" : "n/d"})
- Atendimentos: ${num(k.total_os)} OSs, ${num(k.pacientes)} pacientes únicos
- Ticket médio: ${brl(k.ticket_medio)} (variação: ${v.ticket_medio != null ? v.ticket_medio + "%" : "n/d"})
- Projeção do mês: ${brl(proj.valor)} (acumulado ${brl(proj.acumulado)}, faltam ${proj.dias_restantes} dias úteis)
- Absenteísmo: ${taxa_abs != null ? taxa_abs + "% (" + num(abs.faltantes) + " faltantes de " + num(abs.marcacoes) + " marcações)" : "n/d"}
- Melhor profissional: ${top1 ? top1.profissional + " com " + brl(top1.producao) : "n/d"}
- Principal convênio: ${top_cnv ? top_cnv.convenio + " com " + brl(top_cnv.producao) : "n/d"}`;

    try {
      const res = await fetch(`${API}/api/home/briefing`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      const t = data.texto || "Não foi possível gerar o briefing.";
      setTexto(t);
      sessionStorage.setItem(`briefing_${setor}`, t);
      setGerado(true);
    } catch {
      setTexto("Erro ao conectar com a IA.");
      setGerado(true);
    }
    setLoading(false);
  };

  const corAtual = SETORES.find(s => s.id === setor)?.cor || "#8B1A1A";

  return (
    <div style={{
      background: `linear-gradient(135deg, ${corAtual}15 0%, #fff 60%)`,
      border: `1px solid ${corAtual}30`,
      borderRadius: 16, padding: "20px 24px",
      boxShadow: "0 1px 4px rgba(0,0,0,0.06)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14 }}>
        <div style={{
          width: 32, height: 32, borderRadius: 10,
          background: corAtual, display: "flex", alignItems: "center",
          justifyContent: "center", fontSize: 16,
        }}>✨</div>
        <div>
          <div style={{ fontSize: 13, fontWeight: 800, color: "#111827" }}>Briefing Inteligente</div>
          <div style={{ fontSize: 11, color: "#9CA3AF" }}>Análise gerada por IA · Clínica Censo</div>
        </div>
        <button onClick={gerar} disabled={loading} style={{
          marginLeft: "auto", padding: "5px 14px", borderRadius: 8,
          border: `1px solid ${corAtual}40`, background: corAtual,
          color: "#fff", fontSize: 11, fontWeight: 700, cursor: "pointer",
        }}>
          {loading ? "⟳ Gerando..." : "✨ Gerar Briefing"}
        </button>
      </div>

      {loading ? (
        <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#9CA3AF", fontSize: 13 }}>
          <div style={{
            width: 16, height: 16, border: `2px solid ${corAtual}40`,
            borderTopColor: corAtual, borderRadius: "50%",
            animation: "spin 1s linear infinite",
          }}/>
          Analisando dados da clínica...
        </div>
      ) : texto ? (
        <p style={{ fontSize: 14, lineHeight: 1.7, color: "#374151", margin: 0, fontWeight: 400 }}>
          {texto}
        </p>
      ) : (
        <p style={{ fontSize: 13, color: "#9CA3AF", margin: 0 }}>
          Clique em "✨ Gerar Briefing" para analisar os dados com IA.
        </p>
      )}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function Alertas({ dados }) {
  const alertas = [];
  const v   = dados?.variacoes || {};
  const abs = dados?.absenteismo || {};

  const taxa_abs = abs.marcacoes > 0 ? (abs.faltantes / abs.marcacoes * 100) : 0;
  if (taxa_abs > 40) alertas.push({ tipo: "danger", msg: `Absenteísmo crítico: ${taxa_abs.toFixed(1)}% dos agendamentos não compareceram`, icon: "⚠️" });
  else if (taxa_abs > 25) alertas.push({ tipo: "warn", msg: `Absenteísmo elevado: ${taxa_abs.toFixed(1)}% — acima do ideal de 25%`, icon: "⚠️" });

  if (v.producao != null && v.producao < -10) alertas.push({ tipo: "danger", msg: `Produção caiu ${Math.abs(v.producao)}% vs período anterior`, icon: "📉" });
  else if (v.producao != null && v.producao > 10) alertas.push({ tipo: "success", msg: `Produção cresceu ${v.producao}% vs período anterior`, icon: "📈" });

  if (alertas.length === 0) alertas.push({ tipo: "success", msg: "Nenhum alerta crítico no período. Indicadores dentro do esperado.", icon: "✅" });

  const cores = {
    danger:  { bg: "#FEF2F2", border: "#FECACA", txt: "#DC2626" },
    warn:    { bg: "#FFFBEB", border: "#FDE68A", txt: "#D97706" },
    success: { bg: "#ECFDF5", border: "#A7F3D0", txt: "#059669" },
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {alertas.map((a, i) => {
        const c = cores[a.tipo];
        return (
          <div key={i} style={{
            display: "flex", alignItems: "center", gap: 10,
            background: c.bg, border: `1px solid ${c.border}`,
            borderRadius: 10, padding: "10px 14px",
          }}>
            <span style={{ fontSize: 16 }}>{a.icon}</span>
            <span style={{ fontSize: 13, fontWeight: 600, color: c.txt }}>{a.msg}</span>
          </div>
        );
      })}
    </div>
  );
}

const useIsMobile = () => { const [m, setM] = useState(window.innerWidth < 768); useEffect(() => { const fn = () => setM(window.innerWidth < 768); window.addEventListener("resize", fn); return () => window.removeEventListener("resize", fn); }, []); return m; };

export default function Home({ periodoGlobal }) {
  const isMobile = useIsMobile();
  const [setor,   setSetor]   = useState("todos");
  const [dados,   setDados]   = useState(null);
  const [loading, setLoading] = useState(true);

  const periodo = periodoGlobal || "30d";

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/home/resumo?periodo=${periodo}&setor=${setor}`);
      const d = await r.json();
      setDados(d);
    } catch {}
    setLoading(false);
  }, [periodo, setor]);

  useEffect(() => { carregar(); }, [carregar]);

  const k    = dados?.kpis || {};
  const v    = dados?.variacoes || {};
  const abs  = dados?.absenteismo || {};
  const proj = dados?.projecao || {};
  const taxa_abs = abs.marcacoes > 0 ? ((abs.faltantes / abs.marcacoes) * 100) : 0;
  const corAtual = SETORES.find(s => s.id === setor)?.cor || "#8B1A1A";
  const pct_projecao = proj.valor > 0 ? Math.min(100, (proj.acumulado / proj.valor) * 100) : 0;

  const KPIS = [
    { label: "Produção",     valor: brl(k.producao),     var: v.producao,     sub: `${num(k.total_os)} atendimentos`,  icon: "💰" },
    { label: "Pacientes",    valor: num(k.pacientes),    var: v.pacientes,    sub: "pacientes únicos",                 icon: "👥" },
    { label: "Ticket Médio", valor: brl(k.ticket_medio), var: v.ticket_medio, sub: "por OS",                          icon: "🎯" },
    { label: "Absenteísmo",  valor: taxa_abs.toFixed(1) + "%", var: null,     sub: `${num(abs.faltantes)} faltantes`,  icon: "📅",
      corValor: taxa_abs > 40 ? "#DC2626" : taxa_abs > 25 ? "#D97706" : "#059669" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Header + filtro setor */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ fontSize: 21, fontWeight: 800, color: "#111827", margin: 0 }}>Dashboard Clínica Censo</h2>
          <p style={{ fontSize: 12, color: "#9CA3AF", margin: "2px 0 0" }}>
            {periodo === "30d" ? "Mês atual" : "Período selecionado"} · Atualizado agora
          </p>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {SETORES.map(s => (
            <button key={s.id} onClick={() => setSetor(s.id)} style={{
              padding: "7px 14px", borderRadius: 99, fontSize: 12, fontWeight: 700,
              border: `1.5px solid ${setor === s.id ? s.cor : "#E5E7EB"}`,
              background: setor === s.id ? s.cor : "#fff",
              color: setor === s.id ? "#fff" : "#6B7280",
              cursor: "pointer",
            }}>
              {s.emoji} {s.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 60, color: "#9CA3AF" }}>
          Carregando dados...
        </div>
      ) : (
        <>
          <BriefingIA dados={dados} setor={setor} loading={loading} />
          <Alertas dados={dados} setor={setor} />

          {/* Mini cards por setor */}
          {setor === "todos" && dados?.setores_kpi?.length > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 }}>
              {dados.setores_kpi.filter(s => s.setor !== "Outros").map(s => (
                <div key={s.setor} style={{
                  background: "#fff", borderRadius: 12, padding: "14px 16px",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.07)",
                  borderLeft: `4px solid ${COR_SETOR[s.setor] || "#9CA3AF"}`,
                  cursor: "pointer",
                }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: COR_SETOR[s.setor], textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 4 }}>{s.setor}</div>
                  <div style={{ fontSize: 20, fontWeight: 800, color: "#111827" }}>{num(s.os)}</div>
                  <div style={{ fontSize: 10, color: "#9CA3AF" }}>atendimentos</div>
                  <div style={{ fontSize: 12, fontWeight: 700, color: "#374151", marginTop: 3 }}>{brl(s.producao)}</div>
                </div>
              ))}
            </div>
          )}

          {/* KPIs principais */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
            {KPIS.map((item, i) => (
              <div key={i} style={{
                background: "#fff", borderRadius: 14, padding: "18px 20px",
                boxShadow: "0 1px 4px rgba(0,0,0,0.07)",
                borderTop: `3px solid ${corAtual}`,
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.07em" }}>{item.label}</span>
                  <span style={{ fontSize: 20 }}>{item.icon}</span>
                </div>
                <div style={{ fontSize: 24, fontWeight: 800, color: item.corValor || "#111827", letterSpacing: "-0.5px", marginBottom: 4 }}>
                  {item.valor}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 11, color: "#9CA3AF" }}>{item.sub}</span>
                  <Variacao val={item.var} />
                </div>
              </div>
            ))}
          </div>

          {/* Projeção do mês */}
          <div style={{
            background: "#fff", borderRadius: 14, padding: "18px 22px",
            boxShadow: "0 1px 4px rgba(0,0,0,0.07)",
            display: "grid", gridTemplateColumns: "1fr auto", gap: 16, alignItems: "center",
          }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 700, color: "#9CA3AF", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: 6 }}>
                📊 Projeção do Mês
              </div>
              <div style={{ fontSize: 22, fontWeight: 800, color: "#111827", marginBottom: 4 }}>{brl(proj.valor)}</div>
              <div style={{ fontSize: 12, color: "#6B7280", marginBottom: 10 }}>
                Acumulado {brl(proj.acumulado)} · Média {brl(proj.media_diaria)}/dia · {proj.dias_restantes} dias úteis restantes
              </div>
              <div style={{ height: 8, background: "#F3F4F6", borderRadius: 99, overflow: "hidden" }}>
                <div style={{
                  height: "100%", borderRadius: 99,
                  background: `linear-gradient(90deg, ${corAtual}, ${corAtual}CC)`,
                  width: `${pct_projecao}%`,
                }} />
              </div>
              <div style={{ fontSize: 11, color: "#9CA3AF", marginTop: 4 }}>{pct_projecao.toFixed(0)}% da projeção atingida</div>
            </div>
            <div style={{
              width: 72, height: 72, borderRadius: "50%",
              background: `conic-gradient(${corAtual} ${pct_projecao * 3.6}deg, #F3F4F6 0deg)`,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <div style={{
                width: 52, height: 52, borderRadius: "50%", background: "#fff",
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13, fontWeight: 800, color: corAtual,
              }}>
                {pct_projecao.toFixed(0)}%
              </div>
            </div>
          </div>

          {/* Gráfico produção por dia */}
          <div style={{ background: "#fff", borderRadius: 14, padding: "20px 22px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#374151", marginBottom: 16 }}>📈 Produção por Dia</div>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={dados?.por_dia || []} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                <defs>
                  <linearGradient id="grad1" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor={corAtual} stopOpacity={0.25} />
                    <stop offset="95%" stopColor={corAtual} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" />
                <XAxis dataKey="data" tick={{ fontSize: 10, fill: "#9CA3AF" }} tickFormatter={v => v?.slice(8) + "/" + v?.slice(5, 7)} />
                <YAxis tick={{ fontSize: 10, fill: "#9CA3AF" }} tickFormatter={v => `R$${(v/1000).toFixed(0)}k`} width={52} />
                <Tooltip
                  formatter={v => [brl(v), "Produção"]}
                  labelFormatter={l => `${l?.slice(8)}/${l?.slice(5,7)}/${l?.slice(0,4)}`}
                  contentStyle={{ borderRadius: 10, border: "1px solid #E5E7EB", fontSize: 12 }}
                />
                {proj.media_diaria > 0 && (
                  <ReferenceLine y={proj.media_diaria} stroke={corAtual} strokeDasharray="4 4" strokeOpacity={0.5}
                    label={{ value: "Média", position: "right", fontSize: 10, fill: corAtual }} />
                )}
                <Area type="monotone" dataKey="producao" stroke={corAtual} strokeWidth={2.5}
                  fill="url(#grad1)" dot={false} activeDot={{ r: 5, fill: corAtual }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {/* Rankings */}
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 14 }}>
            <div style={{ background: "#fff", borderRadius: 14, padding: "18px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#374151", marginBottom: 14 }}>🏆 Top Convênios</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {(dados?.top_convenios || []).slice(0, 6).map((c, i) => {
                  const max = dados.top_convenios[0]?.producao || 1;
                  return (
                    <div key={i}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>
                          <span style={{ color: "#D1D5DB", marginRight: 6, fontSize: 10 }}>{i + 1}</span>
                          {c.convenio}
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: corAtual }}>{brl(c.producao)}</span>
                      </div>
                      <div style={{ height: 3, background: "#F3F4F6", borderRadius: 2, overflow: "hidden" }}>
                        <div style={{ height: "100%", background: corAtual, borderRadius: 2, width: `${Math.max(3, (c.producao / max) * 100)}%` }} />
                      </div>
                      <div style={{ fontSize: 10, color: "#9CA3AF", marginTop: 2 }}>{num(c.os)} OSs · {num(c.pacientes)} pac.</div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div style={{ background: "#fff", borderRadius: 14, padding: "18px 20px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#374151", marginBottom: 14 }}>⭐ Top Profissionais</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {(dados?.top_profissionais || []).slice(0, 6).map((p, i) => {
                  const max = dados.top_profissionais[0]?.producao || 1;
                  return (
                    <div key={i}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "#374151" }}>
                          <span style={{ color: "#D1D5DB", marginRight: 6, fontSize: 10 }}>{i + 1}</span>
                          {p.profissional}
                        </span>
                        <span style={{ fontSize: 12, fontWeight: 700, color: corAtual }}>{brl(p.producao)}</span>
                      </div>
                      <div style={{ height: 3, background: "#F3F4F6", borderRadius: 2, overflow: "hidden" }}>
                        <div style={{ height: "100%", background: corAtual, borderRadius: 2, width: `${Math.max(3, (p.producao / max) * 100)}%` }} />
                      </div>
                      <div style={{ fontSize: 10, color: "#9CA3AF", marginTop: 2 }}>{num(p.os)} OSs · {num(p.pacientes)} pac.</div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
