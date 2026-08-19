import { useState, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

const API = `${window.location.protocol}//${window.location.host}`;

// ══════════════════════════════════════════════════════════════════════════════
// PAINEL TV — TEMPO REAL
// ══════════════════════════════════════════════════════════════════════════════

function usePainelFetch(url, intervalMs = 30000) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(true);
  const [tick,    setTick]    = useState(0);

  useEffect(() => {
    let alive = true;
    const load = () => {
      fetch(`${API}${url}`)
        .then(r => r.json())
        .then(d => { if (alive) { setData(d); setLoading(false); } })
        .catch(() => { if (alive) setLoading(false); });
    };
    load();
    const id = setInterval(() => { if (alive) { load(); setTick(t => t+1); } }, intervalMs);
    return () => { alive = false; clearInterval(id); };
  }, [url]);

  return { data, loading, tick };
}

function ColunaRecepcaoTV({ cod, nome, cor }) {
  const { data: resumo, loading } = usePainelFetch(`/api/painel/resumo-hoje?setor=${cod}`);
  const [meta, setMeta] = useState(undefined); // undefined=carregando, null=sem meta
  const [editando, setEditando] = useState(false);
  const [tmp, setTmp] = useState("");

  useEffect(() => {
    fetch(`${API}/api/metas`)
      .then(r => r.json())
      .then(d => setMeta(d?.[`painel_recepcao_${cod}`]?.meta_diaria ?? null))
      .catch(() => setMeta(null));
  }, [cod]);

  const salvar = async () => {
    const valor = Number(tmp);
    if (!valor || valor <= 0) return;
    try {
      await fetch(`${API}/api/metas/painel_recepcao_${cod}`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ meta_diaria: valor }),
      });
    } catch {}
    setMeta(valor);
    setEditando(false);
  };

  const remover = async () => {
    try {
      await fetch(`${API}/api/metas/painel_recepcao_${cod}`, { method: "DELETE" });
    } catch {}
    setMeta(null);
    setEditando(false);
  };

  const brl = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v) : "—";
  const num = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";

  const fat = resumo?.faturamento || 0;
  const pct = meta ? Math.min(100, (fat/meta)*100) : 0;
  const corBarra = pct >= 100 ? "#10B981" : pct >= 60 ? cor : pct >= 30 ? "#F59E0B" : "#EF4444";

  return (
    <div style={{ background:"#1E293B", borderRadius:14, overflow:"hidden", border:`1px solid ${cor}40` }}>
      {/* Barra de meta no topo */}
      <div style={{ background:`linear-gradient(135deg, ${cor}30, ${cor}10)`, padding:"14px 16px", borderBottom:`2px solid ${cor}` }}>
        <div style={{ fontSize:13, fontWeight:800, color:"#F1F5F9", marginBottom:8 }}>{nome}</div>
        {meta === undefined ? (
          <div style={{ height:8 }}/>
        ) : !meta ? (
          editando ? (
            <div style={{ display:"flex", gap:6 }}>
              <input type="number" value={tmp} onChange={e=>setTmp(e.target.value)} placeholder="Meta diária R$" autoFocus
                style={{ flex:1, padding:"5px 8px", borderRadius:6, border:"none", fontSize:12, minWidth:0 }}/>
              <button onClick={salvar} style={{ background:cor, color:"#fff", border:"none", borderRadius:6, padding:"5px 10px", fontWeight:700, fontSize:11, cursor:"pointer" }}>OK</button>
            </div>
          ) : (
            <button onClick={()=>{setTmp(""); setEditando(true);}} style={{
              background:"transparent", border:`1px dashed ${cor}`, borderRadius:6,
              color:cor, fontSize:11, fontWeight:700, padding:"5px 10px", cursor:"pointer",
            }}>+ Definir meta diária</button>
          )
        ) : editando ? (
          <div style={{ display:"flex", gap:6 }}>
            <input type="number" value={tmp} onChange={e=>setTmp(e.target.value)} autoFocus
              style={{ flex:1, padding:"5px 8px", borderRadius:6, border:"none", fontSize:12, minWidth:0 }}/>
            <button onClick={salvar} style={{ background:cor, color:"#fff", border:"none", borderRadius:6, padding:"5px 10px", fontWeight:700, fontSize:11, cursor:"pointer" }}>OK</button>
            <button onClick={remover} title="Remover meta" style={{ background:"transparent", color:"#EF4444", border:"1px solid #EF4444", borderRadius:6, padding:"5px 8px", fontWeight:700, fontSize:11, cursor:"pointer" }}>✕</button>
          </div>
        ) : (
          <>
            <div style={{ display:"flex", justifyContent:"space-between", marginBottom:5, fontSize:11, color:"#CBD5E1", fontWeight:700 }}>
              <span>{pct.toFixed(0)}% da meta</span>
              <span style={{ display:"flex", gap:8 }}>
                <span onClick={()=>{setTmp(meta); setEditando(true);}} style={{ cursor:"pointer", color:"#94A3B8" }} title="Editar meta">⚙</span>
                <span onClick={remover} style={{ cursor:"pointer", color:"#EF4444" }} title="Remover meta">✕</span>
              </span>
            </div>
            <div style={{ height:8, background:"#0F172A", borderRadius:4, overflow:"hidden" }}>
              <div style={{ height:"100%", width:`${pct}%`, background:corBarra, borderRadius:4, transition:"width 1s" }}/>
            </div>
            <div style={{ fontSize:10, color:"#94A3B8", marginTop:4 }}>{brl(fat)} de {brl(meta)}</div>
          </>
        )}
      </div>

      {/* KPIs */}
      <div style={{ padding:"14px 16px", display:"flex", flexDirection:"column", gap:10 }}>
        <div>
          <div style={{ fontSize:9, color:cor, fontWeight:700, textTransform:"uppercase" }}>Produção</div>
          <div style={{ fontSize:20, fontWeight:900, color:"#F1F5F9" }}>{loading ? "…" : brl(resumo?.faturamento)}</div>
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10 }}>
          <div>
            <div style={{ fontSize:9, color:"#64748B", fontWeight:700, textTransform:"uppercase" }}>OS</div>
            <div style={{ fontSize:18, fontWeight:900, color:"#F1F5F9" }}>{loading ? "…" : num(resumo?.total_os)}</div>
          </div>
          <div>
            <div style={{ fontSize:9, color:"#64748B", fontWeight:700, textTransform:"uppercase" }}>Pacientes</div>
            <div style={{ fontSize:18, fontWeight:900, color:"#F1F5F9" }}>{loading ? "…" : num(resumo?.pacientes_unicos)}</div>
          </div>
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10 }}>
          <div>
            <div style={{ fontSize:9, color:"#64748B", fontWeight:700, textTransform:"uppercase" }}>Tempo Médio</div>
            <div style={{ fontSize:14, fontWeight:800, color:"#0891B2" }}>
              {loading ? "…" : resumo?.tempo_medio_min > 0 ? `${Math.round(resumo.tempo_medio_min)}min` : "—"}
            </div>
          </div>
          <div>
            <div style={{ fontSize:9, color:"#64748B", fontWeight:700, textTransform:"uppercase" }}>Espera Média</div>
            <div style={{ fontSize:14, fontWeight:800,
              color: !resumo?.espera_media_min ? "#475569" : resumo.espera_media_min<=15?"#10B981":resumo.espera_media_min<=30?"#F59E0B":"#EF4444" }}>
              {loading ? "…" : resumo?.espera_media_min > 0 ? `${Math.round(resumo.espera_media_min)}min` : "—"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function PainelTV() {
  // Meta diária real (mesma configurada no módulo Produção Mensal) — evita
  // divergir do valor hardcoded que ficava fixo em 45000 independente do que
  // era salvo em /api/metas. Aos sábados usa a meta_sabado (menor).
  const [metaDiaria, setMetaDiaria] = useState(45000);
  useEffect(() => {
    fetch(`${API}/api/metas`)
      .then(r => r.json())
      .then(d => {
        const m = d?.producao;
        if (!m) return;
        const ehSabado = new Date().getDay() === 6;
        const valor = ehSabado ? (m.meta_sabado ?? m.meta_diaria) : m.meta_diaria;
        if (valor != null) setMetaDiaria(valor);
      })
      .catch(() => {});
  }, []);
  const [setor,    setSetor]    = useState("");
  const [isFS,     setIsFS]     = useState(false);
  const ref = { current: null };

  const { data: resumo,  loading: lR } = usePainelFetch(
    `/api/painel/resumo-hoje?meta_diaria=${metaDiaria}${setor ? `&setor=${setor}` : ""}`
  );
  const { data: medicos,    loading: lM  } = usePainelFetch(
    `/api/painel/medicos-ativos${setor ? `?setor=${setor}` : ""}`
  );
  const { data: medicosReq, loading: lMR } = usePainelFetch(
    `/api/painel/medicos-solicitante${setor ? `?setor=${setor}` : ""}`
  );
  const { data: linha,   loading: lL } = usePainelFetch("/api/painel/linha-tempo");
  const { data: evolucao             } = usePainelFetch("/api/painel/evolucao-hora");
  const { data: statusSenhas, loading: lSS } = usePainelFetch(
    `/api/painel-fila/status-senhas${setor ? `?setor=${setor}` : ""}`
  );
  const senhasAguardando = (statusSenhas || []).reduce((s, r) => s + (r.na_fila || 0), 0);
  const { data: setoresList           } = usePainelFetch("/api/painel/setores");
  const [agora, setAgora] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setAgora(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  // Track fullscreen state
  useEffect(() => {
    const handler = () => setIsFS(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  // Som e animação quando meta é atingida — um riff techno diferente a cada
  // 10% da meta, ficando mais rápido/denso conforme se aproxima (e além) de 100%.
  const [metaAtingida,    setMetaAtingida]    = useState(false);
  const [celebrando,      setCelebrando]      = useState(false);
  const [maiorMarcoSom,   setMaiorMarcoSom]   = useState(0);
  const metaAtingidaRef = { current: false };

  const TECHNO_ESCALA = [220.00, 246.94, 261.63, 293.66, 329.63, 349.23, 392.00, 440.00]; // A3 até A4 (menor)

  const tocarKick = (ctx, t) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = "sine";
    osc.frequency.setValueAtTime(150, t);
    osc.frequency.exponentialRampToValueAtTime(40, t + 0.08);
    gain.gain.setValueAtTime(0.5, t);
    gain.gain.exponentialRampToValueAtTime(0.001, t + 0.15);
    osc.start(t);
    osc.stop(t + 0.16);
  };

  const tocarNota = (ctx, t, freq, dur, wave = "sawtooth", vol = 0.22) => {
    const osc  = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.type = wave;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(vol, t + 0.01);
    gain.gain.exponentialRampToValueAtTime(0.001, t + dur);
    osc.start(t);
    osc.stop(t + dur + 0.02);
  };

  // marco: 10, 20, ..., 90 tocam o riff sintetizado (escalando); 100%+ toca
  // o áudio real da comemoração ("Eu vou tomar um tacacá" — Joelma).
  const tocarSomMarco = (marco) => {
    if (marco >= 100) {
      try {
        const audio = new Audio("/som_meta_batida.mp3");
        audio.volume = 1.0;
        audio.play().catch(e => console.warn("Não foi possível tocar o áudio:", e));
      } catch(e) { console.warn("Audio não suportado:", e); }
      return;
    }
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const nivel = marco / 10;                               // 1..9
      const bpm = 90 + nivel * 8;                             // acelera a cada marco
      const stepDur = 60 / bpm / 2;                            // colcheias
      const numNotas = Math.min(4 + nivel, 16);
      const comKick = marco >= 60;

      for (let i = 0; i < numNotas; i++) {
        const t = ctx.currentTime + i * stepDur;
        const freq = TECHNO_ESCALA[i % TECHNO_ESCALA.length];
        tocarNota(ctx, t, freq, stepDur * 0.9, "sawtooth", 0.22);
        if (comKick && i % 4 === 0) tocarKick(ctx, t);
      }
    } catch(e) { console.warn("Audio não suportado:", e); }
  };

  // Detecta cada novo marco de 10% da meta atingido
  useEffect(() => {
    const pct = resumo?.pct_meta || 0;
    const marcoAtual = Math.floor(pct / 10) * 10;

    if (marcoAtual > maiorMarcoSom && marcoAtual >= 10) {
      setMaiorMarcoSom(marcoAtual);
      tocarSomMarco(marcoAtual);
      if (marcoAtual >= 100 && !metaAtingida) {
        setMetaAtingida(true);
        setCelebrando(true);
        setTimeout(() => setCelebrando(false), 5000);
      }
    }
    // Reset se cair bem abaixo do último marco (ex: troca de dia)
    if (marcoAtual < maiorMarcoSom - 10) {
      setMaiorMarcoSom(marcoAtual);
      if (metaAtingida) setMetaAtingida(false);
    }
  }, [resumo?.pct_meta]);

  const toggleFS = () => {
    const el = document.getElementById("painel-tv-root");
    if (!document.fullscreenElement) el?.requestFullscreen();
    else document.exitFullscreen();
  };

  const brl  = v => v != null ? new Intl.NumberFormat("pt-BR",{style:"currency",currency:"BRL",maximumFractionDigits:0}).format(v) : "—";
  const num  = v => v != null ? Number(v).toLocaleString("pt-BR") : "—";
  const hora = agora.toLocaleTimeString("pt-BR", {hour:"2-digit",minute:"2-digit",second:"2-digit"});
  const dataStr = agora.toLocaleDateString("pt-BR",  {weekday:"long",day:"2-digit",month:"long",year:"numeric"});

  const pctMeta = resumo?.pct_meta || 0;
  const corMeta = pctMeta >= 100 ? "#10B981" : pctMeta >= 75 ? "#3B7EF5" : pctMeta >= 50 ? "#F59E0B" : "#EF4444";

  const ATEND_LABEL = { ASS:"Assistencial", PER:"Periódico", ADM:"Admissional",
    DEM:"Demissional", RTB:"Ret. Trabalho", MDF:"Mud. Função", MOC:"Med. Ocup." };
  const STATUS_COR  = { CONCLUIDO:"#10B981", EM_ATEND:"#3B7EF5", DEMORADO:"#EF4444" };
  const STATUS_NOME = { CONCLUIDO:"Concluído", EM_ATEND:"Em atend.", DEMORADO:"Demorado" };

  return (
    <div id="painel-tv-root" style={{
      minHeight:"100vh", background:"#0F172A", color:"#F1F5F9",
      fontFamily:"'DM Sans','Helvetica Neue',sans-serif", padding:"20px 24px",
      overflowY: isFS ? "auto" : "visible",
      height: isFS ? "100vh" : "auto",
      boxSizing:"border-box",
    }}>

      {/* ── HEADER ── */}
      <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:20 }}>
        <div style={{ display:"flex", alignItems:"center", gap:14 }}>
          <div style={{ width:44, height:44, borderRadius:12, background:"linear-gradient(135deg,#3B7EF5,#1D4ED8)",
            display:"flex", alignItems:"center", justifyContent:"center", fontSize:18, fontWeight:900, color:"#fff" }}>Px</div>
          <div>
            <div style={{ fontSize:22, fontWeight:800, color:"#F1F5F9", lineHeight:1 }}>Dashboard Clínica</div>
            <div style={{ fontSize:13, color:"#64748B", marginTop:2 }}>Painel em Tempo Real · Smart Pixeon</div>
          </div>
        </div>
        <div style={{ display:"flex", alignItems:"center", gap:16 }}>
          <div style={{ textAlign:"right" }}>
            <div style={{ fontSize:38, fontWeight:900, color:"#F1F5F9", lineHeight:1, letterSpacing:"-1px", fontVariantNumeric:"tabular-nums" }}>{hora}</div>
            <div style={{ fontSize:13, color:"#64748B", marginTop:2, textTransform:"capitalize" }}>{dataStr}</div>
          </div>
          <button onClick={()=>{ tocarSomMeta(); setCelebrando(true); setTimeout(()=>setCelebrando(false),5000); }}
            style={{
              width:44, height:44, borderRadius:10,
              border:"1px solid #334155", background:"#1E293B",
              cursor:"pointer", color:"#F59E0B",
              display:"flex", alignItems:"center", justifyContent:"center",
              fontSize:20, flexShrink:0, transition:"all 0.2s",
            }} title="Testar som da meta">
            🔔
          </button>
          <button onClick={toggleFS} style={{
            width:44, height:44, borderRadius:10,
            border:`1px solid ${isFS ? "#3B7EF5" : "#334155"}`,
            background: isFS ? "#1D4ED8" : "#1E293B",
            cursor:"pointer", color: isFS ? "#fff" : "#94A3B8",
            display:"flex", alignItems:"center", justifyContent:"center",
            fontSize:18, flexShrink:0, transition:"all 0.2s",
          }} title={isFS ? "Sair da tela cheia" : "Tela cheia"}>
            {isFS ? "✕" : "⛶"}
          </button>
        </div>
      </div>

      {/* ── FILTRO DE SETOR ── */}
      <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:16,
        background:"#1E293B", borderRadius:12, padding:"12px 16px" }}>
        <span style={{ fontSize:12, color:"#64748B", fontWeight:700, flexShrink:0,
          textTransform:"uppercase", letterSpacing:"0.07em" }}>Setor:</span>
        <div style={{ display:"flex", gap:6, flexWrap:"wrap", flex:1 }}>
          <button onClick={()=>setSetor("")} style={{
            padding:"5px 14px", borderRadius:8, fontSize:12, fontWeight:700, cursor:"pointer",
            border:`1.5px solid ${setor===""?"#3B7EF5":"#334155"}`,
            background:setor===""?"#1D4ED8":"transparent",
            color:setor===""?"#fff":"#64748B", transition:"all 0.12s",
          }}>Todos</button>
          {(setoresList||[]).map((s,i) => (
            <button key={s.setor_cod} onClick={()=>setSetor(setor===s.setor_cod?"":s.setor_cod)} style={{
              padding:"5px 14px", borderRadius:8, fontSize:12, fontWeight:700, cursor:"pointer",
              border:`1.5px solid ${setor===s.setor_cod?"#3B7EF5":"#334155"}`,
              background:setor===s.setor_cod?"#1D4ED8":"transparent",
              color:setor===s.setor_cod?"#fff":"#64748B", transition:"all 0.12s",
              whiteSpace:"nowrap",
            }}>
              <span style={{ fontWeight:700, fontSize:12 }}>
                {s.setor_nome ? s.setor_nome.trim() : s.setor_cod}
              </span>
              <span style={{ fontSize:10, opacity:.6, marginLeft:6 }}>
                {Number(s.atendimentos||0)} pac.
              </span>
              {s.espera_media_min > 0 && (
                <span style={{ fontSize:10, marginLeft:4, fontWeight:700,
                  color: s.espera_media_min<=15?"#10B981":s.espera_media_min<=30?"#F59E0B":"#EF4444" }}>
                  · ⏳{Math.round(s.espera_media_min)}m
                </span>
              )}
            </button>
          ))}
        </div>
        {setor && (
          <button onClick={()=>setSetor("")} style={{
            padding:"4px 10px", borderRadius:6, border:"1px solid #EF4444",
            background:"transparent", color:"#EF4444", fontSize:11, fontWeight:700,
            cursor:"pointer", flexShrink:0,
          }}>✕ Limpar</button>
        )}
      </div>

      {/* ── POR RECEPÇÃO — Consultórios, Diagnóstico, Ocupacional, Censo Imagem ── */}
      <div style={{ marginBottom:16 }}>
        <div style={{ fontSize:13, color:"#94A3B8", fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:10 }}>
          📍 Por Recepção — Hoje
        </div>
        <div style={{ display:"grid", gridTemplateColumns:"repeat(4,1fr)", gap:14 }}>
          <ColunaRecepcaoTV cod="RCN" nome="Consultórios" cor="#3B7EF5"/>
          <ColunaRecepcaoTV cod="RDI" nome="Diagnóstico"  cor="#8B5CF6"/>
          <ColunaRecepcaoTV cod="OCUP_TIPO" nome="Ocupacional" cor="#F59E0B"/>
          <ColunaRecepcaoTV cod="RCI" nome="Censo Imagem" cor="#10B981"/>
        </div>
      </div>

      {/* ── META DO DIA ── */}
      <div style={{ background: celebrando ? "#064E3B" : "#1E293B",
        borderRadius:14, padding:"18px 22px", marginBottom:16,
        transition:"background 1s",
        boxShadow: celebrando ? "0 0 40px rgba(16,185,129,0.6)" : "none",
        animation: celebrando ? "celebrar 0.5s ease-in-out infinite alternate" : "none",
      }}>
      {celebrando && (
        <div style={{ textAlign:"center", fontSize:28, letterSpacing:4,
          marginBottom:10, animation:"fadeInDown 0.5s ease" }}>
          🎉 🏆 META ATINGIDA! 🏆 🎉
        </div>
      )}
        <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:12 }}>
          <div>
            <div style={{ fontSize:14, color:"#94A3B8", fontWeight:600, marginBottom:2 }}>META DO DIA</div>
            <div style={{ display:"flex", alignItems:"baseline", gap:10 }}>
              <span style={{ fontSize:32, fontWeight:900, color:corMeta }}>{brl(resumo?.faturamento)}</span>
              <span style={{ fontSize:16, color:"#64748B" }}>de {brl(metaDiaria)}</span>
            </div>
          </div>
          <div style={{ textAlign:"right" }}>
            <div style={{ fontSize:44, fontWeight:900, color:corMeta, lineHeight:1 }}>{pctMeta.toFixed(1)}%</div>
            {pctMeta < 100 && <div style={{ fontSize:13, color:"#94A3B8", marginTop:4 }}>faltam {brl(resumo?.falta_meta)}</div>}
            {pctMeta >= 100 && <div style={{ fontSize:14, color:"#10B981", fontWeight:700, marginTop:4 }}>✓ META ATINGIDA!</div>}
          </div>
        </div>
        <div style={{ height:16, marginTop:20, background:"#0F172A", borderRadius:8, overflow:"hidden" }}>
          <div style={{ height:"100%", borderRadius:8, transition:"width 1s ease",
            width:`${Math.min(100,pctMeta)}%`,
            background: pctMeta>=100 ? "#10B981" : pctMeta>=75 ? "#3B7EF5" : pctMeta>=50 ? "#F59E0B" : "#EF4444",
            boxShadow:`0 0 12px ${corMeta}80`,
          }}/>
        </div>
        {/* Marcadores */}
        <div style={{ display:"flex", justifyContent:"space-between", marginTop:6 }}>
          {[0,25,50,75,100].map(p => (
            <span key={p} style={{ fontSize:10, color:"#475569", fontWeight:600 }}>{p}%</span>
          ))}
        </div>
      </div>

      {/* ── KPIs LINHA 1 ── */}
      <div style={{ display:"grid", gridTemplateColumns:"repeat(6,1fr)", gap:12, marginBottom:12 }}>
        {[
          { label:"Atendimentos (Guias)",  val:num(resumo?.total_os),        color:"#3B7EF5", icon:"📋", sub:null },
          { label:"Pacientes Atendidos", val:num(resumo?.pacientes_unicos),color:"#8B5CF6", icon:"👥", sub:null },
          { label:"Assistencial",
            val: num(resumo?.assistencial),
            color: resumo?.assistencial > 0 ? "#3B7EF5" : "#475569",
            icon:"🩺", sub:null },
          { label:"Ocupacional",
            val: num(resumo?.ocupacional),
            color: resumo?.ocupacional > 0 ? "#F59E0B" : "#475569",
            icon:"🏭", sub: resumo?.outros > 0 ? `+${num(resumo.outros)} outros` : null },
          { label:"Em Atend. Agora", val:num(resumo?.em_atendimento),  color:"#10B981", icon:"⚡", sub:null },
          { label:"Tempo de Atend.",
            val: resumo?.tempo_medio_min > 0 ? `${Math.round(resumo.tempo_medio_min)}min` : "—",
            color:"#0891B2", icon:"⏱",
            sub: resumo?.tempo_medio_min > 0 ? "duração do atendimento" : "sem dados" },
        ].map((k,i) => (
          <div key={i} style={{ background:"#1E293B", borderRadius:12, padding:"14px 16px",
            borderTop:`3px solid ${k.color}` }}>
            <div style={{ fontSize:18, marginBottom:3 }}>{k.icon}</div>
            <div style={{ fontSize:10, color:"#64748B", fontWeight:700, textTransform:"uppercase",
              letterSpacing:"0.07em", marginBottom:3 }}>{k.label}</div>
            {lR
              ? <div style={{ height:28, width:"60%", background:"#334155", borderRadius:6, animation:"pulse 1.5s infinite" }}/>
              : <div style={{ fontSize:26, fontWeight:900, color:k.color, lineHeight:1, letterSpacing:"-0.5px" }}>{k.val}</div>
            }
            {k.sub && <div style={{ fontSize:10, color:"#64748B", marginTop:2 }}>{k.sub}</div>}
          </div>
        ))}
      </div>

      {/* ── TEMPO DE ESPERA ── destaque */}
      {resumo && (
        <div style={{ display:"grid", gridTemplateColumns:"2fr 1fr 1fr 1fr 1fr", gap:12, marginBottom:16 }}>
          {/* Card principal espera */}
          <div style={{ background:"#1E293B", borderRadius:12, padding:"16px 20px",
            borderLeft:"4px solid #F59E0B", display:"flex", alignItems:"center", gap:16 }}>
            <div style={{ fontSize:32 }}>⏳</div>
            <div style={{ flex:1 }}>
              <div style={{ fontSize:11, color:"#64748B", fontWeight:700, textTransform:"uppercase",
                letterSpacing:"0.07em", marginBottom:4 }}>Espera Média na Recepção</div>
              <div style={{ display:"flex", alignItems:"baseline", gap:10 }}>
                {lR
                  ? <div style={{ height:36, width:80, background:"#334155", borderRadius:6, animation:"pulse 1.5s infinite" }}/>
                  : <span style={{ fontSize:34, fontWeight:900, lineHeight:1,
                      color: !resumo.espera_media_min ? "#475569"
                           : resumo.espera_media_min <= 15 ? "#10B981"
                           : resumo.espera_media_min <= 30 ? "#F59E0B" : "#EF4444" }}>
                      {resumo.espera_media_min > 0 ? `${Math.round(resumo.espera_media_min)}min` : "—"}
                    </span>
                }
                {resumo.espera_media_min > 0 && (
                  <span style={{ fontSize:12, color:"#64748B" }}>
                    de espera · base: {resumo.espera_total} pac.
                  </span>
                )}
              </div>
              {/* Barra semáforo */}
              {resumo.espera_media_min > 0 && (
                <div style={{ marginTop:8, height:6, background:"#0F172A", borderRadius:3, overflow:"hidden", width:"100%" }}>
                  <div style={{ height:"100%", borderRadius:3, transition:"width 1s",
                    width:`${Math.min(100,(resumo.espera_media_min/60)*100)}%`,
                    background: resumo.espera_media_min<=15?"#10B981":resumo.espera_media_min<=30?"#F59E0B":"#EF4444"
                  }}/>
                </div>
              )}
            </div>
          </div>

          {/* Sub-cards espera */}
          {[
            { label:"Mín. de Espera",   val: resumo.espera_min_min>0 ? `${Math.round(resumo.espera_min_min)}min` : "—", color:"#10B981" },
            { label:"Máx. de Espera",   val: resumo.espera_max_min>0 ? `${Math.round(resumo.espera_max_min)}min` : "—", color:"#EF4444" },
            { label:"> 30min de Espera",val: resumo.espera_acima_30 > 0 ? num(resumo.espera_acima_30) : "0",
              color: resumo.espera_acima_30 > 0 ? "#EF4444" : "#10B981",
              sub: `de ${num(resumo.espera_total)} agendados` },
            { label:"Senhas Aguardando", val: num(senhasAguardando),
              color: senhasAguardando > 10 ? "#EF4444" : senhasAguardando > 0 ? "#F59E0B" : "#10B981",
              sub: "na recepção", loadingOverride: lSS },
          ].map((k,i) => (
            <div key={i} style={{ background:"#1E293B", borderRadius:12, padding:"14px 16px",
              borderTop:`3px solid ${k.color}` }}>
              <div style={{ fontSize:10, color:"#64748B", fontWeight:700, textTransform:"uppercase",
                letterSpacing:"0.07em", marginBottom:4 }}>{k.label}</div>
              {(k.loadingOverride ?? lR)
                ? <div style={{ height:28, width:"60%", background:"#334155", borderRadius:6, animation:"pulse 1.5s infinite" }}/>
                : <div style={{ fontSize:24, fontWeight:900, color:k.color, lineHeight:1 }}>{k.val}</div>
              }
              {k.sub && <div style={{ fontSize:10, color:"#64748B", marginTop:3 }}>{k.sub}</div>}
            </div>
          ))}
        </div>
      )}


      {/* ── LINHA 3: Evolução por hora + Médicos ── */}
      <div style={{ display:"grid", gridTemplateColumns:"2fr 3fr", gap:14, marginBottom:16 }}>

        {/* Evolução por hora */}
        <div style={{ background:"#1E293B", borderRadius:14, padding:"16px 18px" }}>
          <div style={{ fontSize:13, color:"#94A3B8", fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:12 }}>
            📈 Atendimentos por Hora
          </div>
          {!evolucao?.length ? (
            <div style={{ color:"#475569", fontSize:13, padding:"20px 0", textAlign:"center" }}>Sem dados</div>
          ) : (
            <div>
              {/* Mini bar chart manual */}
              {(() => {
                const max = Math.max(...(evolucao||[]).map(e=>e.atendimentos||0), 1);
                const horaAtual = agora.getHours();
                return (
                  <div style={{ display:"flex", alignItems:"flex-end", gap:3, height:100 }}>
                    {Array.from({length:18},(_,i)=>i+6).map(h => {
                      const e   = (evolucao||[]).find(r=>r.hora===h);
                      const qty = e?.atendimentos||0;
                      const pct = (qty/max)*100;
                      const isNow = h === horaAtual;
                      return (
                        <div key={h} style={{ flex:1, display:"flex", flexDirection:"column", alignItems:"center", gap:3 }}>
                          {qty>0 && <span style={{ fontSize:9, color:isNow?"#3B7EF5":"#64748B", fontWeight:700 }}>{qty}</span>}
                          <div style={{ width:"100%", height:`${Math.max(4,pct)}%`,
                            background:isNow?"#3B7EF5":qty>0?"#334155":"#1E293B",
                            borderRadius:"3px 3px 0 0",
                            border:isNow?"1px solid #3B7EF5":"none",
                            minHeight:4 }}/>
                          <span style={{ fontSize:8, color: isNow?"#3B7EF5":"#475569" }}>{h}h</span>
                        </div>
                      );
                    })}
                  </div>
                );
              })()}
            </div>
          )}
        </div>

        {/* Médicos Executante + Solicitante */}
        <div style={{ display:"grid", gridTemplateColumns:"1fr 1fr", gap:10 }}>
          {/* Executante */}
          <div style={{ background:"#1E293B", borderRadius:14, padding:"14px 16px", overflowY:"auto", maxHeight:220 }}>
            <div style={{ fontSize:11, color:"#94A3B8", fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:10 }}>
              👨‍⚕️ Médico Executante
            </div>
            {lM ? <div style={{ color:"#475569", fontSize:12 }}>Carregando...</div> : (
              <div style={{ display:"flex", flexDirection:"column", gap:5 }}>
                {Object.entries(
                  (medicos||[]).reduce((acc, m) => {
                    const k = m.medico?.trim();
                    if (!acc[k]) acc[k] = { medico:k, atend:0, pac:0, ativo:0, tipos:[] };
                    acc[k].atend += m.atendimentos||0;
                    acc[k].pac   += m.pacientes||0;
                    acc[k].ativo += m.em_atend_agora||0;
                    acc[k].tipos.push(m.tipo_atend);
                    return acc;
                  }, {})
                ).sort((a,b)=>b[1].atend-a[1].atend).map(([nome, m], i) => {
                  const ativo = m.ativo > 0;
                  return (
                    <div key={i} style={{ display:"flex", alignItems:"center", gap:8, padding:"6px 8px",
                      borderRadius:7, background:"#0F172A",
                      border:`1px solid ${ativo?"#10B981":"#1E293B"}` }}>
                      <div style={{ width:7, height:7, borderRadius:"50%", flexShrink:0,
                        background:ativo?"#10B981":"#475569",
                        boxShadow:ativo?"0 0 6px #10B981":"none" }}/>
                      <div style={{ flex:1, minWidth:0 }}>
                        <div style={{ fontSize:12, fontWeight:700, color:"#F1F5F9",
                          overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{nome}</div>
                      </div>
                      <div style={{ textAlign:"right", flexShrink:0 }}>
                        <span style={{ fontSize:15, fontWeight:900, color:"#3B7EF5" }}>{m.atend}</span>
                        <span style={{ fontSize:10, color:"#64748B", marginLeft:4 }}>guias</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Solicitante */}
          <div style={{ background:"#1E293B", borderRadius:14, padding:"14px 16px", overflowY:"auto", maxHeight:220 }}>
            <div style={{ fontSize:11, color:"#94A3B8", fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:10 }}>
              📋 Médico Solicitante
            </div>
            {lMR ? <div style={{ color:"#475569", fontSize:12 }}>Carregando...</div> : (
              <div style={{ display:"flex", flexDirection:"column", gap:5 }}>
                {Object.entries(
                  (medicosReq||[]).reduce((acc, m) => {
                    const k = m.medico?.trim();
                    if (!acc[k]) acc[k] = { medico:k, atend:0, pac:0, tipos:[] };
                    acc[k].atend += m.atendimentos||0;
                    acc[k].pac   += m.pacientes||0;
                    acc[k].tipos.push(m.tipo_atend);
                    return acc;
                  }, {})
                ).sort((a,b)=>b[1].atend-a[1].atend).map(([nome, m], i) => (
                  <div key={i} style={{ display:"flex", alignItems:"center", gap:8, padding:"6px 8px",
                    borderRadius:7, background:"#0F172A", border:"1px solid #1E293B" }}>
                    <div style={{ flex:1, minWidth:0 }}>
                      <div style={{ fontSize:12, fontWeight:700, color:"#F1F5F9",
                        overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap" }}>{nome}</div>
                    </div>
                    <div style={{ textAlign:"right", flexShrink:0 }}>
                      <span style={{ fontSize:15, fontWeight:900, color:"#8B5CF6" }}>{m.atend}</span>
                      <span style={{ fontSize:10, color:"#64748B", marginLeft:4 }}>guias</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── LINHA DO TEMPO ── */}
      <div style={{ background:"#1E293B", borderRadius:14, padding:"16px 18px" }}>
        <div style={{ fontSize:13, color:"#94A3B8", fontWeight:700, textTransform:"uppercase", letterSpacing:"0.07em", marginBottom:14 }}>
          🕐 Linha do Tempo — Últimos Atendimentos
        </div>
        {lL ? <div style={{ color:"#475569", fontSize:13 }}>Carregando...</div> : (
          <div style={{ display:"flex", flexDirection:"column", gap:0 }}>
            {(linha||[]).slice(0,5).map((os,i) => {
              const cor   = STATUS_COR[os.status] || "#64748B";
              const isLast = i === (linha||[]).slice(0,5).length-1;
              return (
                <div key={i} style={{ display:"flex", gap:14, alignItems:"flex-start" }}>
                  {/* Timeline dot & line */}
                  <div style={{ display:"flex", flexDirection:"column", alignItems:"center", flexShrink:0, width:20 }}>
                    <div style={{ width:12, height:12, borderRadius:"50%", background:cor,
                      boxShadow:`0 0 8px ${cor}80`, flexShrink:0, marginTop:4 }}/>
                    {!isLast && <div style={{ width:2, flex:1, background:"#334155", minHeight:28 }}/>}
                  </div>
                  {/* Conteúdo */}
                  <div style={{ flex:1, paddingBottom:16, minWidth:0 }}>
                    <div style={{ display:"flex", justifyContent:"space-between", alignItems:"center" }}>
                      <div style={{ display:"flex", alignItems:"center", gap:8, minWidth:0, flex:1 }}>
                        <span style={{ fontSize:12, fontWeight:700, color:"#94A3B8", flexShrink:0 }}>{os.hora_abertura?.slice(0,5)}</span>
                        <span style={{ fontSize:13, fontWeight:700, color:"#F1F5F9",
                          overflow:"hidden", textOverflow:"ellipsis", whiteSpace:"nowrap", maxWidth:200 }}>
                          {os.paciente?.trim() || "Paciente"}
                        </span>
                        <span style={{ fontSize:11, color:"#64748B", flexShrink:0 }}>— {os.medico?.trim()}</span>
                        <span style={{ fontSize:10, color:"#64748B", background:"#0F172A",
                          padding:"1px 6px", borderRadius:4, flexShrink:0 }}>
                          {ATEND_LABEL[os.osm_atend]||os.osm_atend}
                        </span>
                      </div>
                      <div style={{ display:"flex", alignItems:"center", gap:10, flexShrink:0, marginLeft:10 }}>
                        {os.duracao_min != null && (
                          <span style={{ fontSize:12, fontWeight:700, color:os.duracao_min>60?"#EF4444":os.duracao_min>30?"#F59E0B":"#10B981" }}>
                            ⏱ {os.duracao_min}min
                          </span>
                        )}
                        <span style={{ fontSize:10, fontWeight:700, color:cor,
                          background:cor+"20", padding:"2px 8px", borderRadius:10 }}>
                          {STATUS_NOME[os.status]||os.status}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Rodapé */}
      <div style={{ marginTop:12, textAlign:"center", fontSize:11, color:"#334155" }}>
        Atualiza automaticamente a cada 30 segundos · Última atualização: {resumo?.hora_atual || "—"}
      </div>

      <style dangerouslySetInnerHTML={{__html: `
        @keyframes pulse      { 0%,100%{opacity:1} 50%{opacity:.4} }
        @keyframes glow       { 0%,100%{box-shadow:0 0 8px rgba(16,185,129,0.5)} 50%{box-shadow:0 0 16px #10B981} }
        @keyframes celebrar   { 0%{transform:scale(1)} 100%{transform:scale(1.02)} }
        @keyframes fadeInDown { 0%{opacity:0;transform:translateY(-20px)} 100%{opacity:1;transform:translateY(0)} }
        #painel-tv-root:-webkit-full-screen { overflow-y: auto !important; height: 100vh !important; }
        #painel-tv-root:-moz-full-screen    { overflow-y: auto !important; height: 100vh !important; }
        #painel-tv-root:fullscreen          { overflow-y: auto !important; height: 100vh !important; }
      `}}/>
    </div>
  );
}


export default PainelTV;
