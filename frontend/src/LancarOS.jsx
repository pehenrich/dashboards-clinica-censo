import { useState, useEffect, useRef, useCallback } from "react";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;
const COR = "#4F46E5";
const COR2 = "#7C3AED";

const SETORES = [
  { id: "RDI", label: "Diagnóstico",  desc: "Laboratório e exames de imagem" },
  { id: "RCN", label: "Consultórios", desc: "Consultas e pequenos procedimentos" },
  { id: "ROC", label: "Ocupacional",  desc: "ASO — admissional, periódico, demissional..." },
  { id: "RCI", label: "Censo Imagem", desc: "Unidade de imagem" },
];

const TIPOS_ATENDIMENTO_OCUP = [
  { id: "ADM", label: "Admissional" },
  { id: "PER", label: "Periódico" },
  { id: "DEM", label: "Demissional" },
  { id: "MDF", label: "Mudança de função" },
  { id: "RTB", label: "Retorno ao trabalho" },
  { id: "MOC", label: "Monitoração" },
];

const SETORES_EXECUCAO = ["LAB", "RAD", "USG", "CAR", "OFT", "FON", "GIN", "NUT", "PSI", "END", "ORT", "DER", "PED", "NEU", "PNE", "CSM"];

function brl(v) {
  return (v ?? 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function iniciais(nome) {
  if (!nome) return "?";
  const partes = nome.trim().split(/\s+/);
  return ((partes[0]?.[0] || "") + (partes[1]?.[0] || "")).toUpperCase();
}

function idade(nascimentoISO) {
  if (!nascimentoISO) return null;
  const nasc = new Date(nascimentoISO);
  if (isNaN(nasc)) return null;
  const hoje = new Date();
  let anos = hoje.getFullYear() - nasc.getFullYear();
  const m = hoje.getMonth() - nasc.getMonth();
  if (m < 0 || (m === 0 && hoje.getDate() < nasc.getDate())) anos--;
  return anos >= 0 ? anos : null;
}

const Card = ({ children, style }) => (
  <div style={{
    background: "#fff", borderRadius: 18,
    boxShadow: "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
    overflow: "visible", ...style,
  }}>
    {children}
  </div>
);

const Rotulo = ({ children, obrigatorio }) => (
  <label style={{ display: "block", fontSize: 12, fontWeight: 800, color: "#334155", marginBottom: 7, textTransform: "uppercase", letterSpacing: ".03em" }}>
    {children}{obrigatorio && <span style={{ color: COR, marginLeft: 3 }}>*</span>}
  </label>
);

// ── Campo de busca genérico (autocomplete com dropdown flutuante) ───────────
function CampoBusca({ placeholder, buscar, renderItem, onEscolher, minLen = 2, disabled, valorFixo, chaveItem }) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState(null);
  const [aberto, setAberto] = useState(false);
  const [buscando, setBuscando] = useState(false);
  const [rect, setRect] = useState(null);
  const boxRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!aberto || termo.trim().length < minLen) { setResultados(null); return; }
    setBuscando(true);
    const t = setTimeout(() => {
      buscar(termo.trim())
        .then(r => { setResultados(r); setBuscando(false); })
        .catch(() => { setResultados([]); setBuscando(false); });
    }, 280);
    return () => clearTimeout(t);
  }, [termo, aberto]);

  useEffect(() => {
    const fechar = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setAberto(false); };
    document.addEventListener("mousedown", fechar);
    return () => document.removeEventListener("mousedown", fechar);
  }, []);

  const abrir = () => {
    if (disabled) return;
    if (inputRef.current) {
      const r = inputRef.current.getBoundingClientRect();
      setRect({ top: r.bottom + 4, left: r.left, width: r.width });
    }
    setAberto(true);
  };

  const escolher = (item) => {
    onEscolher(item);
    setTermo("");
    setAberto(false);
    setResultados(null);
    inputRef.current?.focus();
  };

  if (valorFixo) {
    return (
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
        padding: "10px 14px", borderRadius: 10, border: `1.5px solid ${COR}30`, background: `${COR}08`,
      }}>
        <div style={{ minWidth: 0 }}>{valorFixo}</div>
        <button type="button" onClick={() => onEscolher(null)} style={{
          border: "none", background: "transparent", color: "#94A3B8", cursor: "pointer", fontSize: 13, flexShrink: 0, fontWeight: 700,
        }}>trocar</button>
      </div>
    );
  }

  return (
    <div ref={boxRef} style={{ position: "relative" }}>
      <input ref={inputRef} type="text" value={termo} placeholder={placeholder} disabled={disabled}
        onFocus={abrir} onChange={e => { setTermo(e.target.value); abrir(); }}
        style={{
          width: "100%", padding: "11px 14px", borderRadius: 10, boxSizing: "border-box",
          border: "1.5px solid #E2E8F0", fontSize: 13.5, outline: "none",
          background: disabled ? "#F8FAFC" : "#fff", color: disabled ? "#CBD5E1" : "#0F172A",
        }}
        onFocusCapture={e => { if (!disabled) e.target.style.borderColor = COR; }}
        onBlurCapture={e => e.target.style.borderColor = "#E2E8F0"} />
      {aberto && rect && (buscando || resultados !== null) && (
        <div style={{
          position: "fixed", top: rect.top, left: rect.left, width: rect.width, zIndex: 3000,
          background: "#fff", borderRadius: 12, border: "1px solid #E2E8F0",
          boxShadow: "0 12px 32px rgba(15,23,42,.16)", maxHeight: 300, overflowY: "auto",
        }}>
          {buscando ? (
            <div style={{ padding: 16, fontSize: 12.5, color: "#94A3B8", textAlign: "center" }}>Buscando…</div>
          ) : resultados.length === 0 ? (
            <div style={{ padding: 16, fontSize: 12.5, color: "#CBD5E1", textAlign: "center" }}>Nada encontrado.</div>
          ) : resultados.map((r, i) => (
            <div key={chaveItem ? chaveItem(r) : i} onClick={() => escolher(r)} style={{
              padding: "10px 14px", cursor: "pointer", borderBottom: "1px solid #F8FAFC",
            }}
              onMouseEnter={e => e.currentTarget.style.background = "#EEF2FF"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              {renderItem(r)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Cabeçalho ────────────────────────────────────────────────────────────────
function Cabecalho({ totalItens, valorTotal }) {
  return (
    <div style={{
      background: `linear-gradient(135deg, ${COR} 0%, ${COR2} 100%)`,
      borderRadius: 20, padding: "24px 30px", marginBottom: 18,
      boxShadow: `0 8px 32px ${COR}40`, position: "relative", overflow: "hidden",
    }}>
      <div style={{ position: "absolute", right: -30, top: -30, width: 200, height: 200, borderRadius: "50%", background: "rgba(255,255,255,0.08)" }} />
      <div style={{ position: "relative", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16 }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 900, color: "#fff", letterSpacing: "-0.3px", marginBottom: 4 }}>⚡ Lançar OS</div>
          <div style={{ fontSize: 13, color: "rgba(255,255,255,0.78)", fontWeight: 500 }}>
            Abre uma Ordem de Serviço sem passar pelo Smart desktop — pensado pra ser rápido
          </div>
        </div>
        {totalItens > 0 && (
          <div style={{ background: "rgba(255,255,255,0.15)", borderRadius: 14, padding: "12px 20px", backdropFilter: "blur(4px)", textAlign: "right" }}>
            <div style={{ fontSize: 10, color: "rgba(255,255,255,0.8)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em" }}>
              {totalItens} {totalItens === 1 ? "item" : "itens"}
            </div>
            <div style={{ fontSize: 22, fontWeight: 900, color: "#fff" }}>{brl(valorTotal)}</div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Componente principal ─────────────────────────────────────────────────────
export default function LancarOS() {
  const { user } = useAuth();
  const login = user?.login || "";

  const [setor, setSetor] = useState(null);
  const [paciente, setPaciente] = useState(null);
  const [convenio, setConvenio] = useState(null);
  const [medicoReq, setMedicoReq] = useState(null);
  const [mesmoMedico, setMesmoMedico] = useState(true);
  const [medicoExec, setMedicoExec] = useState(null);
  const [tipoAtendimento, setTipoAtendimento] = useState("PER");
  const [urgente, setUrgente] = useState(false);
  const [adicionarFila, setAdicionarFila] = useState(true);
  const [tussCopiado, setTussCopiado] = useState(null);
  const [itens, setItens] = useState([]);
  const [tissTipoAtende, setTissTipoAtende] = useState("");
  const [regimeAtend, setRegimeAtend] = useState("");
  const [observacao, setObservacao] = useState("");

  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);
  const [resultado, setResultado] = useState(null);

  const [filasSenha, setFilasSenha] = useState([]);
  const [filaEscolhida, setFilaEscolhida] = useState("");
  const [filaPreferencial, setFilaPreferencial] = useState(false);
  const [filaEnviando, setFilaEnviando] = useState(false);
  const [filaErro, setFilaErro] = useState(null);
  const [filaResultado, setFilaResultado] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/painel-fila/prestadores`).then(r => r.json()).then(setFilasSenha).catch(() => setFilasSenha([]));
  }, []);

  const buscarPaciente = useCallback((q) =>
    fetch(`${API}/api/atendimento/buscar-paciente?q=${encodeURIComponent(q)}`).then(r => r.json()).then(d => d.pacientes || []), []);
  const buscarConvenio = useCallback((q) =>
    fetch(`${API}/api/atendimento/buscar-convenio?q=${encodeURIComponent(q)}`).then(r => r.json()).then(d => d.resultados || []), []);
  const buscarMedico = useCallback((q) =>
    fetch(`${API}/api/faturamento/buscar-medico?q=${encodeURIComponent(q)}`).then(r => r.json()).then(d => d.resultados || []), []);
  const buscarItem = useCallback((q) => {
    const params = new URLSearchParams({ q });
    if (convenio?.codigo) params.set("convenio", convenio.codigo);
    return fetch(`${API}/api/faturamento/buscar-item-os?${params}`).then(r => r.json()).then(d => d.resultados || []);
  }, [convenio]);

  const exigeTiss = convenio?.tiss === "S";
  const valorTotal = itens.reduce((s, it) => s + (it.preco || 0) * (it.qt || 1), 0);

  const adicionarItem = (r) => {
    setItens(prev => [...prev, {
      chave: `${r.tipo}-${r.codigo}-${prev.length}`,
      tipo: r.tipo, cod: r.codigo, nome: r.nome, qt: 1,
      setor_execucao: "LAB", preco: r.preco, tuss: r.tuss || "",
    }]);
    // Exames de sangue (setor de execução LAB, o padrão ao adicionar item) são
    // sempre coletados pela Jessica Oliveira Ferreira (biomédica, psv_cod 9126)
    // — pré-seleciona como executante, mas continua editável.
    setMesmoMedico(false);
    setMedicoExec(prev => prev || { codigo: 9126, nome: "Jessica Oliveira Ferreira" });
  };
  const copiarTuss = (tuss, chave) => {
    navigator.clipboard?.writeText(tuss);
    setTussCopiado(chave);
    setTimeout(() => setTussCopiado(c => c === chave ? null : c), 1500);
  };
  const removerItem = (chave) => setItens(prev => prev.filter(i => i.chave !== chave));
  const atualizarItem = (chave, campo, valor) => setItens(prev => prev.map(i => i.chave === chave ? { ...i, [campo]: valor } : i));

  const resetarParaProximaOS = () => {
    setPaciente(null); setItens([]); setObservacao(""); setResultado(null); setErro(null);
    // mantém setor, convênio e médicos — comum lançar várias OS seguidas no mesmo contexto
  };

  const podeEnviar = setor && paciente && convenio && medicoReq && (mesmoMedico || medicoExec) && itens.length > 0 && !enviando;

  const podeAdicionarNaFila = setor && paciente && filaEscolhida && !filaEnviando;

  const adicionarNaFilaSenha = async () => {
    if (!podeAdicionarNaFila) return;
    setFilaEnviando(true); setFilaErro(null); setFilaResultado(null);
    try {
      const resp = await fetch(`${API}/api/faturamento/adicionar-fila-senha-teste`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          paciente: paciente.pac_reg, setor, fila_psv_cod: Number(filaEscolhida),
          login, preferencial: filaPreferencial,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        let msg = "Erro ao adicionar na fila.";
        if (typeof data.detail === "string") msg = data.detail;
        else if (Array.isArray(data.detail)) msg = data.detail.map(d => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join(" · ");
        throw new Error(msg);
      }
      setFilaResultado(data);
    } catch (e) {
      setFilaErro(String(e.message || e));
    } finally {
      setFilaEnviando(false);
    }
  };

  const enviar = async () => {
    if (!podeEnviar) return;
    setEnviando(true); setErro(null); setResultado(null);
    try {
      const body = {
        paciente: paciente.pac_reg,
        convenio: convenio.codigo,
        setor,
        medico_requisitante: medicoReq.codigo,
        medico_executante: (mesmoMedico ? medicoReq : medicoExec)?.codigo,
        login,
        itens: itens.map(i => ({ tipo: i.tipo, cod: i.cod, qt: Number(i.qt) || 1, setor_execucao: i.setor_execucao })),
        tipo_atendimento: setor === "ROC" ? tipoAtendimento : "ASS",
        urgente,
        tiss_tipo_atende: tissTipoAtende || null,
        regime_atend: regimeAtend || null,
        observacao: observacao || null,
        adicionar_fila: adicionarFila,
      };
      const resp = await fetch(`${API}/api/faturamento/lancar-os-teste`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const data = await resp.json();
      if (!resp.ok) {
        let msg = "Erro ao lançar OS.";
        if (typeof data.detail === "string") msg = data.detail;
        else if (Array.isArray(data.detail)) {
          msg = data.detail.map(d => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join(" · ");
        }
        throw new Error(msg);
      }
      setResultado(data);
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div style={{ maxWidth: 980, margin: "0 auto" }}>
      <Cabecalho totalItens={itens.length} valorTotal={valorTotal} />

      <div style={{
        display: "flex", alignItems: "center", gap: 10, fontSize: 12.5, color: "#92650A",
        background: "#FFF7E6", border: "1px solid #F5C542", borderRadius: 12, padding: "11px 16px", marginBottom: 18,
      }}>
        <span style={{ fontSize: 16 }}>🧪</span>
        <span><b>Ambiente de teste</b> — esta tela grava em <code>smart_hml</code> (homologação), nunca em produção. Serve pra validar o fluxo antes de decidir sobre liberar de vez.</span>
      </div>

      {/* Setor */}
      <Card style={{ padding: 20, marginBottom: 16 }}>
        <Rotulo obrigatorio>Setor de recepção</Rotulo>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 10 }}>
          {SETORES.map(s => (
            <button key={s.id} type="button" onClick={() => setSetor(s.id)} style={{
              textAlign: "left", padding: "12px 14px", borderRadius: 12, cursor: "pointer",
              border: setor === s.id ? `2px solid ${COR}` : "1.5px solid #E2E8F0",
              background: setor === s.id ? `${COR}0D` : "#fff",
            }}>
              <div style={{ fontSize: 13.5, fontWeight: 800, color: setor === s.id ? COR : "#0F172A" }}>{s.label}</div>
              <div style={{ fontSize: 11, color: "#94A3B8", marginTop: 2 }}>{s.desc}</div>
            </button>
          ))}
        </div>

        {setor === "ROC" && (
          <div style={{ marginTop: 16 }}>
            <Rotulo>Tipo de exame ocupacional</Rotulo>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {TIPOS_ATENDIMENTO_OCUP.map(t => (
                <button key={t.id} type="button" onClick={() => setTipoAtendimento(t.id)} style={{
                  padding: "7px 14px", borderRadius: 99, cursor: "pointer", fontSize: 12, fontWeight: 700,
                  border: tipoAtendimento === t.id ? `1.5px solid ${COR}` : "1.5px solid #E2E8F0",
                  background: tipoAtendimento === t.id ? `${COR}0D` : "#fff",
                  color: tipoAtendimento === t.id ? COR : "#64748B",
                }}>{t.label}</button>
              ))}
            </div>
          </div>
        )}
      </Card>

      {/* Paciente + Convênio */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <Card style={{ padding: 20 }}>
          <Rotulo obrigatorio>Paciente</Rotulo>
          <CampoBusca
            placeholder="Nome, nº de registro ou CPF..."
            buscar={buscarPaciente}
            chaveItem={p => p.pac_reg}
            onEscolher={setPaciente}
            valorFixo={paciente && (
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: "50%", background: `${COR}15`, color: COR,
                  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, fontWeight: 800, flexShrink: 0,
                }}>{iniciais(paciente.nome)}</div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{paciente.nome}</div>
                  <div style={{ fontSize: 11, color: "#94A3B8" }}>
                    reg. {paciente.pac_reg}{idade(paciente.nascimento) != null ? ` · ${idade(paciente.nascimento)} anos` : ""}
                  </div>
                </div>
              </div>
            )}
            renderItem={p => (
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{p.nome}</div>
                <div style={{ fontSize: 11, color: "#94A3B8" }}>
                  reg. {p.pac_reg}{idade(p.nascimento) != null ? ` · ${idade(p.nascimento)} anos` : ""}{p.cpf ? ` · CPF ${p.cpf}` : ""}
                </div>
              </div>
            )} />
        </Card>

        <Card style={{ padding: 20 }}>
          <Rotulo obrigatorio>Convênio</Rotulo>
          <CampoBusca
            placeholder="Nome ou código do convênio..."
            buscar={buscarConvenio}
            chaveItem={c => c.codigo}
            onEscolher={setConvenio}
            valorFixo={convenio && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{convenio.nome}</div>
                {exigeTiss && <span style={{ fontSize: 9, fontWeight: 800, color: "#059669", background: "#ECFDF5", padding: "2px 7px", borderRadius: 99 }}>TISS</span>}
              </div>
            )}
            renderItem={c => (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 700, color: "#334155" }}>{c.nome}</span>
                <span style={{ fontSize: 10, color: "#94A3B8" }}>({c.codigo})</span>
                {c.tiss === "S" && <span style={{ fontSize: 9, fontWeight: 800, color: "#059669", background: "#ECFDF5", padding: "1px 6px", borderRadius: 99 }}>TISS</span>}
              </div>
            )} />
        </Card>
      </div>

      {/* Fila de atendimento (senha) — independente da OS */}
      <Card style={{ padding: 20, marginBottom: 16 }}>
        <Rotulo>Fila de atendimento (senha de recepção)</Rotulo>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          <select value={filaEscolhida} onChange={e => setFilaEscolhida(e.target.value)} style={{
            flex: "1 1 260px", padding: "10px 12px", borderRadius: 10, border: "1.5px solid #E2E8F0",
            fontSize: 13, background: "#fff", color: filaEscolhida ? "#0F172A" : "#94A3B8",
          }}>
            <option value="">Selecione a fila do paciente...</option>
            {filasSenha.map(f => (
              <option key={f.psv_cod} value={f.psv_cod}>{f.psv_apel}{f.especialidade ? ` — ${f.especialidade}` : ""}</option>
            ))}
          </select>
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5, color: "#334155", cursor: "pointer" }}>
            <input type="checkbox" checked={filaPreferencial} onChange={e => setFilaPreferencial(e.target.checked)} />
            Preferencial
          </label>
          <button type="button" onClick={adicionarNaFilaSenha} disabled={!podeAdicionarNaFila} style={{
            padding: "10px 18px", borderRadius: 10, border: "none",
            background: podeAdicionarNaFila ? `linear-gradient(135deg,${COR},${COR2})` : "#CBD5E1",
            color: "#fff", fontWeight: 800, fontSize: 12.5, cursor: podeAdicionarNaFila ? "pointer" : "not-allowed", flexShrink: 0,
          }}>{filaEnviando ? "Adicionando..." : "+ Adicionar na fila"}</button>
        </div>
        {!paciente && <div style={{ fontSize: 11, color: "#94A3B8", marginTop: 8 }}>Escolha o setor e o paciente pra habilitar.</div>}
        {filaErro && (
          <div style={{ marginTop: 10, fontSize: 12.5, color: "#DC2626", background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, padding: "8px 12px" }}>
            ⚠ {filaErro}
          </div>
        )}
        {filaResultado && (
          <div style={{ marginTop: 10, fontSize: 13, color: "#059669", background: "#ECFDF5", border: "1px solid #A7F3D0", borderRadius: 8, padding: "10px 14px", display: "flex", alignItems: "center", gap: 10 }}>
            ✓ Senha <b>{filaResultado.senha}</b> gerada na fila "{filaResultado.fila}"
            <button type="button" onClick={() => navigator.clipboard?.writeText(filaResultado.senha)} title="Copiar senha" style={{
              border: "1px solid #A7F3D0", background: "#fff", color: "#059669", borderRadius: 6, padding: "2px 8px", fontSize: 11, fontWeight: 700, cursor: "pointer",
            }}>⧉ copiar</button>
          </div>
        )}
      </Card>

      {/* Médicos */}
      <Card style={{ padding: 20, marginBottom: 16 }}>
        <div style={{ display: "grid", gridTemplateColumns: mesmoMedico ? "1fr" : "1fr 1fr", gap: 16 }}>
          <div>
            <Rotulo obrigatorio>Médico requisitante</Rotulo>
            <CampoBusca
              placeholder="Nome do médico..."
              buscar={buscarMedico}
              chaveItem={m => m.codigo}
              onEscolher={setMedicoReq}
              valorFixo={medicoReq && <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{medicoReq.nome}</div>}
              renderItem={m => <div style={{ fontSize: 13, fontWeight: 700, color: "#334155" }}>{m.nome}</div>} />
          </div>
          {!mesmoMedico && (
            <div>
              <Rotulo obrigatorio>Médico executante</Rotulo>
              <CampoBusca
                placeholder="Nome do médico..."
                buscar={buscarMedico}
                chaveItem={m => m.codigo}
                onEscolher={setMedicoExec}
                valorFixo={medicoExec && <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{medicoExec.nome}</div>}
                renderItem={m => <div style={{ fontSize: 13, fontWeight: 700, color: "#334155" }}>{m.nome}</div>} />
            </div>
          )}
        </div>
        <label style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 12.5, color: "#64748B", cursor: "pointer" }}>
          <input type="checkbox" checked={mesmoMedico} onChange={e => setMesmoMedico(e.target.checked)} />
          Mesmo médico requisitante e executante
        </label>
      </Card>

      {/* Itens */}
      <Card style={{ padding: 20, marginBottom: 16 }}>
        <Rotulo obrigatorio>Itens da OS</Rotulo>
        <CampoBusca
          placeholder={convenio ? "Buscar exame/procedimento — já mostra o preço da tabela do convênio..." : "Selecione o convênio pra ver o preço ao buscar..."}
          buscar={buscarItem}
          chaveItem={r => `${r.tipo}-${r.codigo}`}
          onEscolher={adicionarItem}
          renderItem={r => (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
              <div style={{ minWidth: 0 }}>
                <span style={{ fontSize: 11, fontWeight: 800, color: COR }}>{r.codigo}</span>
                {r.tuss && <span style={{ fontSize: 9.5, fontWeight: 800, color: "#7C3AED", background: "#7C3AED12", padding: "1px 6px", borderRadius: 99, marginLeft: 6 }}>TUSS {r.tuss}</span>}
                <span style={{ fontSize: 13, color: "#334155", marginLeft: 8 }}>{r.nome}</span>
              </div>
              <span style={{ fontSize: 12.5, fontWeight: 800, color: r.preco != null ? "#059669" : "#CBD5E1", flexShrink: 0 }}>
                {r.preco != null ? brl(r.preco) : "sem preço"}
              </span>
            </div>
          )} />

        {itens.length > 0 && (
          <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
            {itens.map(it => (
              <div key={it.chave} style={{
                display: "flex", alignItems: "center", gap: 10, background: "#FAFBFC",
                border: "1px solid #F1F5F9", borderRadius: 10, padding: "10px 12px", flexWrap: "wrap",
              }}>
                <div style={{ flex: "1 1 200px", minWidth: 0 }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: COR }}>{it.cod}</span>
                  <span style={{ fontSize: 12.5, color: "#334155", marginLeft: 8 }}>{it.nome}</span>
                </div>
                {it.tuss ? (
                  <button type="button" onClick={() => copiarTuss(it.tuss, it.chave)} title="Copiar código TUSS" style={{
                    fontSize: 10.5, fontWeight: 800, color: "#7C3AED", background: "#7C3AED12",
                    border: "1px solid #7C3AED30", borderRadius: 6, padding: "4px 8px", cursor: "pointer", flexShrink: 0,
                  }}>
                    TUSS {it.tuss} {tussCopiado === it.chave ? "✓" : "⧉"}
                  </button>
                ) : (
                  <span style={{ fontSize: 10, color: "#CBD5E1", flexShrink: 0 }}>sem TUSS</span>
                )}
                <input type="number" min="1" value={it.qt} onChange={e => atualizarItem(it.chave, "qt", e.target.value)}
                  title="Quantidade"
                  style={{ width: 50, padding: "6px 6px", borderRadius: 6, border: "1px solid #E2E8F0", fontSize: 12, textAlign: "center" }} />
                <input list="setores-execucao" value={it.setor_execucao} onChange={e => atualizarItem(it.chave, "setor_execucao", e.target.value.toUpperCase())}
                  title="Setor de execução"
                  style={{ width: 60, padding: "6px 6px", borderRadius: 6, border: "1px solid #E2E8F0", fontSize: 11, textAlign: "center", fontWeight: 700, color: "#64748B" }} />
                <span style={{ fontSize: 13, fontWeight: 800, color: it.preco != null ? "#059669" : "#D97706", width: 90, textAlign: "right" }}>
                  {it.preco != null ? brl(it.preco) : "sem preço"}
                </span>
                <button type="button" onClick={() => removerItem(it.chave)} style={{
                  width: 26, height: 26, borderRadius: 6, border: "1px solid #E2E8F0", background: "#fff", color: "#DC2626", cursor: "pointer", fontSize: 12, flexShrink: 0,
                }}>✕</button>
              </div>
            ))}
            <datalist id="setores-execucao">
              {SETORES_EXECUCAO.map(s => <option key={s} value={s} />)}
            </datalist>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, alignItems: "baseline", padding: "6px 4px 0" }}>
              <span style={{ fontSize: 12, color: "#94A3B8", fontWeight: 700, textTransform: "uppercase" }}>Total</span>
              <span style={{ fontSize: 18, fontWeight: 900, color: "#0F172A" }}>{brl(valorTotal)}</span>
            </div>
          </div>
        )}
      </Card>

      {/* TISS + urgência + observação */}
      <Card style={{ padding: 20, marginBottom: 16 }}>
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: exigeTiss ? 16 : 0 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#334155", cursor: "pointer" }}>
            <input type="checkbox" checked={urgente} onChange={e => setUrgente(e.target.checked)} />
            Urgente
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#334155", cursor: "pointer" }}>
            <input type="checkbox" checked={adicionarFila} onChange={e => setAdicionarFila(e.target.checked)} />
            Adicionar paciente à fila do médico executante (como no Smart desktop)
          </label>
        </div>

        {exigeTiss && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, padding: 14, background: "#F8FAFC", borderRadius: 12, border: "1px dashed #CBD5E1" }}>
            <div>
              <Rotulo>TISS — tipo de atendimento</Rotulo>
              <input type="text" value={tissTipoAtende} onChange={e => setTissTipoAtende(e.target.value)}
                placeholder="ex: 05 (exames), 04 (consulta)..."
                style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
              <div style={{ fontSize: 10.5, color: "#94A3B8", marginTop: 4 }}>Convênio exige TISS e não há valor padrão confiável — confira antes de lançar.</div>
            </div>
            <div>
              <Rotulo>TISS — regime de atendimento</Rotulo>
              <input type="text" value={regimeAtend} onChange={e => setRegimeAtend(e.target.value)}
                placeholder="ex: 01 (ambulatorial)..."
                style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
              <div style={{ fontSize: 10.5, color: "#94A3B8", marginTop: 4 }}>Só uma parte das OS desse tipo de convênio preenche — confirme se se aplica.</div>
            </div>
          </div>
        )}

        <div style={{ marginTop: 16 }}>
          <Rotulo>Observação (opcional)</Rotulo>
          <textarea rows={2} value={observacao} onChange={e => setObservacao(e.target.value)}
            style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, fontFamily: "inherit", resize: "vertical", boxSizing: "border-box" }} />
        </div>
      </Card>

      {erro && (
        <div style={{ background: "#FEF2F2", border: "1.5px solid #FECACA", color: "#DC2626", borderRadius: 12, padding: "14px 18px", fontSize: 13, marginBottom: 16 }}>
          ⚠ {erro}
        </div>
      )}

      {resultado && (
        <div style={{ background: "#ECFDF5", border: "1.5px solid #A7F3D0", borderRadius: 16, padding: "20px 24px", marginBottom: 16 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
            <div style={{ fontSize: 16, fontWeight: 900, color: "#059669" }}>✓ OS {resultado.os} lançada</div>
            <button type="button" onClick={resetarParaProximaOS} style={{
              padding: "8px 16px", borderRadius: 10, border: "none",
              background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: "pointer",
            }}>+ Lançar próxima OS</button>
          </div>
          <div style={{ fontSize: 12, color: "#065F46" }}>Tabela de preço usada: <b>{resultado.tabela_preco_usada}</b> · ambiente: <b>{resultado.ambiente}</b></div>
          {resultado.fila?.adicionado && (
            <div style={{ fontSize: 12, color: "#065F46", marginTop: 4 }}>
              ✓ Paciente adicionado à fila do médico (posição <b>{resultado.fila.ordem}</b>)
            </div>
          )}
          {resultado.avisos?.length > 0 && (
            <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 6 }}>
              {resultado.avisos.map((a, i) => (
                <div key={i} style={{ fontSize: 12, color: "#92650A", background: "#FFF7E6", border: "1px solid #F5C542", borderRadius: 8, padding: "8px 12px" }}>
                  ⚠ {a}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <button type="button" onClick={enviar} disabled={!podeEnviar} style={{
        width: "100%", padding: "16px 22px", borderRadius: 14, border: "none",
        background: podeEnviar ? `linear-gradient(135deg,${COR},${COR2})` : "#CBD5E1",
        color: "#fff", fontSize: 15, fontWeight: 800, cursor: podeEnviar ? "pointer" : "not-allowed",
        boxShadow: podeEnviar ? `0 8px 24px ${COR}40` : "none", marginBottom: 40,
      }}>
        {enviando ? "Lançando..." : `⚡ Lançar OS${itens.length ? ` — ${brl(valorTotal)}` : ""}`}
      </button>
    </div>
  );
}
