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
  { id: "57",  label: "CMI",          desc: "Recepção CMI" },
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

// Setores de execução com um único "dono" da fila na prática — confirmado com
// dado real de produção (ago-set/2026): LAB praticamente sempre Jessica
// Oliveira Ferreira (~96% dos casos), RAD praticamente sempre Maria de
// Nazaré Martins Leão (~99%). Outros setores (PSI, USG, CSM...) têm vários
// profissionais dividindo a fila, então não têm um padrão único confiável.
const EXECUTANTE_PADRAO_POR_SETOR = {
  LAB: { codigo: 9126, nome: "Jessica Oliveira Ferreira" },
  RAD: { codigo: 8541, nome: "Maria de Nazaré Martins Leão" },
};

// Recepção fica "fixa" por navegador — a recepcionista escolhe o setor uma vez e
// ele continua pré-selecionado em todas as próximas OS e depois de recarregar.
const SETOR_KEY = "lancaros_setor_fixo";
function carregarSetorFixo() {
  try { return localStorage.getItem(SETOR_KEY) || null; } catch { return null; }
}
function salvarSetorFixo(setor) {
  try { setor ? localStorage.setItem(SETOR_KEY, setor) : localStorage.removeItem(SETOR_KEY); } catch { /* ignore */ }
}

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
function CampoBusca({ placeholder, buscar, renderItem, onEscolher, minLen = 2, disabled, valorFixo, chaveItem, debounceMs = 280, autoFocus = false }) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState(null);
  const [aberto, setAberto] = useState(false);
  const [buscando, setBuscando] = useState(false);
  const [rect, setRect] = useState(null);
  const [destaque, setDestaque] = useState(0);
  const boxRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!aberto || termo.trim().length < minLen) { setResultados(null); return; }
    setBuscando(true);
    const t = setTimeout(() => {
      buscar(termo.trim())
        .then(r => { setResultados(r); setDestaque(0); setBuscando(false); })
        .catch(() => { setResultados([]); setBuscando(false); });
    }, debounceMs);
    return () => clearTimeout(t);
  }, [termo, aberto]);

  useEffect(() => { if (autoFocus && !valorFixo) inputRef.current?.focus(); }, [autoFocus, valorFixo]);

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
    setDestaque(0);
    inputRef.current?.focus();
  };

  // Teclado: ↓/↑ navega, Enter escolhe o item destacado (por padrão o 1º — então
  // digitar o código e dar Enter já adiciona sem precisar do mouse), Esc fecha.
  const aoTeclar = (e) => {
    if (!aberto || !resultados || resultados.length === 0) return;
    if (e.key === "ArrowDown") { e.preventDefault(); setDestaque(d => Math.min(d + 1, resultados.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setDestaque(d => Math.max(d - 1, 0)); }
    else if (e.key === "Enter") { e.preventDefault(); escolher(resultados[destaque] || resultados[0]); }
    else if (e.key === "Escape") { setAberto(false); }
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
        onFocus={abrir} onChange={e => { setTermo(e.target.value); abrir(); }} onKeyDown={aoTeclar}
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
            <div key={chaveItem ? chaveItem(r) : i} onClick={() => escolher(r)}
              onMouseEnter={() => setDestaque(i)} style={{
              padding: "10px 14px", cursor: "pointer", borderBottom: "1px solid #F8FAFC",
              background: i === destaque ? "#EEF2FF" : "transparent",
            }}>
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

  const [setor, setSetorState] = useState(() => carregarSetorFixo());
  // Troca de setor já persiste — vira a recepção fixa deste navegador.
  const setSetor = useCallback((s) => { setSetorState(s); salvarSetorFixo(s); }, []);
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
  const [osmWSenha, setOsmWSenha] = useState("");
  const [observacao, setObservacao] = useState("");

  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState(null);
  const [resultado, setResultado] = useState(null);

  const [modalFilaAberto, setModalFilaAberto] = useState(false);
  const [filaDestino, setFilaDestino] = useState(null);

  const FORM_PAC_VAZIO = { nome: "", nascimento: "", sexo: "", cpf: "", telefone: "" };
  const [modalPacienteAberto, setModalPacienteAberto] = useState(false);
  const [formPac, setFormPac] = useState(FORM_PAC_VAZIO);
  const [salvandoPac, setSalvandoPac] = useState(false);
  const [erroPac, setErroPac] = useState(null);

  const abrirCadastroPaciente = () => {
    setFormPac(FORM_PAC_VAZIO);
    setErroPac(null);
    setModalPacienteAberto(true);
  };

  const cadastrarPaciente = async () => {
    if (formPac.nome.trim().length < 3) { setErroPac("Informe o nome completo."); return; }
    setSalvandoPac(true); setErroPac(null);
    try {
      const resp = await fetch(`${API}/api/faturamento/cadastrar-paciente-teste`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nome: formPac.nome.trim(),
          nascimento: formPac.nascimento || null,
          sexo: formPac.sexo || null,
          cpf: formPac.cpf || null,
          telefone: formPac.telefone || null,
          convenio: convenio?.codigo || null,
          login,
        }),
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Erro ao cadastrar paciente.");
      setPaciente({ pac_reg: data.pac_reg, nome: data.nome, nascimento: data.nascimento, cpf: data.cpf });
      setModalPacienteAberto(false);
    } catch (e) {
      setErroPac(String(e.message || e));
    } finally {
      setSalvandoPac(false);
    }
  };

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

  // Pré-seleciona o executante padrão daquele setor de execução (LAB/RAD...),
  // quando existe um "dono" único e dominante na prática — continua editável.
  // Também pré-seleciona a mesma pessoa como fila padrão (é quem realmente
  // recebe o paciente na prática) — mas fila e executante são campos
  // independentes a partir daqui: trocar um não mexe no outro.
  const aplicarExecutantePadrao = (setorExec) => {
    const padrao = EXECUTANTE_PADRAO_POR_SETOR[setorExec];
    if (!padrao) return;
    setMesmoMedico(false);
    setMedicoExec(prev => prev || padrao);
    setFilaDestino(prev => prev || padrao);
  };

  // Escolher explicitamente pra qual fila mandar o paciente — campo
  // independente do médico executante (que fatura o serviço, SMM_MED, e
  // precisa ser sempre um profissional real). A fila pode ser uma "estação"
  // cadastrada como prestador (Coleta Diagnóstico, Radiologia Diagnóstica,
  // Vale, Particular etc.) sem relação com quem executa de fato. Não gera
  // senha — é só o mesmo mecanismo de "entra como último da fila".
  const escolherFila = (f) => {
    setFilaDestino(f);
    setModalFilaAberto(false);
  };

  const adicionarItem = (r) => {
    setItens(prev => [...prev, {
      chave: `${r.tipo}-${r.codigo}-${prev.length}`,
      tipo: r.tipo, cod: r.codigo, nome: r.nome, qt: 1,
      setor_execucao: "LAB", preco: r.preco, tuss: r.tuss || "",
    }]);
    aplicarExecutantePadrao("LAB");
  };
  const copiarTuss = (tuss, chave) => {
    navigator.clipboard?.writeText(tuss);
    setTussCopiado(chave);
    setTimeout(() => setTussCopiado(c => c === chave ? null : c), 1500);
  };
  const removerItem = (chave) => setItens(prev => prev.filter(i => i.chave !== chave));
  const atualizarItem = (chave, campo, valor) => {
    setItens(prev => prev.map(i => i.chave === chave ? { ...i, [campo]: valor } : i));
    if (campo === "setor_execucao") aplicarExecutantePadrao(valor.toUpperCase());
  };

  const resetarParaProximaOS = () => {
    setPaciente(null); setItens([]); setObservacao(""); setResultado(null); setErro(null);
    // mantém setor, convênio e médicos — comum lançar várias OS seguidas no mesmo contexto
  };

  const podeEnviar = setor && paciente && convenio && medicoReq && (mesmoMedico || medicoExec) && itens.length > 0 && !enviando;

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
        osm_w_senha: osmWSenha || null,
        observacao: observacao || null,
        adicionar_fila: adicionarFila,
        fila_destino_psv_cod: filaDestino?.codigo || null,
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
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 7 }}>
          <Rotulo obrigatorio>Setor de recepção</Rotulo>
          {setor && (
            <span style={{ fontSize: 10, fontWeight: 800, color: COR, background: `${COR}12`, padding: "2px 8px", borderRadius: 99, marginBottom: 7 }}>
              📌 fixada neste computador
            </span>
          )}
        </div>
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
          {!paciente && (
            <button type="button" onClick={abrirCadastroPaciente} style={{
              marginTop: 10, width: "100%", padding: "9px 14px", borderRadius: 10, cursor: "pointer",
              border: `1.5px dashed ${COR}50`, background: `${COR}06`, color: COR, fontWeight: 700, fontSize: 12.5,
            }}>+ Cadastrar novo paciente</button>
          )}
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
          placeholder={convenio ? "Buscar por código ou nome — Enter adiciona o 1º resultado..." : "Selecione o convênio pra ver o preço ao buscar..."}
          buscar={buscarItem}
          debounceMs={140}
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
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center", marginBottom: exigeTiss ? 16 : 0 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#334155", cursor: "pointer" }}>
            <input type="checkbox" checked={urgente} onChange={e => setUrgente(e.target.checked)} />
            Urgente
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#334155", cursor: "pointer" }}>
            <input type="checkbox" checked={adicionarFila} onChange={e => setAdicionarFila(e.target.checked)} />
            Adicionar paciente à fila{filaDestino ? " de:" : " do médico executante"} (como no Smart desktop)
          </label>
          {adicionarFila && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {filaDestino && (
                <span style={{ fontSize: 11.5, fontWeight: 800, color: COR, background: `${COR}12`, padding: "3px 10px", borderRadius: 99 }}>
                  {filaDestino.nome}
                </span>
              )}
              <button type="button" onClick={() => setModalFilaAberto(true)} style={{
                padding: "5px 10px", borderRadius: 8, border: `1.5px solid ${COR}30`, background: `${COR}08`,
                color: COR, fontWeight: 700, fontSize: 11.5, cursor: "pointer",
              }}>{filaDestino ? "trocar fila" : "🔀 Escolher fila específica..."}</button>
              {filaDestino && (
                <button type="button" onClick={() => setFilaDestino(null)} title="Voltar ao padrão (fila do médico executante)" style={{
                  border: "none", background: "transparent", color: "#94A3B8", fontWeight: 700, fontSize: 11, cursor: "pointer",
                }}>✕</button>
              )}
            </div>
          )}
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
            <div>
              <Rotulo>Senha de autorização (opcional)</Rotulo>
              <input type="text" value={osmWSenha} onChange={e => setOsmWSenha(e.target.value)}
                placeholder="senha da guia no convênio, se já autorizada..."
                style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
              <div style={{ fontSize: 10.5, color: "#94A3B8", marginTop: 4 }}>Maioria das OS TISS preenche (grava no primeiro item, como já é feito no Smart) — confira se o convênio já autorizou antes de lançar.</div>
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
              ✓ Paciente adicionado à fila de <b>{filaDestino?.nome || "médico executante"}</b> (posição <b>{resultado.fila.ordem}</b>)
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

      {modalFilaAberto && (
        <div onClick={() => setModalFilaAberto(false)} style={{
          position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 4000,
          display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: "#fff", borderRadius: 16, width: "100%", maxWidth: 440,
            boxShadow: "0 20px 60px rgba(0,0,0,.3)", padding: 20,
          }}>
            <div style={{ fontSize: 15, fontWeight: 800, color: "#0F172A", marginBottom: 4 }}>Mandar paciente pra qual fila?</div>
            <div style={{ fontSize: 11.5, color: "#94A3B8", marginBottom: 12 }}>
              Busca cobre médicos reais e estações cadastradas como prestador (Coleta Diagnóstico, Radiologia Diagnóstica, Vale, Particular...).
            </div>
            <CampoBusca
              placeholder="Nome da fila ou do médico..."
              buscar={buscarMedico}
              chaveItem={m => m.codigo}
              onEscolher={escolherFila}
              renderItem={m => (
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{m.nome}</div>
                  {m.apelido && m.apelido !== m.nome && <div style={{ fontSize: 11, color: "#94A3B8" }}>{m.apelido}</div>}
                </div>
              )} />
            <div style={{ marginTop: 14, textAlign: "right" }}>
              <button type="button" onClick={() => setModalFilaAberto(false)} style={{
                border: "none", background: "transparent", color: "#94A3B8", fontWeight: 700, fontSize: 12.5, cursor: "pointer",
              }}>Cancelar</button>
            </div>
          </div>
        </div>
      )}

      {modalPacienteAberto && (
        <div onClick={() => setModalPacienteAberto(false)} style={{
          position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 4000,
          display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: "#fff", borderRadius: 16, width: "100%", maxWidth: 460,
            boxShadow: "0 20px 60px rgba(0,0,0,.3)", padding: 22,
          }}>
            <div style={{ fontSize: 15, fontWeight: 800, color: "#0F172A", marginBottom: 4 }}>Cadastrar novo paciente</div>
            <div style={{ fontSize: 11.5, color: "#94A3B8", marginBottom: 16 }}>
              Grava em <code>smart_hml</code> (homologação), como o resto desta tela. Só o nome é obrigatório.
            </div>

            <div style={{ marginBottom: 12 }}>
              <Rotulo obrigatorio>Nome completo</Rotulo>
              <input type="text" value={formPac.nome} autoFocus
                onChange={e => setFormPac(f => ({ ...f, nome: e.target.value }))}
                onKeyDown={e => { if (e.key === "Enter") cadastrarPaciente(); }}
                style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
              <div>
                <Rotulo>Data de nascimento</Rotulo>
                <input type="date" value={formPac.nascimento}
                  onChange={e => setFormPac(f => ({ ...f, nascimento: e.target.value }))}
                  style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
              </div>
              <div>
                <Rotulo>Sexo</Rotulo>
                <div style={{ display: "flex", gap: 8 }}>
                  {["M", "F"].map(s => (
                    <button key={s} type="button" onClick={() => setFormPac(f => ({ ...f, sexo: f.sexo === s ? "" : s }))} style={{
                      flex: 1, padding: "9px 0", borderRadius: 8, cursor: "pointer", fontSize: 13, fontWeight: 700,
                      border: formPac.sexo === s ? `1.5px solid ${COR}` : "1.5px solid #E2E8F0",
                      background: formPac.sexo === s ? `${COR}0D` : "#fff", color: formPac.sexo === s ? COR : "#64748B",
                    }}>{s === "M" ? "Masculino" : "Feminino"}</button>
                  ))}
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 12 }}>
              <div>
                <Rotulo>CPF</Rotulo>
                <input type="text" inputMode="numeric" value={formPac.cpf} placeholder="só números"
                  onChange={e => setFormPac(f => ({ ...f, cpf: e.target.value }))}
                  style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
              </div>
              <div>
                <Rotulo>Telefone/celular</Rotulo>
                <input type="text" value={formPac.telefone}
                  onChange={e => setFormPac(f => ({ ...f, telefone: e.target.value }))}
                  style={{ width: "100%", padding: "10px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" }} />
              </div>
            </div>

            <div style={{ fontSize: 11, color: "#94A3B8", marginBottom: 14 }}>
              Convênio: <b>{convenio ? convenio.nome : "Particular Diag (padrão)"}</b>
              {" "}— pode trocar depois no campo Convênio da OS.
            </div>

            {erroPac && (
              <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#DC2626", borderRadius: 8, padding: "9px 12px", fontSize: 12, marginBottom: 12 }}>
                ⚠ {erroPac}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
              <button type="button" onClick={() => setModalPacienteAberto(false)} style={{
                border: "none", background: "transparent", color: "#94A3B8", fontWeight: 700, fontSize: 12.5, cursor: "pointer",
              }}>Cancelar</button>
              <button type="button" onClick={cadastrarPaciente} disabled={salvandoPac} style={{
                padding: "9px 18px", borderRadius: 10, border: "none",
                background: salvandoPac ? "#CBD5E1" : `linear-gradient(135deg,${COR},${COR2})`,
                color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: salvandoPac ? "not-allowed" : "pointer",
              }}>{salvandoPac ? "Salvando..." : "Cadastrar e usar"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
