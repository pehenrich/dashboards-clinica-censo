import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;
const COR = "#8B1A1A";
const COR2 = "#C0392B";

function useIsMobileLocal() {
  const [mobile, setMobile] = useState(window.innerWidth < 860);
  useEffect(() => {
    const onResize = () => setMobile(window.innerWidth < 860);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  return mobile;
}

function idade(nascimentoISO) {
  if (!nascimentoISO) return "—";
  const nasc = new Date(nascimentoISO);
  if (isNaN(nasc)) return "—";
  const hoje = new Date();
  let anos = hoje.getFullYear() - nasc.getFullYear();
  const m = hoje.getMonth() - nasc.getMonth();
  if (m < 0 || (m === 0 && hoje.getDate() < nasc.getDate())) anos--;
  return anos >= 0 ? `${anos} anos` : "—";
}

function iniciais(nome) {
  if (!nome) return "?";
  const partes = nome.trim().split(/\s+/);
  return ((partes[0]?.[0] || "") + (partes[1]?.[0] || "")).toUpperCase();
}

function hora(dtISO) {
  if (!dtISO) return "—";
  const d = new Date(dtISO);
  if (isNaN(d)) return "—";
  return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function dataHora(dtISO) {
  if (!dtISO) return "—";
  const d = new Date(dtISO);
  if (isNaN(d)) return "—";
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function Skeleton({ h = 80 }) {
  return (
    <div style={{
      height: h, borderRadius: 12,
      background: "linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%)",
      backgroundSize: "200% 100%", animation: "shimmer 1.4s infinite",
    }} />
  );
}

const Card = ({ children, style }) => (
  <div style={{ background: "#fff", borderRadius: 18, boxShadow: "0 1px 4px rgba(0,0,0,.07), 0 0 0 1px rgba(0,0,0,.03)", overflow: "hidden", display: "flex", flexDirection: "column", ...style }}>
    {children}
  </div>
);

// ── HERO — resumo do médico logado ──────────────────────────────────────────
function AtendimentoHero({ nome, fila, loading }) {
  const total = fila?.length || 0;
  const proximo = fila?.[0];
  const esperaMedia = total ? Math.round(fila.reduce((s, p) => s + (p.espera_min || 0), 0) / total) : 0;

  const stats = [
    { label: "Na fila", value: loading ? "—" : String(total), sub: total === 1 ? "paciente" : "pacientes" },
    { label: "Tempo médio de espera", value: loading ? "—" : `${esperaMedia} min`, sub: total ? "aguardando" : "sem fila" },
    { label: "Próximo", value: loading ? "—" : (proximo ? proximo.paciente.split(" ").slice(0, 2).join(" ") : "—"), sub: proximo?.servico || "" },
  ];

  return (
    <div style={{
      background: `linear-gradient(135deg, ${COR} 0%, ${COR2} 100%)`,
      borderRadius: 20, padding: "22px 30px",
      boxShadow: `0 8px 32px ${COR}40`, position: "relative", overflow: "hidden",
    }}>
      <div style={{ position: "absolute", right: -30, top: -30, width: 200, height: 200, borderRadius: "50%", background: "rgba(255,255,255,0.07)", pointerEvents: "none" }} />
      <div style={{ position: "absolute", right: 60, bottom: -60, width: 160, height: 160, borderRadius: "50%", background: "rgba(255,255,255,0.05)", pointerEvents: "none" }} />
      <div style={{ position: "relative" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
          <span style={{ fontSize: 22 }}>🩺</span>
          <div style={{ fontSize: 20, fontWeight: 900, color: "#fff", letterSpacing: "-0.3px" }}>Atendimento — {nome}</div>
        </div>
        <div style={{ fontSize: 13, color: "rgba(255,255,255,0.75)", marginBottom: 22, fontWeight: 500 }}>
          Fila de pacientes recepcionados hoje, em tempo real
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 16 }}>
          {stats.map((s, i) => (
            <div key={i} style={{ background: "rgba(255,255,255,0.15)", borderRadius: 14, padding: "14px 18px", backdropFilter: "blur(4px)", minWidth: 0 }}>
              <div style={{ fontSize: 10, color: "rgba(255,255,255,0.8)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 5 }}>{s.label}</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: "#fff", lineHeight: 1.15, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{s.value}</div>
              {s.sub && <div style={{ fontSize: 11, color: "rgba(255,255,255,0.7)", marginTop: 3 }}>{s.sub}</div>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── FILA ─────────────────────────────────────────────────────────────────────
function Fila({ psvCod, onAbrir, onCarregou }) {
  const [fila, setFila] = useState([]);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState(null);

  const carregar = useCallback(() => {
    setLoading(true); setErro(null);
    fetch(`${API}/api/atendimento/fila?medico=${psvCod}`)
      .then(r => r.json())
      .then(d => { setFila(d.fila || []); setLoading(false); onCarregou?.(d.fila || [], false); })
      .catch(() => { setErro("Não foi possível carregar a fila."); setLoading(false); onCarregou?.([], false); });
  }, [psvCod]);

  useEffect(() => {
    carregar();
    const t = setInterval(carregar, 30000);
    return () => clearInterval(t);
  }, [carregar]);

  return (
    <Card style={{ flex: 1, minHeight: 0 }}>
      <div style={{ padding: "18px 22px", borderBottom: "1px solid #F1F5F9", display: "flex", justifyContent: "space-between", alignItems: "center", flexShrink: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, background: `${COR}12`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>📋</div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: "#0F172A" }}>Fila de Atendimento</div>
            <div style={{ fontSize: 12, color: "#64748B", marginTop: 1 }}>Pacientes recepcionados, aguardando chamada</div>
          </div>
        </div>
        <button onClick={carregar} title="Atualizar" style={{
          width: 36, height: 36, borderRadius: 10, border: "1px solid #E2E8F0", background: "#F8FAFC",
          cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, color: "#64748B",
          transition: "transform .2s",
        }}>↻</button>
      </div>

      {loading ? (
        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 10 }}>
          <Skeleton h={64} /><Skeleton h={64} /><Skeleton h={64} />
        </div>
      ) : erro ? (
        <div style={{ padding: 32, textAlign: "center", color: "#DC2626", fontSize: 13 }}>{erro}</div>
      ) : fila.length === 0 ? (
        <div style={{ padding: 48, textAlign: "center", color: "#CBD5E1" }}>
          <div style={{ fontSize: 38, marginBottom: 10 }}>✓</div>
          <div style={{ fontSize: 14, fontWeight: 700, color: "#94A3B8" }}>Nenhum paciente aguardando</div>
          <div style={{ fontSize: 12, color: "#CBD5E1", marginTop: 4 }}>A fila atualiza automaticamente a cada 30s</div>
        </div>
      ) : (
        <div style={{ overflowY: "auto", flex: 1, minHeight: 0 }}>
          {fila.map((p, i) => (
            <div key={p.pac_reg + "_" + p.chegada} onClick={() => onAbrir(p)}
              style={{
                display: "flex", alignItems: "center", gap: 14, padding: "16px 22px", cursor: "pointer",
                borderBottom: i < fila.length - 1 ? "1px solid #F1F5F9" : "none", transition: "background .12s",
              }}
              onMouseEnter={e => e.currentTarget.style.background = "#FEF2F2"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              <div style={{
                width: 40, height: 40, borderRadius: "50%", flexShrink: 0,
                background: i === 0 ? `linear-gradient(135deg,${COR},${COR2})` : "#F1F5F9",
                color: i === 0 ? "#fff" : "#64748B", display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 13, fontWeight: 800, boxShadow: i === 0 ? `0 4px 12px ${COR}40` : "none",
              }}>{iniciais(p.paciente)}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: "#0F172A", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  {p.paciente}
                </div>
                <div style={{ fontSize: 12, color: "#94A3B8", marginTop: 2, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <span>{idade(p.nascimento)}</span><span>·</span><span>chegou {hora(p.chegada)}</span>
                  {p.servico && <span style={{
                    fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 99,
                    background: `${COR}12`, color: COR,
                  }}>{p.servico}</span>}
                </div>
              </div>
              <div style={{
                fontSize: 11, fontWeight: 800, padding: "5px 12px", borderRadius: 99, flexShrink: 0,
                background: p.espera_min > 30 ? "#FEF2F2" : "#ECFDF5",
                color: p.espera_min > 30 ? "#DC2626" : "#059669",
              }}>{p.espera_min} min</div>
              <div style={{ color: "#CBD5E1", fontSize: 18 }}>›</div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── HISTÓRICO ────────────────────────────────────────────────────────────────
function Historico({ pacReg }) {
  const [historico, setHistorico] = useState([]);
  const [loading, setLoading] = useState(true);
  const [aberto, setAberto] = useState(null);

  useEffect(() => {
    setLoading(true);
    fetch(`${API}/api/atendimento/historico?paciente=${pacReg}&limite=15`)
      .then(r => r.json())
      .then(d => { setHistorico(d.historico || []); setLoading(false); })
      .catch(() => setLoading(false));
  }, [pacReg]);

  if (loading) return <div style={{ display: "flex", flexDirection: "column", gap: 8 }}><Skeleton h={54} /><Skeleton h={54} /></div>;
  if (historico.length === 0) return (
    <div style={{ padding: 28, textAlign: "center", color: "#CBD5E1", background: "#FAFBFC", borderRadius: 12 }}>
      <div style={{ fontSize: 26, marginBottom: 6 }}>📄</div>
      <div style={{ fontSize: 13 }}>Sem registros clínicos anteriores.</div>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {historico.map((h, i) => {
        const ab = aberto === i;
        return (
          <div key={i} style={{ border: "1px solid #F1F5F9", borderLeft: `3px solid ${ab ? COR : "#E2E8F0"}`, borderRadius: 10, overflow: "hidden", transition: "border-color .15s" }}>
            <div onClick={() => setAberto(ab ? null : i)} style={{
              padding: "12px 16px", display: "flex", justifyContent: "space-between", alignItems: "center",
              cursor: "pointer", background: ab ? "#FEF2F2" : "#fff",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{
                  fontSize: 11, fontWeight: 800, color: COR, background: `${COR}12`, padding: "3px 10px", borderRadius: 99,
                }}>{h.servico}</span>
                <span style={{ fontSize: 12, color: "#94A3B8" }}>{dataHora(h.data)}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ fontSize: 11, color: "#94A3B8" }}>{h.medico}</div>
                <span style={{ fontSize: 12, color: "#CBD5E1", transform: ab ? "rotate(180deg)" : "none", transition: "transform .15s" }}>▾</span>
              </div>
            </div>
            {ab && (
              <div style={{ padding: "14px 16px", borderTop: "1px solid #F1F5F9", display: "flex", flexDirection: "column", gap: 10, background: "#FAFBFC" }}>
                {h.campos.length === 0 ? (
                  <div style={{ fontSize: 12, color: "#CBD5E1" }}>Sem campos preenchidos.</div>
                ) : h.campos.map(c => (
                  <div key={c.campo}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase", letterSpacing: ".04em", marginBottom: 2 }}>{c.rotulo}</div>
                    <div style={{ fontSize: 13, color: "#111827", whiteSpace: "pre-wrap" }}>{c.valor}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── BUSCA DE PACIENTE (cadastro geral, fora da fila) ────────────────────────
function BuscaPaciente({ onSelecionar }) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState(null);
  const [buscando, setBuscando] = useState(false);
  const [aberto, setAberto] = useState(false);

  useEffect(() => {
    if (termo.trim().length < 2) { setResultados(null); return; }
    setBuscando(true);
    const t = setTimeout(() => {
      fetch(`${API}/api/atendimento/buscar-paciente?q=${encodeURIComponent(termo.trim())}`)
        .then(r => r.json())
        .then(d => { setResultados(d.pacientes || []); setBuscando(false); })
        .catch(() => setBuscando(false));
    }, 350);
    return () => clearTimeout(t);
  }, [termo]);

  const escolher = (p) => {
    onSelecionar({
      pac_reg: p.pac_reg, paciente: p.nome, nascimento: p.nascimento,
      chegada: null, espera_min: null, servico: null,
    });
    setAberto(false); setTermo(""); setResultados(null);
  };

  return (
    <Card style={{ marginBottom: 16 }}>
      <div onClick={() => setAberto(v => !v)} style={{
        padding: "16px 22px", display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 34, height: 34, borderRadius: 10, background: "#EFF6FF", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16 }}>🔍</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 800, color: "#0F172A" }}>Buscar Paciente</div>
            <div style={{ fontSize: 12, color: "#64748B", marginTop: 1 }}>Atender alguém fora da fila (busca no cadastro)</div>
          </div>
        </div>
        <span style={{ fontSize: 14, color: "#94A3B8", transform: aberto ? "rotate(180deg)" : "none", transition: "transform .15s" }}>▾</span>
      </div>
      {aberto && (
        <div style={{ padding: "0 22px 18px" }}>
          <input autoFocus placeholder="Nome, nº de registro ou CPF..." value={termo}
            onChange={e => setTermo(e.target.value)}
            style={{ width: "100%", padding: "11px 14px", borderRadius: 10, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box", outline: "none" }}
            onFocus={e => e.target.style.borderColor = COR}
            onBlur={e => e.target.style.borderColor = "#E2E8F0"} />
          {buscando && <div style={{ marginTop: 10 }}><Skeleton h={40} /></div>}
          {resultados !== null && !buscando && (
            resultados.length === 0 ? (
              <div style={{ padding: 14, textAlign: "center", color: "#CBD5E1", fontSize: 12 }}>Nenhum paciente encontrado.</div>
            ) : (
              <div style={{ marginTop: 10, maxHeight: 280, overflowY: "auto", display: "flex", flexDirection: "column", gap: 6 }}>
                {resultados.map(p => (
                  <div key={p.pac_reg} onClick={() => escolher(p)} style={{
                    display: "flex", alignItems: "center", gap: 10,
                    padding: "10px 14px", borderRadius: 10, border: "1px solid #F1F5F9", cursor: "pointer",
                  }}
                    onMouseEnter={e => e.currentTarget.style.background = "#FEF2F2"}
                    onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                    <div style={{
                      width: 30, height: 30, borderRadius: "50%", background: "#F1F5F9", color: "#64748B",
                      display: "flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 800, flexShrink: 0,
                    }}>{iniciais(p.nome)}</div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{p.nome}</div>
                      <div style={{ fontSize: 11, color: "#94A3B8" }}>
                        {idade(p.nascimento)} · reg. {p.pac_reg}{p.cpf ? ` · CPF ${p.cpf}` : ""}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}
        </div>
      )}
    </Card>
  );
}

// ── CAMPO CID — busca no catálogo CID-10 ────────────────────────────────────
function CampoCid({ valor, onChange }) {
  const [termo, setTermo] = useState(valor || "");
  const [resultados, setResultados] = useState(null);
  const [aberto, setAberto] = useState(false);
  const [rect, setRect] = useState(null);
  const boxRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { setTermo(valor || ""); }, [valor]);

  useEffect(() => {
    if (!aberto || termo.trim().length < 2) { setResultados(null); return; }
    const t = setTimeout(() => {
      fetch(`${API}/api/atendimento/buscar-cid?q=${encodeURIComponent(termo.trim())}`)
        .then(r => r.json())
        .then(d => setResultados(d.resultados || []))
        .catch(() => setResultados([]));
    }, 300);
    return () => clearTimeout(t);
  }, [termo, aberto]);

  useEffect(() => {
    const fechar = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setAberto(false);
    };
    document.addEventListener("mousedown", fechar);
    return () => document.removeEventListener("mousedown", fechar);
  }, []);

  const abrir = () => {
    if (inputRef.current) {
      const r = inputRef.current.getBoundingClientRect();
      setRect({ top: r.bottom + 4, left: r.left, width: r.width });
    }
    setAberto(true);
  };

  const escolher = (r) => {
    onChange(r.codigo);
    setTermo(r.codigo);
    setAberto(false);
  };

  return (
    <div ref={boxRef}>
      <input ref={inputRef} type="text" value={termo} placeholder="Digite o código ou o nome do diagnóstico..."
        onFocus={abrir}
        onChange={e => { setTermo(e.target.value); onChange(e.target.value); abrir(); }}
        style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
      {aberto && resultados !== null && rect && (
        <div style={{
          position: "fixed", top: rect.top, left: rect.left, width: rect.width, zIndex: 2000,
          background: "#fff", borderRadius: 10, border: "1px solid #E2E8F0", boxShadow: "0 8px 24px rgba(0,0,0,.18)",
          maxHeight: 260, overflowY: "auto",
        }}>
          {resultados.length === 0 ? (
            <div style={{ padding: 14, fontSize: 12, color: "#CBD5E1", textAlign: "center" }}>Nenhum CID encontrado.</div>
          ) : resultados.map(r => (
            <div key={r.codigo} onClick={() => escolher(r)} style={{
              padding: "9px 14px", cursor: "pointer", borderBottom: "1px solid #F8FAFC",
            }}
              onMouseEnter={e => e.currentTarget.style.background = "#FEF2F2"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              <span style={{ fontSize: 12, fontWeight: 800, color: COR }}>{r.codigo}</span>
              <span style={{ fontSize: 12, color: "#475569", marginLeft: 8 }}>{r.nome}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── FORMULÁRIO DE ATENDIMENTO ───────────────────────────────────────────────
function CampoField({ c, valor, onChange }) {
  return (
    <div>
      <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "#334155", marginBottom: 6 }}>
        {c.rotulo}
      </label>
      {c.input === "cid" ? (
        <CampoCid valor={valor || ""} onChange={onChange} />
      ) : c.input === "textarea" ? (
        <textarea rows={3} value={valor || ""} onChange={e => onChange(e.target.value)}
          style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, fontFamily: "inherit", resize: "vertical", boxSizing: "border-box" }} />
      ) : c.input === "select" ? (
        <select value={valor || ""} onChange={e => onChange(e.target.value)}
          style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, background: "#fff", boxSizing: "border-box" }}>
          <option value="">—</option>
          {c.opcoes.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input type="text" value={valor || ""} onChange={e => onChange(e.target.value)}
          style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
      )}
    </div>
  );
}

// ── ABA EVOLUÇÃO ─────────────────────────────────────────────────────────────
function AbaEvolucao({ campos, valores, setValores }) {
  if (campos.length === 0) return <div style={{ padding: 20, textAlign: "center", color: "#CBD5E1", fontSize: 13 }}>Nada a preencher nessa aba.</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {campos.map(c => (
        <CampoField key={c.campo} c={c} valor={valores[c.campo]} onChange={v => setValores(prev => ({ ...prev, [c.campo]: v }))} />
      ))}
    </div>
  );
}

// ── ABA PRESCRIÇÃO ───────────────────────────────────────────────────────────
function AbaPrescricao({ suportado, valor, onChange }) {
  const [itens, setItens] = useState(() => {
    if (!valor) return [{ medicamento: "", posologia: "" }];
    return valor.split("\n").filter(Boolean).map(linha => {
      const [medicamento, ...resto] = linha.split(" — ");
      return { medicamento, posologia: resto.join(" — ") };
    });
  });

  const atualizar = (novos) => {
    setItens(novos);
    const texto = novos
      .filter(i => i.medicamento.trim())
      .map(i => i.posologia.trim() ? `${i.medicamento.trim()} — ${i.posologia.trim()}` : i.medicamento.trim())
      .join("\n");
    onChange(texto);
  };

  if (!suportado) {
    return (
      <div style={{ padding: 28, textAlign: "center", color: "#CBD5E1", background: "#FAFBFC", borderRadius: 12 }}>
        <div style={{ fontSize: 26, marginBottom: 6 }}>💊</div>
        <div style={{ fontSize: 13 }}>Este serviço não usa o campo de prescrição.</div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {itens.map((item, i) => (
          <div key={i} style={{ display: "flex", gap: 8, alignItems: "flex-start", background: "#FAFBFC", padding: 12, borderRadius: 10, border: "1px solid #F1F5F9" }}>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 8 }}>
              <input type="text" placeholder="Medicamento (ex: Dipirona 500mg)" value={item.medicamento}
                onChange={e => { const n = [...itens]; n[i] = { ...n[i], medicamento: e.target.value }; atualizar(n); }}
                style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box", fontWeight: 700 }} />
              <input type="text" placeholder="Posologia (ex: 1 comprimido de 8/8h por 5 dias)" value={item.posologia}
                onChange={e => { const n = [...itens]; n[i] = { ...n[i], posologia: e.target.value }; atualizar(n); }}
                style={{ width: "100%", padding: "9px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
            </div>
            <button onClick={() => atualizar(itens.filter((_, j) => j !== i))} disabled={itens.length === 1} style={{
              width: 32, height: 32, borderRadius: 8, border: "1px solid #E2E8F0", background: "#fff",
              color: itens.length === 1 ? "#E2E8F0" : "#DC2626", cursor: itens.length === 1 ? "not-allowed" : "pointer", fontSize: 14, flexShrink: 0,
            }}>✕</button>
          </div>
        ))}
      </div>
      <button onClick={() => atualizar([...itens, { medicamento: "", posologia: "" }])} style={{
        marginTop: 10, padding: "9px 16px", borderRadius: 9, border: `1.5px dashed ${COR}50`,
        background: "transparent", color: COR, fontWeight: 700, fontSize: 12, cursor: "pointer",
      }}>+ Adicionar medicamento</button>
    </div>
  );
}

// ── ABA DOCUMENTOS (gerar/imprimir — não grava no banco) ───────────────────
function abrirEImprimir(html, titulo) {
  const janela = window.open("", "_blank", "width=900,height=1000");
  janela.document.write(html);
  janela.document.close();
  janela.focus();
  setTimeout(() => janela.print(), 300);
}

// ── busca de procedimento (TUSS) ─────────────────────────────────────────────
function CampoProcedimento({ onEscolher }) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState(null);
  const [aberto, setAberto] = useState(false);
  const [rect, setRect] = useState(null);
  const boxRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!aberto || termo.trim().length < 2) { setResultados(null); return; }
    const t = setTimeout(() => {
      fetch(`${API}/api/atendimento/buscar-procedimento?q=${encodeURIComponent(termo.trim())}`)
        .then(r => r.json()).then(d => setResultados(d.resultados || [])).catch(() => setResultados([]));
    }, 300);
    return () => clearTimeout(t);
  }, [termo, aberto]);

  useEffect(() => {
    const fechar = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setAberto(false); };
    document.addEventListener("mousedown", fechar);
    return () => document.removeEventListener("mousedown", fechar);
  }, []);

  const abrir = () => {
    if (inputRef.current) {
      const r = inputRef.current.getBoundingClientRect();
      setRect({ top: r.bottom + 4, left: r.left, width: r.width });
    }
    setAberto(true);
  };

  return (
    <div ref={boxRef}>
      <input ref={inputRef} type="text" value={termo} placeholder="Buscar exame/procedimento por nome ou código TUSS..."
        onFocus={abrir} onChange={e => { setTermo(e.target.value); abrir(); }}
        style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
      {aberto && resultados !== null && rect && (
        <div style={{
          position: "fixed", top: rect.top, left: rect.left, width: rect.width, zIndex: 2000,
          background: "#fff", borderRadius: 10, border: "1px solid #E2E8F0", boxShadow: "0 8px 24px rgba(0,0,0,.18)",
          maxHeight: 260, overflowY: "auto",
        }}>
          {resultados.length === 0 ? (
            <div style={{ padding: 14, fontSize: 12, color: "#CBD5E1", textAlign: "center" }}>Nenhum procedimento com TUSS cadastrado encontrado.</div>
          ) : resultados.map(r => (
            <div key={r.codigo} onClick={() => { onEscolher(r); setTermo(""); setAberto(false); }} style={{
              padding: "9px 14px", cursor: "pointer", borderBottom: "1px solid #F8FAFC",
            }}
              onMouseEnter={e => e.currentTarget.style.background = "#FEF2F2"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              <span style={{ fontSize: 12, fontWeight: 800, color: COR }}>{r.tuss}</span>
              <span style={{ fontSize: 12, color: "#475569", marginLeft: 8 }}>{r.nome}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Atestado / Declaração ────────────────────────────────────────────────────
function DocAtestado({ item, medicoInfo }) {
  const [tipo, setTipo] = useState("atestado");
  const [dias, setDias] = useState("1");
  const [cid, setCid] = useState("");
  const [texto, setTexto] = useState("");

  const gerar = () => {
    const hoje = new Date().toLocaleDateString("pt-BR");
    const medNome = medicoInfo ? `${medicoInfo.tratamento} ${medicoInfo.nome}`.trim() : "";
    const medCrm = medicoInfo ? `${medicoInfo.conselho} ${medicoInfo.crm}${medicoInfo.uf ? "/" + medicoInfo.uf : ""}` : "";
    const corpo = tipo === "atestado"
      ? `Atesto para os devidos fins que o(a) paciente <b>${item.paciente}</b> necessita de afastamento de suas atividades por <b>${dias} dia(s)</b>, a partir desta data.${cid ? ` CID: <b>${cid}</b>.` : ""}${texto ? `<br/><br/>${texto}` : ""}`
      : `Declaro para os devidos fins que o(a) paciente <b>${item.paciente}</b> compareceu a esta unidade de saúde na data de hoje.${texto ? `<br/><br/>${texto}` : ""}`;
    const titulo = tipo === "atestado" ? "ATESTADO MÉDICO" : "DECLARAÇÃO DE COMPARECIMENTO";
    const html = `
      <html><head><title>${titulo}</title>
      <style>
        body { font-family: 'DM Sans', Arial, sans-serif; padding: 60px 70px; color: #111; }
        h1 { text-align:center; font-size:16px; letter-spacing:2px; margin-bottom:50px; }
        .cabecalho { text-align:center; margin-bottom:40px; }
        .cabecalho b { font-size:15px; }
        .corpo { font-size:14px; line-height:2; text-align:justify; margin-bottom:80px; }
        .assinatura { text-align:center; margin-top:100px; }
        .linha { border-top:1px solid #111; width:320px; margin:0 auto 6px; }
        .data { text-align:right; margin-bottom:40px; font-size:13px; }
      </style></head>
      <body>
        <div class="cabecalho"><b>Clínica Censo</b><br/>Parauapebas · PA</div>
        <h1>${titulo}</h1>
        <div class="data">Parauapebas, ${hoje}</div>
        <div class="corpo">${corpo}</div>
        <div class="assinatura"><div class="linha"></div>${medNome}<br/>${medCrm}</div>
      </body></html>`;
    abrirEImprimir(html, titulo);
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        {[{ id: "atestado", label: "Atestado Médico" }, { id: "declaracao", label: "Declaração de Comparecimento" }].map(t => (
          <button key={t.id} onClick={() => setTipo(t.id)} style={{
            flex: 1, padding: "10px 14px", borderRadius: 10, cursor: "pointer",
            border: tipo === t.id ? `1.5px solid ${COR}` : "1.5px solid #E2E8F0",
            background: tipo === t.id ? `${COR}0D` : "#fff", color: tipo === t.id ? COR : "#64748B",
            fontWeight: 700, fontSize: 12.5,
          }}>{t.label}</button>
        ))}
      </div>

      {tipo === "atestado" && (
        <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
          <div style={{ flex: 1 }}>
            <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "#334155", marginBottom: 6 }}>Dias de afastamento</label>
            <input type="number" min="1" value={dias} onChange={e => setDias(e.target.value)}
              style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
          </div>
          <div style={{ flex: 2 }}>
            <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "#334155", marginBottom: 6 }}>CID (opcional)</label>
            <CampoCid valor={cid} onChange={setCid} />
          </div>
        </div>
      )}

      <div>
        <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "#334155", marginBottom: 6 }}>Observação adicional (opcional)</label>
        <textarea rows={3} value={texto} onChange={e => setTexto(e.target.value)}
          style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, fontFamily: "inherit", resize: "vertical", boxSizing: "border-box" }} />
      </div>

      <button onClick={gerar} style={{
        marginTop: 18, padding: "13px 22px", borderRadius: 11, border: "none",
        background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff",
        fontSize: 14, fontWeight: 700, cursor: "pointer", boxShadow: `0 4px 14px ${COR}40`,
      }}>🖨️ Gerar e Imprimir</button>
    </div>
  );
}

// ── busca de convênio (pra trocar o usado na guia, sem mexer no cadastro) ───
function CampoConvenio({ onEscolher }) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState(null);
  const [aberto, setAberto] = useState(false);
  const [rect, setRect] = useState(null);
  const boxRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!aberto || termo.trim().length < 2) { setResultados(null); return; }
    const t = setTimeout(() => {
      fetch(`${API}/api/atendimento/buscar-convenio?q=${encodeURIComponent(termo.trim())}`)
        .then(r => r.json()).then(d => setResultados(d.resultados || [])).catch(() => setResultados([]));
    }, 300);
    return () => clearTimeout(t);
  }, [termo, aberto]);

  useEffect(() => {
    const fechar = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setAberto(false); };
    document.addEventListener("mousedown", fechar);
    return () => document.removeEventListener("mousedown", fechar);
  }, []);

  const abrir = () => {
    if (inputRef.current) {
      const r = inputRef.current.getBoundingClientRect();
      setRect({ top: r.bottom + 4, left: r.left, width: r.width });
    }
    setAberto(true);
  };

  return (
    <div ref={boxRef}>
      <input ref={inputRef} type="text" value={termo} placeholder="Buscar convênio por nome ou código..."
        onFocus={abrir} onChange={e => { setTermo(e.target.value); abrir(); }}
        style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
      {aberto && resultados !== null && rect && (
        <div style={{
          position: "fixed", top: rect.top, left: rect.left, width: rect.width, zIndex: 2000,
          background: "#fff", borderRadius: 10, border: "1px solid #E2E8F0", boxShadow: "0 8px 24px rgba(0,0,0,.18)",
          maxHeight: 260, overflowY: "auto",
        }}>
          {resultados.length === 0 ? (
            <div style={{ padding: 14, fontSize: 12, color: "#CBD5E1", textAlign: "center" }}>Nenhum convênio encontrado.</div>
          ) : resultados.map(r => (
            <div key={r.codigo} onClick={() => { onEscolher(r); setTermo(""); setAberto(false); }} style={{
              padding: "9px 14px", cursor: "pointer", borderBottom: "1px solid #F8FAFC",
              display: "flex", alignItems: "center", gap: 8,
            }}
              onMouseEnter={e => e.currentTarget.style.background = "#FEF2F2"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              <span style={{ fontSize: 12, fontWeight: 700, color: "#334155" }}>{r.nome}</span>
              <span style={{ fontSize: 10, color: "#94A3B8" }}>({r.codigo})</span>
              {r.tiss === "S" && <span style={{ fontSize: 9, fontWeight: 800, color: "#059669", background: "#ECFDF5", padding: "1px 6px", borderRadius: 99 }}>TISS</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Guia SP/SADT (solicitação de exames/procedimentos ao convênio) ─────────
function DocGuiaSadt({ item, medicoInfo }) {
  const [paciente, setPaciente] = useState(null);
  const [clinica, setClinica] = useState(null);
  const [carater, setCarater] = useState("eletivo");
  const [cid, setCid] = useState("");
  const [indicacao, setIndicacao] = useState("");
  const [itens, setItens] = useState([]);
  const [convenio, setConvenio] = useState(null); // {codigo, nome, reg_ans} — pode ser trocado sem alterar o cadastro
  const [carteirinha, setCarteirinha] = useState("");
  const [trocandoConvenio, setTrocandoConvenio] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/atendimento/paciente/${item.pac_reg}`).then(r => r.json()).then(d => {
      setPaciente(d);
      if (d.convenio_cod) setConvenio({ codigo: d.convenio_cod, nome: d.convenio_nome, reg_ans: d.convenio_reg_ans });
      setCarteirinha(d.carteirinha || "");
    }).catch(() => {});
    fetch(`${API}/api/atendimento/clinica`).then(r => r.json()).then(setClinica).catch(() => {});
  }, [item.pac_reg]);

  const escolherConvenio = (c) => {
    setConvenio({ codigo: c.codigo, nome: c.nome, reg_ans: c.reg_ans });
    setCarteirinha(""); // carteirinha é específica de cada convênio — não reaproveita
    setTrocandoConvenio(false);
  };

  const semConvenio = paciente && !convenio;

  const adicionar = (proc) => setItens(prev => [...prev, { ...proc, qtd: 1 }]);
  const remover = (i) => setItens(prev => prev.filter((_, j) => j !== i));
  const setQtd = (i, qtd) => setItens(prev => prev.map((it, j) => j === i ? { ...it, qtd } : it));

  const gerar = () => {
    const hoje = new Date().toLocaleDateString("pt-BR");
    const medNome = medicoInfo ? `${medicoInfo.tratamento} ${medicoInfo.nome}`.trim() : "";
    const medConselho = medicoInfo?.conselho || "";
    const medNumConselho = medicoInfo?.crm || "";
    const medUf = medicoInfo?.uf || "";
    const logoUrl = convenio?.codigo ? `${API}/tiss-logos/c-${convenio.codigo.trim()}.bmp` : "";

    const linhasProc = itens.map(it => `
      <tr>
        <td>${hoje}</td><td style="text-align:center">22</td><td>${it.tuss}</td><td>${it.nome}</td><td style="text-align:center">${it.qtd}</td>
      </tr>`).join("");
    // preenche linhas vazias até 5, pra manter o formato de tabela do formulário oficial
    const linhasVazias = Array.from({ length: Math.max(0, 5 - itens.length) })
      .map(() => `<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>`).join("");

    const box = (num, lbl, val, width) => `
      <div class="box" style="width:${width}">
        <span class="num">${num}</span>
        <span class="lbl">${lbl}</span>
        <span class="val">${val || "&nbsp;"}</span>
      </div>`;

    const html = `
      <html><head><title>GUIA SP/SADT</title>
      <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; padding: 22px 28px; color: #111; font-size: 11px; }
        .topo { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px; }
        .topo-boxes { display:flex; gap:0; }
        .logo { height:44px; object-fit:contain; }
        h1 { text-align:center; font-size:13px; letter-spacing:.5px; margin:6px 0 14px; text-transform:uppercase; }
        .aviso { background:#FFF7E6; border:1px solid #D9A400; padding:6px 10px; margin-bottom:12px; font-size:10px; }
        .secao { background:#8B1A1A; color:#fff; font-size:9.5px; font-weight:700; text-transform:uppercase;
                 letter-spacing:.04em; padding:3px 8px; margin-top:10px; }
        .linha-boxes { display:flex; flex-wrap:wrap; border:1px solid #111; border-top:none; }
        .box { border-right:1px solid #111; border-bottom:1px solid #111; padding:3px 6px 4px; position:relative; min-height:34px; }
        .box:last-child { border-right:none; }
        .box .num { position:absolute; top:1px; left:3px; font-size:7px; color:#888; font-weight:700; }
        .box .lbl { display:block; font-size:7px; color:#555; text-transform:uppercase; margin-top:7px; }
        .box .val { display:block; font-size:11px; font-weight:600; margin-top:1px; }
        table.proc { width:100%; border-collapse:collapse; border:1px solid #111; border-top:none; }
        table.proc th, table.proc td { border:1px solid #111; padding:4px 6px; font-size:10px; height:20px; }
        table.proc th { background:#F1F5F9; text-align:left; font-size:8.5px; text-transform:uppercase; }
        .assinatura { text-align:center; margin-top:60px; }
        .linha-assin { border-top:1px solid #111; width:300px; margin:0 auto 5px; }
        .rodape { margin-top:24px; font-size:8px; color:#999; text-align:center; }
      </style></head>
      <body>
        <div class="topo">
          <div class="linha-boxes" style="border-bottom:none;">
            ${box(1, "Registro ANS", convenio?.reg_ans, "170px")}
            ${box(2, "Nº Guia no Prestador", `<b style="color:#B45309">A PREENCHER</b>`, "220px")}
          </div>
          ${logoUrl ? `<img class="logo" src="${logoUrl}" onerror="this.style.display='none'"/>` : ""}
        </div>
        <h1>Guia de Solicitação de SP/SADT</h1>
        <div class="aviso">⚠ Documento gerado pelo Dashboard Censo como SOLICITAÇÃO — o número oficial da guia e a autorização são atribuídos pelo setor de faturamento / operadora, não por este sistema.</div>

        <div class="secao">Dados do Beneficiário</div>
        <div class="linha-boxes">
          ${box(3, "Nº Carteira", carteirinha, "45%")}
          ${box(4, "Validade da Carteira", "", "20%")}
          ${box(5, "Nome", item.paciente, "35%")}
        </div>

        <div class="secao">Dados do Contratado Solicitante</div>
        <div class="linha-boxes">
          ${box(6, "Nome do Contratado", clinica?.nome, "45%")}
          ${box(7, "CNES", clinica?.cnes, "15%")}
          ${box(8, "CNPJ", clinica?.cnpj, "40%")}
        </div>
        <div class="linha-boxes">
          ${box(9, "Nome do Profissional Solicitante", medNome, "45%")}
          ${box(10, "Conselho", medConselho, "15%")}
          ${box(11, "Número no Conselho", medNumConselho, "20%")}
          ${box(12, "UF", medUf, "20%")}
        </div>

        <div class="secao">Dados da Solicitação</div>
        <div class="linha-boxes">
          ${box(13, "Data da Solicitação", hoje, "25%")}
          ${box(14, "Caráter do Atendimento", carater === "eletivo" ? "1 - Eletivo" : "2 - Urgência/Emergência", "25%")}
          ${box(15, "CID", cid, "50%")}
        </div>
        <div class="linha-boxes">
          ${box(16, "Indicação Clínica", indicacao, "100%")}
        </div>

        <div class="secao">Procedimentos ou Exames Solicitados</div>
        <table class="proc">
          <tr>
            <th style="width:70px">17 Data</th><th style="width:45px">18 Tabela</th>
            <th style="width:90px">19 Código</th><th>20 Descrição</th><th style="width:50px">21 Qtd.</th>
          </tr>
          ${linhasProc}
          ${linhasVazias}
        </table>

        <div class="assinatura">
          <div class="linha-assin"></div>
          Data: ${hoje} &nbsp;·&nbsp; Assinatura e carimbo do profissional solicitante<br/>
          ${medNome} — ${medConselho} ${medNumConselho}${medUf ? "/" + medUf : ""}
        </div>
        <div class="rodape">Documento gerado pelo Dashboard Censo · não substitui a guia oficial emitida/autorizada pela operadora</div>
      </body></html>`;
    abrirEImprimir(html, "GUIA SP/SADT");
  };

  return (
    <div>
      {paciente === null ? <Skeleton h={80} /> : trocandoConvenio ? (
        <div style={{ padding: 14, borderRadius: 10, background: "#F8FAFC", border: "1px solid #E2E8F0", marginBottom: 16 }}>
          <div style={{ fontSize: 10, color: "#94A3B8", fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>
            Trocar convênio (só pra essa guia — não altera o cadastro do paciente)
          </div>
          <CampoConvenio onEscolher={escolherConvenio} />
          <button onClick={() => setTrocandoConvenio(false)} style={{
            marginTop: 8, padding: "6px 12px", borderRadius: 8, border: "1px solid #E2E8F0",
            background: "#fff", color: "#64748B", fontWeight: 700, fontSize: 11, cursor: "pointer",
          }}>Cancelar</button>
        </div>
      ) : semConvenio ? (
        <div style={{ padding: 16, background: "#FFF7E6", border: "1px solid #F5C542", borderRadius: 10, fontSize: 13, color: "#92650A", marginBottom: 16 }}>
          ⚠ Este paciente não tem convênio cadastrado (particular).
          <button onClick={() => setTrocandoConvenio(true)} style={{
            marginLeft: 10, padding: "5px 12px", borderRadius: 8, border: "1px solid #F5C542",
            background: "#fff", color: "#92650A", fontWeight: 700, fontSize: 11, cursor: "pointer",
          }}>+ Definir convênio pra essa guia</button>
        </div>
      ) : (
        <div style={{ display: "flex", gap: 10, marginBottom: 16, alignItems: "stretch" }}>
          <div style={{ flex: 1, padding: "10px 14px", borderRadius: 10, background: "#F8FAFC", border: "1px solid #E2E8F0" }}>
            <div style={{ fontSize: 10, color: "#94A3B8", fontWeight: 700, textTransform: "uppercase" }}>Convênio</div>
            <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{convenio.nome || convenio.codigo}</div>
          </div>
          <div style={{ flex: 1, padding: "10px 14px", borderRadius: 10, background: "#F8FAFC", border: "1px solid #E2E8F0" }}>
            <div style={{ fontSize: 10, color: "#94A3B8", fontWeight: 700, textTransform: "uppercase" }}>Nº da Carteira</div>
            <input type="text" value={carteirinha} onChange={e => setCarteirinha(e.target.value)} placeholder="não informada"
              style={{ width: "100%", border: "none", background: "transparent", padding: 0, fontSize: 13, fontWeight: 700, color: "#0F172A", outline: "none" }} />
          </div>
          <button onClick={() => setTrocandoConvenio(true)} title="Trocar convênio" style={{
            flexShrink: 0, padding: "0 16px", borderRadius: 10, border: "1px solid #E2E8F0",
            background: "#fff", color: COR, fontWeight: 700, fontSize: 12, cursor: "pointer",
          }}>Trocar</button>
        </div>
      )}

      <div style={{
        display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "#92650A",
        background: "#FFF7E6", border: "1px solid #F5C542", borderRadius: 10, padding: "10px 14px", marginBottom: 18,
      }}>
        <span style={{ fontSize: 14 }}>⚠️</span>
        <span>Número da guia fica em branco (a clínica não usa numeração automática pra nenhum convênio) — o faturamento completa depois.</span>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 16 }}>
        <div style={{ flex: 1 }}>
          <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "#334155", marginBottom: 6 }}>Caráter do atendimento</label>
          <select value={carater} onChange={e => setCarater(e.target.value)}
            style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, background: "#fff", boxSizing: "border-box" }}>
            <option value="eletivo">Eletivo</option>
            <option value="urgencia">Urgência/Emergência</option>
          </select>
        </div>
        <div style={{ flex: 2 }}>
          <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "#334155", marginBottom: 6 }}>CID</label>
          <CampoCid valor={cid} onChange={setCid} />
        </div>
      </div>

      <div style={{ marginBottom: 16 }}>
        <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "#334155", marginBottom: 6 }}>Indicação clínica</label>
        <textarea rows={2} value={indicacao} onChange={e => setIndicacao(e.target.value)}
          style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, fontFamily: "inherit", resize: "vertical", boxSizing: "border-box" }} />
      </div>

      <label style={{ display: "block", fontSize: 12.5, fontWeight: 700, color: "#334155", marginBottom: 6 }}>Procedimentos / exames solicitados</label>
      <CampoProcedimento onEscolher={adicionar} />

      {itens.length > 0 && (
        <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 6 }}>
          {itens.map((it, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10, background: "#FAFBFC", border: "1px solid #F1F5F9", borderRadius: 8, padding: "8px 12px" }}>
              <span style={{ fontSize: 11, fontWeight: 800, color: COR, flexShrink: 0 }}>{it.tuss}</span>
              <span style={{ fontSize: 12, color: "#334155", flex: 1 }}>{it.nome}</span>
              <input type="number" min="1" value={it.qtd} onChange={e => setQtd(i, e.target.value)}
                style={{ width: 50, padding: "5px 6px", borderRadius: 6, border: "1px solid #E2E8F0", fontSize: 12, textAlign: "center" }} />
              <button onClick={() => remover(i)} style={{ width: 26, height: 26, borderRadius: 6, border: "1px solid #E2E8F0", background: "#fff", color: "#DC2626", cursor: "pointer", fontSize: 12 }}>✕</button>
            </div>
          ))}
        </div>
      )}

      <button onClick={gerar} disabled={itens.length === 0} style={{
        marginTop: 18, padding: "13px 22px", borderRadius: 11, border: "none",
        background: itens.length === 0 ? "#CBD5E1" : `linear-gradient(135deg,${COR},${COR2})`, color: "#fff",
        fontSize: 14, fontWeight: 700, cursor: itens.length === 0 ? "not-allowed" : "pointer",
        boxShadow: itens.length === 0 ? "none" : `0 4px 14px ${COR}40`,
      }}>🖨️ Gerar e Imprimir</button>
    </div>
  );
}

// ── ABA DOCUMENTOS ───────────────────────────────────────────────────────────
function AbaDocumentos({ item, medico }) {
  const [tipo, setTipo] = useState("atestado");
  const [medicoInfo, setMedicoInfo] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/atendimento/medico/${medico}`).then(r => r.json()).then(setMedicoInfo).catch(() => {});
  }, [medico]);

  return (
    <div>
      <div style={{
        display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "#2563EB",
        background: "#EFF6FF", border: "1px solid #DBEAFE", borderRadius: 10, padding: "10px 14px", marginBottom: 18,
      }}>
        <span style={{ fontSize: 14 }}>ℹ️</span>
        <span>Documentos são gerados só para impressão — não ficam salvos no Smart.</span>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 18, borderBottom: "1px solid #F1F5F9", paddingBottom: 12 }}>
        {[{ id: "atestado", label: "Atestado / Declaração" }, { id: "guia", label: "Guia SP/SADT" }].map(t => (
          <button key={t.id} onClick={() => setTipo(t.id)} style={{
            padding: "8px 16px", borderRadius: 99, cursor: "pointer",
            border: tipo === t.id ? "none" : "1.5px solid #E2E8F0",
            background: tipo === t.id ? `linear-gradient(135deg,${COR},${COR2})` : "#fff",
            color: tipo === t.id ? "#fff" : "#64748B", fontWeight: 700, fontSize: 12.5,
          }}>{t.label}</button>
        ))}
      </div>

      {tipo === "atestado"
        ? <DocAtestado item={item} medicoInfo={medicoInfo} />
        : <DocGuiaSadt item={item} medicoInfo={medicoInfo} />}
    </div>
  );
}

// ── TELA DE ATENDIMENTO (página inteira — Evolução / Prescrição / Documentos) ─
function TelaAtendimento({ item, medico, login, servico, onSalvo, onCancelar }) {
  const [template, setTemplate] = useState(undefined); // undefined=carregando, null=não mapeado
  const [valores, setValores] = useState({});
  const [aba, setAba] = useState("evolucao");
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/atendimento/template?servico=${encodeURIComponent(servico)}`)
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(setTemplate)
      .catch(() => setTemplate(null));
  }, [servico]);

  const salvar = async () => {
    setSalvando(true); setMsg(null);
    try {
      const res = await fetch(`${API}/api/atendimento/salvar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paciente: item.pac_reg, medico, servico, login, campos: valores }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.detail || "Erro ao salvar.");
      setMsg({ ok: true, txt: "Registro salvo em smart_hml." });
      onSalvo?.();
    } catch (e) {
      setMsg({ ok: false, txt: e.message });
    }
    setSalvando(false);
  };

  const camposEvolucao = template && template.campos ? template.campos.filter(c => c.campo !== "30") : [];
  const campoPrescricao = template && template.campos ? template.campos.find(c => c.campo === "30") : null;

  const ABAS = [
    { id: "evolucao", label: "Evolução", icon: "📝" },
    { id: "prescricao", label: "Prescrição", icon: "💊" },
    { id: "documentos", label: "Documentos", icon: "📄" },
  ];

  return (
    <Card style={{ height: "100%" }}>
      <div style={{
        padding: "18px 24px", borderBottom: "1px solid #F1F5F9", display: "flex", justifyContent: "space-between", alignItems: "center",
        background: "linear-gradient(180deg,#FFFBFB 0%,#fff 100%)", flexShrink: 0,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 42, height: 42, borderRadius: "50%", flexShrink: 0,
            background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 800,
          }}>{iniciais(item.paciente)}</div>
          <div>
            <div style={{ fontSize: 15, fontWeight: 800, color: "#0F172A" }}>{item.paciente}</div>
            <div style={{ fontSize: 11, color: "#94A3B8" }}>
              Atendendo agora {template ? `· ${template.nome}` : ""} {template ? `(modelo ${template.modelo})` : ""}
            </div>
          </div>
        </div>
        <button onClick={onCancelar} style={{
          width: 32, height: 32, borderRadius: 9, border: "1px solid #E2E8F0", background: "#F8FAFC",
          cursor: "pointer", fontSize: 14, color: "#64748B", flexShrink: 0,
        }}>✕</button>
      </div>

      <div style={{ padding: "0 24px", borderBottom: "1px solid #F1F5F9", display: "flex", gap: 4, flexShrink: 0 }}>
        {ABAS.map(a => (
          <button key={a.id} onClick={() => setAba(a.id)} style={{
            padding: "13px 18px", border: "none", background: "none", cursor: "pointer",
            fontSize: 13, fontWeight: 700, color: aba === a.id ? COR : "#94A3B8",
            borderBottom: aba === a.id ? `2.5px solid ${COR}` : "2.5px solid transparent",
            display: "flex", alignItems: "center", gap: 7, marginBottom: -1,
          }}>
            <span>{a.icon}</span>{a.label}
          </button>
        ))}
      </div>

      <div style={{ padding: 24, overflowY: "auto", flex: 1, minHeight: 0 }}>
        {template === undefined ? <Skeleton h={220} /> : template === null ? (
          <div style={{ padding: 22, background: "#FEF2F2", borderRadius: 14, border: "1px solid #FECACA" }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: "#DC2626", marginBottom: 6 }}>
              Serviço "{servico}" ainda não tem formulário mapeado
            </div>
            <div style={{ fontSize: 12, color: "#7F1D1D", lineHeight: 1.5 }}>
              O atendimento por essa plataforma hoje só cobre CONSCLIN, CONSPED, AVOFTAL e RETORNO.
              Para os demais serviços, continue lançando a evolução direto no Smart por enquanto.
              A aba Documentos continua disponível pra imprimir atestado/declaração.
            </div>
          </div>
        ) : (
          <>
            {aba === "evolucao" && (
              <>
                <div style={{
                  display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: COR,
                  background: `${COR}0D`, border: `1px solid ${COR}22`, borderRadius: 10, padding: "10px 14px", marginBottom: 18,
                }}>
                  <span style={{ fontSize: 14 }}>🧪</span>
                  <span><b>Ambiente de teste (smart_hml)</b> · Modelo {template.modelo} · {template.nome}</span>
                </div>
                <AbaEvolucao campos={camposEvolucao} valores={valores} setValores={setValores} />
              </>
            )}
            {aba === "prescricao" && (
              <AbaPrescricao
                suportado={!!campoPrescricao}
                valor={valores["30"] || ""}
                onChange={v => setValores(prev => ({ ...prev, "30": v }))}
              />
            )}
            {aba === "documentos" && <AbaDocumentos item={item} medico={medico} />}
          </>
        )}

        {msg && (
          <div style={{
            marginTop: 16, padding: "11px 14px", borderRadius: 10, fontSize: 13, fontWeight: 600,
            background: msg.ok ? "#ECFDF5" : "#FEF2F2", border: `1px solid ${msg.ok ? "#A7F3D0" : "#FECACA"}`,
            color: msg.ok ? "#065F46" : "#DC2626",
          }}>{msg.txt}</div>
        )}
      </div>

      {template && aba !== "documentos" && (
        <div style={{ padding: "16px 24px", borderTop: "1px solid #F1F5F9", display: "flex", gap: 10, flexShrink: 0 }}>
          <button onClick={salvar} disabled={salvando} style={{
            flex: 1, padding: 13, borderRadius: 11, border: "none",
            background: salvando ? "#CBD5E1" : `linear-gradient(135deg,${COR},${COR2})`,
            color: "#fff", fontSize: 14, fontWeight: 700, cursor: salvando ? "not-allowed" : "pointer",
            boxShadow: salvando ? "none" : `0 4px 14px ${COR}40`,
          }}>{salvando ? "Salvando..." : "Salvar registro"}</button>
          <button onClick={onCancelar} style={{
            padding: "13px 22px", borderRadius: 11, border: "1px solid #E2E8F0", background: "#fff",
            color: "#64748B", fontSize: 13, fontWeight: 700, cursor: "pointer",
          }}>Cancelar</button>
        </div>
      )}
    </Card>
  );
}

// ── SELETOR DE SERVIÇO (quando não detectado automaticamente pela agenda) ──
function SeletorServico({ onEscolher, onCancelar }) {
  const [opcoes, setOpcoes] = useState(null);
  const ICONES = { CONSCLIN: "🩺", CONSPED: "🧸", AVOFTAL: "👁️", RETORNO: "🔁" };

  useEffect(() => {
    fetch(`${API}/api/atendimento/template`).then(r => r.json()).then(setOpcoes).catch(() => setOpcoes({}));
  }, []);

  return (
    <div style={{ padding: 22, background: "#F8FAFC", borderRadius: 14, border: "1px solid #E2E8F0" }}>
      <div style={{ fontSize: 14, fontWeight: 700, color: "#0F172A", marginBottom: 4 }}>
        Não foi possível identificar o serviço automaticamente
      </div>
      <div style={{ fontSize: 12, color: "#64748B", marginBottom: 16 }}>
        Esse paciente não tem um agendamento vinculado hoje. Selecione manualmente o tipo de consulta:
      </div>
      {opcoes === null ? <Skeleton h={140} /> : (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          {Object.entries(opcoes).map(([cod, t]) => (
            <button key={cod} onClick={() => onEscolher(cod)} style={{
              textAlign: "left", padding: "14px 16px", borderRadius: 12, border: "1.5px solid #E2E8F0",
              background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", gap: 12, transition: "all .15s",
            }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = COR; e.currentTarget.style.background = "#FEF2F2"; }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = "#E2E8F0"; e.currentTarget.style.background = "#fff"; }}>
              <span style={{ fontSize: 22 }}>{ICONES[cod] || "📄"}</span>
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{t.nome}</div>
                <div style={{ fontSize: 11, color: "#94A3B8" }}>{cod} · modelo {t.modelo}</div>
              </div>
            </button>
          ))}
        </div>
      )}
      <button onClick={onCancelar} style={{
        marginTop: 16, padding: "9px 18px", borderRadius: 9, border: "1px solid #E2E8F0",
        background: "#fff", color: "#64748B", fontWeight: 700, fontSize: 12, cursor: "pointer",
      }}>Cancelar</button>
    </div>
  );
}

// ── DETALHE DO PACIENTE ──────────────────────────────────────────────────────
function DetalhePaciente({ item, onFechar, onIniciarAtendimento }) {
  const [paciente, setPaciente] = useState(null);
  const [escolhendoServico, setEscolhendoServico] = useState(false);

  useEffect(() => {
    fetch(`${API}/api/atendimento/paciente/${item.pac_reg}`).then(r => r.json()).then(setPaciente).catch(() => {});
  }, [item.pac_reg]);

  const clicarAtender = () => {
    if (item.servico) onIniciarAtendimento(item.servico);
    else setEscolhendoServico(true);
  };

  return (
    <Card style={{ height: "100%" }}>
      <div style={{
        padding: "20px 24px", borderBottom: "1px solid #F1F5F9", display: "flex", justifyContent: "space-between", alignItems: "flex-start",
        background: "linear-gradient(180deg,#FFFBFB 0%,#fff 100%)", flexShrink: 0,
      }}>
        <div style={{ display: "flex", gap: 14 }}>
          <div style={{
            width: 52, height: 52, borderRadius: "50%", flexShrink: 0,
            background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 17, fontWeight: 800,
            boxShadow: `0 4px 14px ${COR}40`,
          }}>{iniciais(item.paciente)}</div>
          <div>
            <div style={{ fontSize: 17, fontWeight: 800, color: "#0F172A" }}>{item.paciente}</div>
            <div style={{ fontSize: 12, color: "#64748B", marginTop: 3 }}>
              {idade(paciente?.nascimento || item.nascimento)}{paciente?.sexo ? ` · ${paciente.sexo === "F" ? "Feminino" : "Masculino"}` : ""}
              {paciente?.telefone ? ` · ${paciente.telefone}` : ""}
            </div>
            <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
              {item.chegada ? (
                <>
                  <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 99, background: "#F8FAFC", color: "#64748B" }}>
                    chegou {hora(item.chegada)}
                  </span>
                  <span style={{
                    fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 99,
                    background: item.espera_min > 30 ? "#FEF2F2" : "#ECFDF5", color: item.espera_min > 30 ? "#DC2626" : "#059669",
                  }}>{item.espera_min} min de espera</span>
                </>
              ) : (
                <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 99, background: "#EFF6FF", color: "#2563EB" }}>
                  atendimento avulso · fora da fila
                </span>
              )}
              {item.servico && (
                <span style={{ fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 99, background: `${COR}12`, color: COR }}>
                  {item.servico}
                </span>
              )}
            </div>
          </div>
        </div>
        <button onClick={onFechar} style={{
          width: 32, height: 32, borderRadius: 9, border: "1px solid #E2E8F0", background: "#F8FAFC",
          cursor: "pointer", fontSize: 14, color: "#64748B", flexShrink: 0,
        }}>✕</button>
      </div>

      <div style={{ padding: 24, overflowY: "auto", flex: 1, minHeight: 0 }}>
        {escolhendoServico ? (
          <SeletorServico
            onEscolher={(servico) => { setEscolhendoServico(false); onIniciarAtendimento(servico); }}
            onCancelar={() => setEscolhendoServico(false)}
          />
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
              <div style={{ fontSize: 14, fontWeight: 800, color: "#0F172A", display: "flex", alignItems: "center", gap: 8 }}>
                <span>📖</span> Histórico Clínico
              </div>
              <button onClick={clicarAtender} style={{
                padding: "10px 20px", borderRadius: 11, border: "none",
                background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff",
                fontSize: 13, fontWeight: 700, cursor: "pointer", boxShadow: `0 4px 14px ${COR}40`,
              }}>Atender</button>
            </div>
            <Historico pacReg={item.pac_reg} />
          </>
        )}
      </div>
    </Card>
  );
}

// ── MÓDULO ────────────────────────────────────────────────────────────────────
export default function Atendimento() {
  const { user } = useAuth();
  const [selecionado, setSelecionado] = useState(null);
  const [servicoAtendimento, setServicoAtendimento] = useState(null); // != null → tela cheia de atendimento
  const [refreshKey, setRefreshKey] = useState(0);
  const [filaAtual, setFilaAtual] = useState([]);
  const [filaLoading, setFilaLoading] = useState(true);
  const mobile = useIsMobileLocal();

  if (!user?.psv_cod) {
    return (
      <Card style={{ padding: 48, textAlign: "center" }}>
        <div style={{ fontSize: 38, marginBottom: 12 }}>🩺</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: "#0F172A", marginBottom: 6 }}>
          Seu usuário não está vinculado a um médico no Smart
        </div>
        <div style={{ fontSize: 13, color: "#64748B" }}>
          O módulo de Atendimento é exclusivo para logins com registro de médico (PSV) associado.
        </div>
      </Card>
    );
  }

  // Tela cheia de atendimento (Evolução/Prescrição/Documentos) — some tudo o resto, mobile e desktop.
  if (selecionado && servicoAtendimento) {
    return (
      <div style={{ height: "100%", padding: mobile ? 10 : "18px 24px", boxSizing: "border-box" }}>
        <TelaAtendimento
          item={selecionado} medico={user.psv_cod} login={user.login} servico={servicoAtendimento}
          onSalvo={() => { setServicoAtendimento(null); setSelecionado(null); setRefreshKey(k => k + 1); }}
          onCancelar={() => setServicoAtendimento(null)}
        />
      </div>
    );
  }

  // Mobile: navegação em drill-down (fila → detalhe em tela cheia), rolagem única da página.
  if (mobile) {
    return (
      <div style={{ minHeight: "100%", padding: 14, boxSizing: "border-box", overflowY: "auto" }}>
        {selecionado ? (
          <DetalhePaciente
            item={selecionado}
            onFechar={() => setSelecionado(null)}
            onIniciarAtendimento={(servico) => setServicoAtendimento(servico)}
          />
        ) : (
          <>
            <AtendimentoHero nome={user.nome?.split(" ").slice(0, 2).join(" ") || user.login} fila={filaAtual} loading={filaLoading} />
            <div style={{ marginTop: 14 }}>
              <BuscaPaciente onSelecionar={setSelecionado} />
            </div>
            <div style={{ marginTop: 14 }}>
              <Fila key={refreshKey} psvCod={user.psv_cod} onAbrir={setSelecionado}
                onCarregou={(f, loading) => { setFilaAtual(f); setFilaLoading(loading); }} />
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column", padding: "18px 24px", boxSizing: "border-box", gap: 16, minHeight: 0 }}>
      <div style={{ flexShrink: 0 }}>
        <AtendimentoHero nome={user.nome?.split(" ").slice(0, 3).join(" ") || user.login} fila={filaAtual} loading={filaLoading} />
      </div>
      <div style={{ flex: 1, minHeight: 0, display: "flex", gap: 18 }}>
        <div style={{ width: 400, flexShrink: 0, display: "flex", flexDirection: "column", gap: 16, minHeight: 0 }}>
          <div style={{ flexShrink: 0 }}>
            <BuscaPaciente onSelecionar={setSelecionado} />
          </div>
          <Fila key={refreshKey} psvCod={user.psv_cod} onAbrir={setSelecionado}
            onCarregou={(f, loading) => { setFilaAtual(f); setFilaLoading(loading); }} />
        </div>
        <div style={{ flex: 1, minWidth: 0, minHeight: 0 }}>
          {selecionado ? (
            <DetalhePaciente
              item={selecionado}
              onFechar={() => setSelecionado(null)}
              onIniciarAtendimento={(servico) => setServicoAtendimento(servico)}
            />
          ) : (
            <Card style={{ height: "100%", alignItems: "center", justifyContent: "center" }}>
              <div style={{ textAlign: "center", color: "#CBD5E1", padding: 40 }}>
                <div style={{ fontSize: 46, marginBottom: 14 }}>🩺</div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#94A3B8" }}>Selecione um paciente</div>
                <div style={{ fontSize: 13, color: "#CBD5E1", marginTop: 4 }}>
                  Escolha alguém na fila ao lado, ou busque um paciente fora da fila
                </div>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
