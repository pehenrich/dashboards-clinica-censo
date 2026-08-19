// Faturamento.jsx — Gestão de Guias Pendentes de Faturamento
// Armazenamento próprio (SQLite, fora do banco Smart) — cruza com OS de produção
// pra autopreencher paciente/valor/setor/convênio ao lançar uma guia.

import { useState, useEffect, useCallback, useRef } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

const API = `${window.location.protocol}//${window.location.host}`;

const C = {
  primary: "#059669",
  text:    "#111827",
  sub:     "#6B7280",
  faint:   "#9CA3AF",
  border:  "#E5E7EB",
};

const RECEPCOES_FAT = {
  RDI: "Recepção Diagnóstico",
  ROC: "Recepção Ocupacional",
  RCN: "Recepção Consultórios",
  RCI: "Recepção Censo Imagem",
};

const STATUS_CFG = {
  Pendente:  { cor: "#D97706", bg: "#FFFBEB" },
  Entregue:  { cor: "#2563EB", bg: "#EFF6FF" },
  Cancelada: { cor: "#DC2626", bg: "#FEF2F2" },
};
const STATUS_LISTA = ["Pendente", "Entregue", "Cancelada"];

const brl = v => v != null
  ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(v)
  : "—";
const dataBr = d => d ? d.split("-").reverse().join("/") : "—";

function Badge({ status }) {
  const cfg = STATUS_CFG[status] || STATUS_CFG.Pendente;
  return (
    <span style={{
      display: "inline-block", padding: "3px 10px", borderRadius: 99,
      background: cfg.bg, color: cfg.cor, fontSize: 11, fontWeight: 800,
    }}>{status}</span>
  );
}

// ── Busca de OS na produção (Smart) pra autopreencher a guia ─────────────────
function CampoOS({ onEscolher }) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState(null);
  const [buscando, setBuscando] = useState(false);
  const [aberto, setAberto] = useState(false);
  const [rect, setRect] = useState(null);
  const [carregado, setCarregado] = useState(null); // os_label da última OS autopreenchida
  const boxRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!aberto || termo.trim().length < 3) { setResultados(null); return; }
    setBuscando(true);
    const t = setTimeout(() => {
      fetch(`${API}/api/faturamento/buscar-os?q=${encodeURIComponent(termo.trim())}`)
        .then(r => r.json())
        .then(d => {
          const lista = d.resultados || [];
          setBuscando(false);
          if (lista.length === 1) {
            // match único (ex: "126-39594") — carrega automaticamente, sem precisar clicar
            onEscolher(lista[0]);
            setCarregado(lista[0].os_label);
            setTermo("");
            setAberto(false);
            setResultados(null);
          } else {
            setResultados(lista);
          }
        })
        .catch(() => { setResultados([]); setBuscando(false); });
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
      <input ref={inputRef} type="text" value={termo}
        placeholder="Buscar pela nº da OS (ex: 39594 ou 126-39594)..."
        onFocus={abrir} onChange={e => { setTermo(e.target.value); setCarregado(null); abrir(); }}
        style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
      {carregado && !aberto && (
        <div style={{ fontSize: 11.5, color: C.primary, fontWeight: 700, marginTop: 5 }}>
          ✓ OS {carregado} encontrada — convênio, serviço e valor preenchidos
        </div>
      )}
      {aberto && rect && termo.trim().length >= 3 && (
        <div style={{
          position: "fixed", top: rect.top, left: rect.left, width: Math.max(rect.width, 360), zIndex: 2000,
          background: "#fff", borderRadius: 10, border: "1px solid #E2E8F0", boxShadow: "0 8px 24px rgba(0,0,0,.18)",
          maxHeight: 320, overflowY: "auto",
        }}>
          {buscando ? (
            <div style={{ padding: 14, fontSize: 12, color: "#94A3B8", textAlign: "center" }}>Buscando...</div>
          ) : (resultados || []).length === 0 ? (
            <div style={{ padding: 14, fontSize: 12, color: "#CBD5E1", textAlign: "center" }}>Nenhuma OS encontrada.</div>
          ) : resultados.map(r => (
            <div key={r.os_label} onClick={() => { onEscolher(r); setCarregado(r.os_label); setTermo(""); setAberto(false); }} style={{
              padding: "9px 14px", cursor: "pointer", borderBottom: "1px solid #F8FAFC",
            }}
              onMouseEnter={e => e.currentTarget.style.background = "#F0FDF4"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <span style={{ fontSize: 12.5, fontWeight: 700, color: "#334155" }}>{r.paciente}</span>
                <span style={{ fontSize: 11, fontWeight: 800, color: C.primary, whiteSpace: "nowrap" }}>OS {r.os_label}</span>
              </div>
              <div style={{ fontSize: 11, color: "#94A3B8", marginTop: 2 }}>
                {dataBr(r.data)} · {r.setor_nome} · {r.convenio || "particular"} · {brl(r.valor)}
              </div>
              {r.tipo_exame && (
                <div style={{ fontSize: 10.5, color: "#64748B", marginTop: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.tipo_exame}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Modal de criação/edição de guia ───────────────────────────────────────────
function ModalGuia({ guia, onClose, onSalvo }) {
  const hoje = new Date().toISOString().slice(0, 10);
  const editando = !!guia;
  const [form, setForm] = useState(() => guia ? {
    data: guia.data, paciente: guia.paciente, os_serie: guia.os_serie, os_num: guia.os_num,
    tipo_exame: guia.tipo_exame || "", valor: guia.valor != null ? String(guia.valor) : "",
    setor: guia.setor || "", convenio: guia.convenio || "", observacao: guia.observacao || "",
  } : {
    data: hoje, paciente: "", os_serie: null, os_num: null,
    tipo_exame: "", valor: "", setor: "", convenio: "", observacao: "",
  });
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  const [itensOS, setItensOS] = useState([]); // serviços da OS carregada — pra escolher só os pendentes

  const set = (campo, valor) => setForm(f => ({ ...f, [campo]: valor }));

  const round2 = v => Math.round((v || 0) * 100) / 100;

  const aplicarSelecao = (itens) => {
    const marcados = itens.filter(i => i.marcado);
    setForm(f => ({
      ...f,
      tipo_exame: marcados.map(i => i.nome).join(", "),
      valor: String(round2(marcados.reduce((s, i) => s + (i.valor || 0), 0))),
    }));
  };

  const toggleItemOS = (idx) => {
    setErro("");
    setItensOS(prev => {
      const novo = prev.map((it, i) => i === idx ? { ...it, marcado: !it.marcado } : it);
      aplicarSelecao(novo);
      return novo;
    });
  };

  const preencherPorOS = (r) => {
    const temVariosItens = (r.itens || []).length > 1;
    setForm(f => ({
      ...f,
      paciente: r.paciente || f.paciente,
      os_serie: r.os_serie, os_num: r.os_num,
      // com vários serviços, o usuário marca abaixo só os que estão
      // pendentes — com um único serviço não há ambiguidade, preenche direto
      tipo_exame: temVariosItens ? "" : (r.tipo_exame || f.tipo_exame),
      valor: temVariosItens ? "" : (r.valor != null ? String(r.valor) : f.valor),
      setor: r.setor || f.setor,
      convenio: r.convenio || f.convenio,
      data: r.data || f.data,
    }));
    const itens = (r.itens || []).map(it => ({ ...it, marcado: !temVariosItens }));
    setItensOS(itens);
  };

  const salvar = () => {
    if (!form.data || !form.paciente.trim()) {
      setErro("Preencha ao menos a data e o paciente.");
      return;
    }
    if (itensOS.length > 1 && !itensOS.some(i => i.marcado)) {
      setErro("Marque ao menos um serviço pendente na lista acima.");
      return;
    }
    setSalvando(true);
    setErro("");
    const url = editando ? `${API}/api/faturamento/guias/${guia.id}` : `${API}/api/faturamento/guias`;
    fetch(url, {
      method: editando ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...form,
        valor: form.valor ? Number(form.valor) : null,
        os_serie: form.os_serie || null,
        os_num: form.os_num || null,
      }),
    })
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then(() => { onSalvo(); onClose(); })
      .catch(() => { setErro("Não foi possível salvar a guia."); setSalvando(false); });
  };

  const campoStyle = { width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" };
  const labelStyle = { fontSize: 11.5, fontWeight: 700, color: C.sub, marginBottom: 5, display: "block" };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 3000,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
    }} onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: "#fff", borderRadius: 16, padding: 26, width: 560, maxWidth: "100%",
        maxHeight: "90vh", overflowY: "auto", boxShadow: "0 20px 60px rgba(0,0,0,.3)",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>{editando ? "Editar Guia" : "Nova Guia Pendente"}</div>
          <button onClick={onClose} style={{ border: "none", background: "none", fontSize: 20, color: C.faint, cursor: "pointer" }}>×</button>
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={labelStyle}>Buscar OS (opcional — autopreenche os campos)</label>
          <CampoOS onEscolher={preencherPorOS} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
          <div>
            <label style={labelStyle}>Data *</label>
            <input type="date" value={form.data} onChange={e => set("data", e.target.value)} style={campoStyle} />
          </div>
          <div>
            <label style={labelStyle}>OS (série-número)</label>
            <input type="text" value={form.os_serie ? `${form.os_serie}-${form.os_num}` : ""} readOnly
              placeholder="—" style={{ ...campoStyle, background: "#F8FAFC", color: C.sub }} />
          </div>
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={labelStyle}>Paciente *</label>
          <input type="text" value={form.paciente} onChange={e => set("paciente", e.target.value)} style={campoStyle} />
        </div>

        {itensOS.length > 1 && (() => {
          const marcados = itensOS.filter(i => i.marcado);
          const nenhumMarcado = marcados.length === 0;
          return (
            <div style={{
              marginBottom: 14, border: `2px solid ${nenhumMarcado ? "#F59E0B" : "#A7F3D0"}`,
              borderRadius: 10, padding: "12px 14px", background: nenhumMarcado ? "#FFFBEB" : "#F0FDF4",
            }}>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 16, lineHeight: "18px" }}>{nenhumMarcado ? "⚠️" : "☑️"}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 800, color: C.text }}>
                    Esta OS tem {itensOS.length} serviços — marque abaixo SÓ os que ainda estão pendentes
                  </div>
                  <div style={{ fontSize: 11.5, color: C.sub, marginTop: 2, lineHeight: 1.5 }}>
                    Se algum serviço desta OS já foi entregue ou faturado separadamente, deixe-o
                    <b> desmarcado</b>. Só o que ficar marcado aqui vai entrar nesta guia.
                  </div>
                </div>
              </div>

              <div style={{ display: "flex", gap: 8, marginBottom: 8 }}>
                <button type="button" onClick={() => { setErro(""); const novo = itensOS.map(it => ({ ...it, marcado: true })); setItensOS(novo); aplicarSelecao(novo); }}
                  style={{ fontSize: 11, fontWeight: 700, color: C.primary, background: "#fff", border: `1px solid ${C.primary}`, borderRadius: 6, padding: "3px 9px", cursor: "pointer" }}>
                  Marcar todos
                </button>
                <button type="button" onClick={() => { setErro(""); const novo = itensOS.map(it => ({ ...it, marcado: false })); setItensOS(novo); aplicarSelecao(novo); }}
                  style={{ fontSize: 11, fontWeight: 700, color: C.sub, background: "#fff", border: `1px solid ${C.border}`, borderRadius: 6, padding: "3px 9px", cursor: "pointer" }}>
                  Desmarcar todos
                </button>
              </div>

              <div style={{ background: "#fff", borderRadius: 8, border: `1px solid ${C.border}`, overflow: "hidden" }}>
                {itensOS.map((it, i) => (
                  <label key={i} style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "8px 10px",
                    fontSize: 12.5, cursor: "pointer",
                    background: it.marcado ? "#ECFDF5" : "#fff",
                    borderBottom: i < itensOS.length - 1 ? `1px solid ${C.border}` : "none",
                  }}>
                    <input type="checkbox" checked={it.marcado} onChange={() => toggleItemOS(i)}
                      style={{ width: 16, height: 16, accentColor: C.primary, cursor: "pointer", flexShrink: 0 }} />
                    <span style={{ flex: 1, fontWeight: it.marcado ? 700 : 500, color: it.marcado ? C.text : C.faint }}>{it.nome}</span>
                    <span style={{ fontWeight: 800, whiteSpace: "nowrap", color: it.marcado ? C.primary : C.faint }}>{brl(it.valor)}</span>
                  </label>
                ))}
              </div>

              <div style={{
                marginTop: 10, fontSize: 12.5, fontWeight: 800,
                color: nenhumMarcado ? "#B45309" : C.primary,
              }}>
                {nenhumMarcado
                  ? "Nenhum serviço marcado como pendente — selecione ao menos um acima."
                  : `${marcados.length} de ${itensOS.length} serviço${marcados.length !== 1 ? "s" : ""} marcado${marcados.length !== 1 ? "s" : ""} como pendente · Total: ${brl(marcados.reduce((s, i) => s + (i.valor || 0), 0))}`
                }
              </div>
            </div>
          );
        })()}

        <div style={{ marginBottom: 14 }}>
          <label style={labelStyle}>Tipo de Exame / Serviço</label>
          <input type="text" value={form.tipo_exame} onChange={e => set("tipo_exame", e.target.value)} style={campoStyle} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 14 }}>
          <div>
            <label style={labelStyle}>Valor (R$)</label>
            <input type="number" step="0.01" value={form.valor} onChange={e => set("valor", e.target.value)} style={campoStyle} />
          </div>
          <div>
            <label style={labelStyle}>Setor</label>
            <select value={form.setor} onChange={e => set("setor", e.target.value)} style={campoStyle}>
              <option value="">—</option>
              {Object.entries(RECEPCOES_FAT).map(([cod, nome]) => (
                <option key={cod} value={cod}>{nome}</option>
              ))}
            </select>
          </div>
        </div>

        <div style={{ marginBottom: 14 }}>
          <label style={labelStyle}>Convênio</label>
          <input type="text" value={form.convenio} onChange={e => set("convenio", e.target.value)} style={campoStyle} />
        </div>

        <div style={{ marginBottom: 18 }}>
          <label style={labelStyle}>Observação</label>
          <textarea value={form.observacao} onChange={e => set("observacao", e.target.value)} rows={2}
            style={{ ...campoStyle, resize: "vertical" }} />
        </div>

        {erro && <div style={{ color: "#DC2626", fontSize: 12.5, marginBottom: 12 }}>{erro}</div>}

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{
            padding: "10px 18px", borderRadius: 9, border: `1.5px solid ${C.border}`,
            background: "#fff", color: C.sub, fontWeight: 700, fontSize: 13, cursor: "pointer",
          }}>Cancelar</button>
          <button onClick={salvar} disabled={salvando} style={{
            padding: "10px 20px", borderRadius: 9, border: "none",
            background: C.primary, color: "#fff", fontWeight: 700, fontSize: 13,
            cursor: salvando ? "wait" : "pointer", opacity: salvando ? 0.7 : 1,
          }}>{salvando ? "Salvando..." : editando ? "Salvar Alterações" : "Salvar Guia"}</button>
        </div>
      </div>
    </div>
  );
}

// ── Hero fixo com o resumo de TODO o período (não muda com o filtro de mês) ──
function FaixaResumoGeral({ resumo }) {
  if (!resumo) return null;
  const pendente = resumo.por_status?.Pendente || { total: 0, valor_total: 0 };

  return (
    <div style={{
      position: "relative", overflow: "hidden", borderRadius: 18, marginBottom: 20,
      padding: "22px 26px",
      background: "linear-gradient(135deg, #7F1D1D 0%, #DC2626 60%, #EF4444 100%)",
      boxShadow: "0 8px 28px rgba(220,38,38,.28)",
    }}>
      {/* Ornamento decorativo */}
      <div style={{
        position: "absolute", top: -60, right: -60, width: 220, height: 220,
        borderRadius: "50%", background: "rgba(255,255,255,.08)", pointerEvents: "none",
      }}/>
      <div style={{
        position: "absolute", bottom: -80, right: 120, width: 160, height: 160,
        borderRadius: "50%", background: "rgba(255,255,255,.06)", pointerEvents: "none",
      }}/>

      <div style={{ position: "relative" }}>
        <div style={{
          fontSize: 11, fontWeight: 800, color: "rgba(255,255,255,.75)",
          textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 6,
        }}>⏳ Guias Pendentes · Todo o período</div>
        <div style={{ fontSize: 34, fontWeight: 900, color: "#fff", lineHeight: 1.1 }}>
          {brl(pendente.valor_total)}
        </div>
        <div style={{ fontSize: 13, color: "rgba(255,255,255,.8)", marginTop: 4, fontWeight: 500 }}>
          {pendente.total} guia{pendente.total !== 1 ? "s" : ""} pendente{pendente.total !== 1 ? "s" : ""}
        </div>
      </div>
    </div>
  );
}

// ── Cards de resumo ────────────────────────────────────────────────────────
function CardsResumo({ resumo }) {
  if (!resumo) return null;
  const ordem = ["Pendente", "Entregue", "Cancelada"];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 18 }}>
      {ordem.map(s => {
        const cfg = STATUS_CFG[s];
        const dados = resumo.por_status?.[s] || { total: 0, valor_total: 0 };
        return (
          <div key={s} style={{
            background: "#fff", borderRadius: 14, padding: "16px 18px",
            boxShadow: "0 1px 4px rgba(0,0,0,0.07)", borderLeft: `4px solid ${cfg.cor}`,
          }}>
            <div style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, textTransform: "uppercase", letterSpacing: ".03em" }}>{s}</div>
            <div style={{ fontSize: 24, fontWeight: 900, color: C.text, marginTop: 4 }}>{dados.total}</div>
            <div style={{ fontSize: 12, fontWeight: 700, color: cfg.cor, marginTop: 2 }}>{brl(dados.valor_total)}</div>
          </div>
        );
      })}
      {resumo.pendentes_30dias > 0 && (
        <div style={{
          background: "#FEF2F2", borderRadius: 14, padding: "16px 18px",
          boxShadow: "0 1px 4px rgba(0,0,0,0.07)", borderLeft: "4px solid #DC2626",
          display: "flex", flexDirection: "column", justifyContent: "center",
        }}>
          <div style={{ fontSize: 11.5, fontWeight: 700, color: "#DC2626" }}>⚠ Pendentes há 30+ dias</div>
          <div style={{ fontSize: 24, fontWeight: 900, color: "#DC2626", marginTop: 4 }}>{resumo.pendentes_30dias}</div>
        </div>
      )}
    </div>
  );
}

// ── Dashboards analíticos ─────────────────────────────────────────────────
const MESES_ABREV = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"];
const mesLabel = m => {
  const [a, mm] = m.split("-");
  return `${MESES_ABREV[Number(mm) - 1]}/${a.slice(2)}`;
};
const truncar = (v, n = 18) => v?.length > n ? v.slice(0, n) + "…" : v;

function CardChart({ titulo, alturaVazio, children, vazio }) {
  return (
    <div style={{ background: "#fff", borderRadius: 14, padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
      <div style={{ fontSize: 13, fontWeight: 800, color: C.text, marginBottom: 12 }}>{titulo}</div>
      {vazio ? (
        <div style={{ height: alturaVazio || 240, display: "flex", alignItems: "center", justifyContent: "center", color: C.faint, fontSize: 12.5 }}>
          Sem dados no período.
        </div>
      ) : children}
    </div>
  );
}

function DashboardsFaturamento({ dashboard }) {
  if (!dashboard) return (
    <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 13 }}>Carregando dashboards...</div>
  );

  const porMes = (dashboard.por_mes || []).map(m => ({ ...m, mesLabel: mesLabel(m.mes) }));
  const porConvenio = dashboard.por_convenio || [];
  const porSetor = dashboard.por_setor || [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(380px, 1fr))", gap: 16 }}>
      <div style={{ gridColumn: "1 / -1" }}>
        <CardChart titulo="📅 Pendências por mês (últimos 12 meses)" vazio={!porMes.length} alturaVazio={280}>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={porMes} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" vertical={false} />
              <XAxis dataKey="mesLabel" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={v => brl(v).replace(",00", "")} width={70} />
              <Tooltip formatter={(v, n) => [brl(v), n]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {STATUS_LISTA.map(s => (
                <Bar key={s} dataKey={s} name={s} stackId="a" fill={STATUS_CFG[s].cor} radius={s === "Cancelada" ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </CardChart>
      </div>

      <CardChart titulo="🏥 Pendentes por convênio (top 10)" vazio={!porConvenio.length}>
        <ResponsiveContainer width="100%" height={Math.max(220, porConvenio.length * 34)}>
          <BarChart data={porConvenio} layout="vertical" margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 10 }} tickFormatter={v => brl(v).replace(",00", "")} />
            <YAxis type="category" dataKey="convenio" width={130} tick={{ fontSize: 10 }} tickFormatter={v => truncar(v)} />
            <Tooltip formatter={v => [brl(v), "Pendente"]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Bar dataKey="valor_total" fill={STATUS_CFG.Pendente.cor} radius={[0, 4, 4, 0]} barSize={16} />
          </BarChart>
        </ResponsiveContainer>
      </CardChart>

      <CardChart titulo="🏢 Pendentes por setor" vazio={!porSetor.length}>
        <ResponsiveContainer width="100%" height={Math.max(220, porSetor.length * 40)}>
          <BarChart data={porSetor.map(s => ({ ...s, setorNome: RECEPCOES_FAT[s.setor] || s.setor }))}
            layout="vertical" margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" horizontal={false} />
            <XAxis type="number" tick={{ fontSize: 10 }} tickFormatter={v => brl(v).replace(",00", "")} />
            <YAxis type="category" dataKey="setorNome" width={130} tick={{ fontSize: 10 }} tickFormatter={v => truncar(v)} />
            <Tooltip formatter={v => [brl(v), "Pendente"]} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Bar dataKey="valor_total" fill={STATUS_CFG.Pendente.cor} radius={[0, 4, 4, 0]} barSize={16} />
          </BarChart>
        </ResponsiveContainer>
      </CardChart>
    </div>
  );
}

// ── Tabela de guias ────────────────────────────────────────────────────────
function TabelaGuias({ guias, onMudarStatus, onExcluir, onEditar }) {
  const hoje = new Date();
  const diasPendente = (data) => {
    const d = new Date(data + "T00:00:00");
    return Math.floor((hoje - d) / 86400000);
  };

  if (!guias.length) return (
    <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 13 }}>Nenhuma guia encontrada.</div>
  );

  // Larguras/offsets das 4 últimas colunas (Valor, Status, Dias, Ações), que
  // ficam fixas (sticky) à direita ao rolar a tabela horizontalmente.
  const W_ACOES  = 76, W_DIAS = 60, W_STATUS = 118, W_VALOR = 96;
  const R_ACOES  = 0;
  const R_DIAS   = R_ACOES + W_ACOES;
  const R_STATUS = R_DIAS + W_DIAS;
  const R_VALOR  = R_STATUS + W_STATUS;
  const stickyBase = { position: "sticky", background: "#fff", zIndex: 1 };

  return (
    <div style={{ overflow: "auto", border: `1px solid ${C.border}`, borderRadius: 10 }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
        <thead>
          <tr style={{ background: "#F8FAFC" }}>
            {["Data", "Paciente", "OS", "Tipo de Exame", "Setor", "Convênio"].map((h, i) => (
              <th key={i} style={{ padding: "10px 12px", textAlign: "left", fontWeight: 700, color: C.faint, fontSize: 10.5, textTransform: "uppercase", whiteSpace: "nowrap" }}>{h}</th>
            ))}
            <th style={{ ...stickyBase, right: R_VALOR, width: W_VALOR, padding: "10px 12px", textAlign: "center", fontWeight: 700, color: C.faint, fontSize: 10.5, textTransform: "uppercase", whiteSpace: "nowrap", background: "#F8FAFC", boxShadow: "-1px 0 0 " + C.border }}>Valor</th>
            <th style={{ ...stickyBase, right: R_STATUS, width: W_STATUS, padding: "10px 12px", textAlign: "center", fontWeight: 700, color: C.faint, fontSize: 10.5, textTransform: "uppercase", whiteSpace: "nowrap", background: "#F8FAFC" }}>Status</th>
            <th style={{ ...stickyBase, right: R_DIAS, width: W_DIAS, padding: "10px 12px", textAlign: "center", fontWeight: 700, color: C.faint, fontSize: 10.5, textTransform: "uppercase", whiteSpace: "nowrap", background: "#F8FAFC" }}>Dias</th>
            <th style={{ ...stickyBase, right: R_ACOES, width: W_ACOES, padding: "10px 12px", textAlign: "center", fontWeight: 700, color: C.faint, fontSize: 10.5, textTransform: "uppercase", whiteSpace: "nowrap", background: "#F8FAFC" }}></th>
          </tr>
        </thead>
        <tbody>
          {guias.map(g => (
            <tr key={g.id} style={{ borderTop: `1px solid ${C.border}` }}
              onMouseEnter={e => e.currentTarget.style.background = "#FAFAFA"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              <td style={{ padding: "9px 12px", whiteSpace: "nowrap", color: C.sub }}>{dataBr(g.data)}</td>
              <td style={{ padding: "9px 12px", fontWeight: 700, color: C.text, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{g.paciente}</td>
              <td style={{ padding: "9px 12px", color: C.sub, whiteSpace: "nowrap" }}>{g.os_serie ? `${g.os_serie}-${g.os_num}` : "—"}</td>
              <td style={{ padding: "9px 12px", color: C.sub, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={g.tipo_exame}>{g.tipo_exame || "—"}</td>
              <td style={{ padding: "9px 12px", color: C.sub, whiteSpace: "nowrap" }}>{RECEPCOES_FAT[g.setor] || g.setor || "—"}</td>
              <td style={{ padding: "9px 12px", color: C.sub, maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{g.convenio || "—"}</td>
              <td style={{ ...stickyBase, right: R_VALOR, width: W_VALOR, padding: "9px 12px", fontWeight: 700, color: C.text, whiteSpace: "nowrap", boxShadow: "-1px 0 0 " + C.border }}>{brl(g.valor)}</td>
              <td style={{ ...stickyBase, right: R_STATUS, width: W_STATUS, padding: "9px 12px", textAlign: "center" }}>
                <select value={g.status} onChange={e => onMudarStatus(g, e.target.value)}
                  style={{
                    border: "none", background: STATUS_CFG[g.status]?.bg, color: STATUS_CFG[g.status]?.cor,
                    fontWeight: 800, fontSize: 11, borderRadius: 99, padding: "4px 8px", cursor: "pointer",
                  }}>
                  {STATUS_LISTA.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </td>
              <td style={{ ...stickyBase, right: R_DIAS, width: W_DIAS, padding: "9px 12px", textAlign: "center", color: g.status === "Pendente" && diasPendente(g.data) > 30 ? "#DC2626" : C.faint, fontWeight: g.status === "Pendente" && diasPendente(g.data) > 30 ? 800 : 500 }}>
                {g.status === "Entregue" ? "—" : diasPendente(g.data)}
              </td>
              <td style={{ ...stickyBase, right: R_ACOES, width: W_ACOES, padding: "9px 12px", textAlign: "center", whiteSpace: "nowrap" }}>
                <button onClick={() => onEditar(g)} title="Editar" style={{
                  border: "none", background: "none", color: C.sub, cursor: "pointer", fontSize: 13, marginRight: 10,
                }}>✏️</button>
                <button onClick={() => onExcluir(g.id)} title="Excluir" style={{
                  border: "none", background: "none", color: "#DC2626", cursor: "pointer", fontSize: 13,
                }}>🗑</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Modal de motivo de cancelamento — obrigatório antes de marcar uma guia
// como Cancelada, pra sempre ficar registrado o porquê ────────────────────
function ModalMotivoCancelamento({ guia, onClose, onConfirmar }) {
  const [motivo, setMotivo] = useState("");
  const [salvando, setSalvando] = useState(false);
  const podeConfirmar = motivo.trim().length >= 3;

  const confirmar = () => {
    if (!podeConfirmar) return;
    setSalvando(true);
    onConfirmar(motivo.trim());
  };

  return (
    <div style={{
      position: "fixed", inset: 0, background: "rgba(15,23,42,0.45)", zIndex: 3100,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
    }} onMouseDown={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{
        background: "#fff", borderRadius: 16, padding: 26, width: 460, maxWidth: "100%",
        boxShadow: "0 20px 60px rgba(0,0,0,.3)",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: C.text }}>Cancelar guia</div>
          <button onClick={onClose} style={{ border: "none", background: "none", fontSize: 20, color: C.faint, cursor: "pointer" }}>×</button>
        </div>
        <div style={{ fontSize: 12.5, color: C.sub, marginBottom: 18 }}>
          {guia.paciente} · {dataBr(guia.data)}{guia.tipo_exame ? ` · ${guia.tipo_exame}` : ""}
        </div>

        <label style={{ fontSize: 11.5, fontWeight: 700, color: C.sub, marginBottom: 5, display: "block" }}>
          Motivo do cancelamento <span style={{ color: "#DC2626" }}>*</span>
        </label>
        <textarea
          value={motivo}
          onChange={e => setMotivo(e.target.value)}
          rows={3}
          autoFocus
          placeholder="Explique por que essa guia está sendo cancelada..."
          style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box", resize: "vertical" }}
        />
        <div style={{ fontSize: 11, color: C.faint, marginTop: 6, marginBottom: 18 }}>
          Fica registrado na observação da guia, junto com a data.
        </div>

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={{
            padding: "10px 18px", borderRadius: 9, border: `1.5px solid ${C.border}`,
            background: "#fff", color: C.sub, fontWeight: 700, fontSize: 13, cursor: "pointer",
          }}>Voltar</button>
          <button onClick={confirmar} disabled={!podeConfirmar || salvando} style={{
            padding: "10px 20px", borderRadius: 9, border: "none",
            background: "#DC2626", color: "#fff", fontWeight: 700, fontSize: 13,
            cursor: (!podeConfirmar || salvando) ? "not-allowed" : "pointer", opacity: (!podeConfirmar || salvando) ? 0.5 : 1,
          }}>{salvando ? "Cancelando..." : "Confirmar cancelamento"}</button>
        </div>
      </div>
    </div>
  );
}

const MESES = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho","Agosto","Setembro","Outubro","Novembro","Dezembro"];

// ── Módulo principal ──────────────────────────────────────────────────────
export default function Faturamento() {
  const hoje = new Date();
  const [guias, setGuias] = useState([]);
  const [resumo, setResumo] = useState(null);
  const [resumoGeral, setResumoGeral] = useState(null);
  const [loading, setLoading] = useState(true);
  const [filtroStatus, setFiltroStatus] = useState("");
  const [filtroSetor, setFiltroSetor] = useState("");
  const [busca, setBusca] = useState("");
  const [modalAberto, setModalAberto] = useState(false);
  const [guiaEditando, setGuiaEditando] = useState(null);
  const [usarMes, setUsarMes] = useState(true);
  const [ano, setAno] = useState(hoje.getFullYear());
  const [mes, setMes] = useState(hoje.getMonth() + 1);
  const [aba, setAba] = useState("lista"); // "lista" | "dashboards"
  const [dashboard, setDashboard] = useState(null);
  const [guiaCancelando, setGuiaCancelando] = useState(null); // guia aguardando motivo de cancelamento

  const carregar = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (filtroStatus) params.set("status", filtroStatus);
    if (filtroSetor) params.set("setor", filtroSetor);
    if (busca.trim()) params.set("q", busca.trim());
    if (usarMes) { params.set("ano", ano); params.set("mes", mes); }
    const paramsResumo = new URLSearchParams();
    if (usarMes) { paramsResumo.set("ano", ano); paramsResumo.set("mes", mes); }
    Promise.all([
      fetch(`${API}/api/faturamento/guias?${params}`).then(r => r.json()),
      fetch(`${API}/api/faturamento/resumo?${paramsResumo}`).then(r => r.json()),
    ]).then(([g, r]) => {
      setGuias(g.guias || []);
      setResumo(r);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [filtroStatus, filtroSetor, busca, usarMes, ano, mes]);

  useEffect(() => {
    const t = setTimeout(carregar, busca ? 300 : 0);
    return () => clearTimeout(t);
  }, [carregar]);

  // Resumo de TODO o período — busca uma única vez, fixo, independente do
  // filtro de mês selecionado acima (esse muda; este não).
  useEffect(() => {
    fetch(`${API}/api/faturamento/resumo`).then(r => r.json()).then(setResumoGeral).catch(() => {});
  }, []);

  // Dados dos dashboards — busca só quando a aba é aberta pela primeira vez.
  useEffect(() => {
    if (aba === "dashboards" && !dashboard) {
      fetch(`${API}/api/faturamento/dashboard`).then(r => r.json()).then(setDashboard).catch(() => {});
    }
  }, [aba, dashboard]);

  const mudarMes = (delta) => {
    let m = mes + delta, a = ano;
    if (m > 12) { m = 1; a++; } else if (m < 1) { m = 12; a--; }
    setMes(m); setAno(a);
  };
  const ehMesAtual = ano === hoje.getFullYear() && mes === hoje.getMonth() + 1;

  const aplicarStatus = (id, campos) => {
    setGuias(prev => prev.map(g => g.id === id ? { ...g, ...campos } : g));
    fetch(`${API}/api/faturamento/guias/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(campos),
    }).then(() => {
      const paramsResumo = new URLSearchParams();
      if (usarMes) { paramsResumo.set("ano", ano); paramsResumo.set("mes", mes); }
      fetch(`${API}/api/faturamento/resumo?${paramsResumo}`).then(r => r.json()).then(setResumo);
      fetch(`${API}/api/faturamento/resumo`).then(r => r.json()).then(setResumoGeral);
    }).catch(() => carregar());
  };

  // Cancelar exige motivo — abre modal em vez de aplicar direto; os demais
  // status seguem aplicando na hora, como antes.
  const mudarStatus = (guia, status) => {
    if (status === "Cancelada") { setGuiaCancelando(guia); return; }
    aplicarStatus(guia.id, { status });
  };

  const confirmarCancelamento = (motivo) => {
    const guia = guiaCancelando;
    const carimbo = `[Cancelado em ${dataBr(new Date().toISOString().slice(0, 10))}] ${motivo}`;
    const observacao = guia.observacao ? `${guia.observacao}\n${carimbo}` : carimbo;
    aplicarStatus(guia.id, { status: "Cancelada", observacao });
    setGuiaCancelando(null);
  };

  const excluir = (id) => {
    if (!window.confirm("Excluir esta guia?")) return;
    fetch(`${API}/api/faturamento/guias/${id}`, { method: "DELETE" })
      .then(carregar).catch(() => {});
  };

  const [imprimindo, setImprimindo] = useState(false);
  const imprimirGuias = async () => {
    setImprimindo(true);
    try {
      const params = new URLSearchParams();
      if (filtroStatus) params.set("status", filtroStatus);
      if (filtroSetor) params.set("setor", filtroSetor);
      if (busca.trim()) params.set("q", busca.trim());
      if (usarMes) { params.set("ano", ano); params.set("mes", mes); }
      const r = await fetch(`${API}/api/faturamento/guias/pdf?${params}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `Guias_${filtroStatus || "Todas"}.pdf`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (e) {
      alert("Erro ao gerar PDF: " + e.message);
    } finally {
      setImprimindo(false);
    }
  };

  return (
    <div style={{ padding: "0 4px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 800, color: C.text }}>💰 Faturamento — Guias Pendentes</div>
          <div style={{ fontSize: 12.5, color: C.sub, marginTop: 2 }}>Controle de guias e cruzamento com a produção</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {usarMes && (
              <>
                <button onClick={() => mudarMes(-1)} style={{
                  width: 28, height: 28, borderRadius: 8, border: `1px solid ${C.border}`, background: "#fff",
                  cursor: "pointer", fontSize: 13, color: C.sub,
                }}>‹</button>
                <div style={{
                  fontSize: 12.5, fontWeight: 700, color: C.text, minWidth: 118, textAlign: "center",
                  padding: "5px 10px", borderRadius: 8, background: "#F8FAFC",
                }}>{MESES[mes - 1]} {ano}{ehMesAtual && <span style={{ color: C.primary }}> ·</span>}</div>
                <button onClick={() => mudarMes(1)} disabled={ehMesAtual} style={{
                  width: 28, height: 28, borderRadius: 8, border: `1px solid ${C.border}`,
                  background: ehMesAtual ? "#F8FAFC" : "#fff",
                  cursor: ehMesAtual ? "not-allowed" : "pointer",
                  fontSize: 13, color: ehMesAtual ? "#D1D5DB" : C.sub,
                }}>›</button>
              </>
            )}
            <button onClick={() => setUsarMes(u => !u)} style={{
              padding: "7px 14px", borderRadius: 8, fontSize: 11.5, fontWeight: 700,
              border: `1.5px solid ${!usarMes ? C.primary : C.border}`,
              background: !usarMes ? C.primary : "#fff",
              color: !usarMes ? "#fff" : C.sub, cursor: "pointer", whiteSpace: "nowrap",
            }}>Todo o período</button>
          </div>
          <button onClick={() => setAba(a => a === "lista" ? "dashboards" : "lista")} style={{
            padding: "10px 18px", borderRadius: 9, fontWeight: 700, fontSize: 13, cursor: "pointer",
            border: `1.5px solid ${aba === "dashboards" ? C.primary : C.border}`,
            background: aba === "dashboards" ? C.primary : "#fff",
            color: aba === "dashboards" ? "#fff" : C.sub,
          }}>📊 Dashboards</button>
          <button onClick={() => setModalAberto(true)} style={{
            padding: "10px 18px", borderRadius: 9, border: "none",
            background: C.primary, color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer",
          }}>+ Nova Guia</button>
        </div>
      </div>

      <FaixaResumoGeral resumo={resumoGeral} />

      {aba === "dashboards" ? (
        <DashboardsFaturamento dashboard={dashboard} />
      ) : (
        <>
          <CardsResumo resumo={resumo} />

          <div style={{ background: "#fff", borderRadius: 14, padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,0.07)" }}>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 14 }}>
              <input
                value={busca}
                onChange={e => setBusca(e.target.value)}
                placeholder="Buscar paciente ou exame..."
                style={{ flex: "1 1 220px", minWidth: 180, padding: "8px 12px", borderRadius: 8, border: `1px solid ${C.border}`, fontSize: 12.5, outline: "none", background: "#F8FAFC" }}
              />
              <select value={filtroSetor} onChange={e => setFiltroSetor(e.target.value)}
                style={{ padding: "8px 12px", borderRadius: 8, border: `1px solid ${C.border}`, fontSize: 12.5, background: "#fff" }}>
                <option value="">Todos os setores</option>
                {Object.entries(RECEPCOES_FAT).map(([cod, nome]) => (
                  <option key={cod} value={cod}>{nome}</option>
                ))}
              </select>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                <button onClick={() => setFiltroStatus("")} style={{
                  padding: "7px 14px", borderRadius: 99, fontSize: 11.5, fontWeight: 700,
                  border: `1.5px solid ${filtroStatus === "" ? C.primary : C.border}`,
                  background: filtroStatus === "" ? C.primary : "#fff",
                  color: filtroStatus === "" ? "#fff" : C.sub, cursor: "pointer",
                }}>Todas</button>
                {STATUS_LISTA.map(s => {
                  const active = filtroStatus === s;
                  const cor = STATUS_CFG[s].cor;
                  return (
                    <button key={s} onClick={() => setFiltroStatus(s)} style={{
                      padding: "7px 14px", borderRadius: 99, fontSize: 11.5, fontWeight: 700,
                      border: `1.5px solid ${active ? cor : C.border}`,
                      background: active ? cor : "#fff",
                      color: active ? "#fff" : C.sub, cursor: "pointer",
                    }}>{s}</button>
                  );
                })}
              </div>
              <button onClick={imprimirGuias} disabled={imprimindo || !guias.length} style={{
                padding: "7px 14px", borderRadius: 8, fontSize: 11.5, fontWeight: 700,
                border: `1.5px solid ${C.primary}`, background: "#fff", color: C.primary,
                cursor: guias.length ? "pointer" : "not-allowed", opacity: guias.length ? 1 : 0.5,
                whiteSpace: "nowrap",
              }}>{imprimindo ? "Gerando..." : "🖨️ Imprimir"}</button>
            </div>

            {loading ? (
              <div style={{ padding: 40, textAlign: "center", color: C.faint, fontSize: 13 }}>Carregando...</div>
            ) : (
              <>
                <div style={{ fontSize: 11, color: C.faint, marginBottom: 8 }}>{guias.length} guia{guias.length !== 1 ? "s" : ""}</div>
                <TabelaGuias guias={guias} onMudarStatus={mudarStatus} onExcluir={excluir} onEditar={setGuiaEditando} />
              </>
            )}
          </div>
        </>
      )}

      {modalAberto && (
        <ModalGuia onClose={() => setModalAberto(false)} onSalvo={carregar} />
      )}
      {guiaEditando && (
        <ModalGuia guia={guiaEditando} onClose={() => setGuiaEditando(null)} onSalvo={carregar} />
      )}
      {guiaCancelando && (
        <ModalMotivoCancelamento
          guia={guiaCancelando}
          onClose={() => setGuiaCancelando(null)}
          onConfirmar={confirmarCancelamento}
        />
      )}
    </div>
  );
}
