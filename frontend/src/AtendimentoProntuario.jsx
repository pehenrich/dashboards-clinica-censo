import { useState, useEffect, useRef, useCallback } from "react";
import { abrirEImprimir, DocGuiaSadt, CSS_TIMBRADO, htmlTimbrado, CSS_RODAPE_CLINICA, htmlRodapeClinica } from "./Atendimento";
import BriefingCard from "./BriefingCard";

const API = `${window.location.protocol}//${window.location.host}`;
const COR = "#8B1A1A";

function imprimirAtestado(atestado, item, medicoInfo, clinica) {
  const hoje = new Date().toLocaleDateString("pt-BR");
  const medNome = medicoInfo ? `${medicoInfo.tratamento} ${medicoInfo.nome}`.trim() : "";
  const medCrm = medicoInfo ? `${medicoInfo.conselho} ${medicoInfo.crm}${medicoInfo.uf ? "/" + medicoInfo.uf : ""}` : "";
  const corpo = `Atesto para os devidos fins que o(a) paciente <b>${item.paciente}</b>`
    + (atestado.dias ? ` necessita de afastamento de suas atividades por <b>${atestado.dias} dia(s)</b>, a partir de ${atestado.data_inicio ? new Date(atestado.data_inicio + "T00:00:00").toLocaleDateString("pt-BR") : "hoje"}.` : ".")
    + (atestado.cid_cod ? ` CID: <b>${atestado.cid_cod}</b>.` : "")
    + (atestado.texto ? `<br/><br/>${atestado.texto}` : "");
  const html = `
    <html><head><title>ATESTADO MÉDICO</title>
    <style>
      body { font-family: 'DM Sans', Arial, sans-serif; padding: 40px 70px; color: #111; }
      ${CSS_TIMBRADO}
      ${CSS_RODAPE_CLINICA}
      h1 { text-align:center; font-size:16px; letter-spacing:2px; margin-bottom:50px; }
      .corpo { font-size:14px; line-height:2; text-align:justify; margin-bottom:80px; }
      .assinatura { text-align:center; margin-top:100px; }
      .linha { border-top:1px solid #111; width:320px; margin:0 auto 6px; }
      .data { text-align:right; margin-bottom:40px; font-size:13px; }
    </style></head>
    <body>
      ${htmlTimbrado()}
      <h1>ATESTADO MÉDICO</h1>
      <div class="data">Parauapebas, ${hoje}</div>
      <div class="corpo">${corpo}</div>
      <div class="assinatura"><div class="linha"></div>${medNome}<br/>${medCrm}</div>
      ${htmlRodapeClinica(clinica)}
    </body></html>`;
  abrirEImprimir(html, "ATESTADO MÉDICO");
}

function imprimirReceita(consulta, item, medicoInfo, clinica) {
  const hoje = new Date().toLocaleDateString("pt-BR");
  const medNome = medicoInfo ? `${medicoInfo.tratamento} ${medicoInfo.nome}`.trim() : "";
  const medCrm = medicoInfo ? `${medicoInfo.conselho} ${medicoInfo.crm}${medicoInfo.uf ? "/" + medicoInfo.uf : ""}` : "";
  const itens = (consulta.prescricoes || []).map((p, i) => `
    <div class="item">
      <div class="num">${i + 1}.</div>
      <div>
        <div class="med">${p.medicamento}${p.uso_continuo === "S" ? " <span class='uc'>(uso contínuo)</span>" : ""}</div>
        <div class="pos">${p.posologia || ""}${p.quantidade ? ` — ${p.quantidade}` : ""}</div>
      </div>
    </div>`).join("");
  const html = `
    <html><head><title>RECEITUÁRIO</title>
    <style>
      body { font-family: 'DM Sans', Arial, sans-serif; padding: 40px 70px; color: #111; }
      ${CSS_TIMBRADO}
      ${CSS_RODAPE_CLINICA}
      h1 { text-align:center; font-size:16px; letter-spacing:2px; margin-bottom:40px; }
      .paciente { font-size:13px; margin-bottom:30px; }
      .item { display:flex; gap:10px; margin-bottom:22px; font-size:14px; }
      .num { font-weight:700; }
      .med { font-weight:700; }
      .uc { font-weight:400; font-size:11px; color:#059669; }
      .pos { font-size:12.5px; color:#444; margin-top:2px; }
      .assinatura { text-align:center; margin-top:100px; }
      .linha { border-top:1px solid #111; width:320px; margin:0 auto 6px; }
      .data { text-align:right; margin-bottom:10px; font-size:13px; }
    </style></head>
    <body>
      ${htmlTimbrado()}
      <h1>RECEITUÁRIO</h1>
      <div class="data">Parauapebas, ${hoje}</div>
      <div class="paciente">Paciente: <b>${item.paciente}</b></div>
      ${itens || "<div style='text-align:center;color:#999'>Nenhum item prescrito.</div>"}
      <div class="assinatura"><div class="linha"></div>${medNome}<br/>${medCrm}</div>
      ${htmlRodapeClinica(clinica)}
    </body></html>`;
  abrirEImprimir(html, "RECEITUÁRIO");
}

function blocoIdentificacaoPaciente(item, pacienteDetalhe, hoje) {
  const nascimento = pacienteDetalhe?.nascimento
    ? new Date(pacienteDetalhe.nascimento + "T00:00:00").toLocaleDateString("pt-BR") : "—";
  return `
    <div class="paciente-info">
      <div><b>Paciente:</b> ${item.paciente}</div>
      <div><b>Nome da mãe:</b> ${pacienteDetalhe?.nome_mae || "—"}</div>
      <div><b>Data de nascimento:</b> ${nascimento}</div>
      <div><b>Telefone:</b> ${pacienteDetalhe?.telefone || "—"}</div>
      <div><b>Data do atendimento:</b> ${hoje}</div>
    </div>`;
}

function imprimirEncaminhamento(enc, item, pacienteDetalhe, medicoInfo, clinica) {
  const hoje = new Date().toLocaleDateString("pt-BR");
  const medNome = medicoInfo ? `${medicoInfo.tratamento} ${medicoInfo.nome}`.trim() : "";
  const medCrm = medicoInfo ? `${medicoInfo.conselho} ${medicoInfo.crm}${medicoInfo.uf ? "/" + medicoInfo.uf : ""}` : "";
  const html = `
    <html><head><title>ENCAMINHAMENTO</title>
    <style>
      body { font-family: 'DM Sans', Arial, sans-serif; padding: 40px 70px; color: #111; }
      ${CSS_TIMBRADO}
      ${CSS_RODAPE_CLINICA}
      h1 { text-align:center; font-size:16px; letter-spacing:2px; margin-bottom:24px; }
      .paciente-info { display:grid; grid-template-columns:1fr 1fr; gap:6px 24px; font-size:12.5px;
                        border:1px solid #E2E8F0; border-radius:8px; padding:12px 16px; margin-bottom:30px; }
      .destino { font-size:14px; margin-bottom:18px; }
      .corpo { font-size:14px; line-height:1.9; text-align:justify; margin-bottom:80px; }
      .assinatura { text-align:center; margin-top:100px; }
      .linha { border-top:1px solid #111; width:320px; margin:0 auto 6px; }
    </style></head>
    <body>
      ${htmlTimbrado()}
      <h1>ENCAMINHAMENTO MÉDICO</h1>
      ${blocoIdentificacaoPaciente(item, pacienteDetalhe, hoje)}
      <div class="destino">Encaminho o(a) paciente acima para avaliação com <b>${enc.especialidade}</b>.</div>
      <div class="corpo">${enc.texto || ""}</div>
      <div class="assinatura"><div class="linha"></div>${medNome}<br/>${medCrm}</div>
      ${htmlRodapeClinica(clinica)}
    </body></html>`;
  abrirEImprimir(html, "ENCAMINHAMENTO");
}

function useDebounce(valor, atraso = 600) {
  const [debounced, setDebounced] = useState(valor);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(valor), atraso);
    return () => clearTimeout(t);
  }, [valor, atraso]);
  return debounced;
}

function Secao({ titulo, children, contador }) {
  return (
    <div style={{ marginBottom: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <div style={{ fontSize: 12.5, fontWeight: 700, color: "#334155" }}>{titulo}</div>
        {contador && <div style={{ fontSize: 10.5, color: "#94A3B8" }}>{contador}</div>}
      </div>
      {children}
    </div>
  );
}

const inputStyle = {
  width: "100%", padding: "9px 11px", borderRadius: 8, border: "1.5px solid #E2E8F0",
  fontSize: 13, boxSizing: "border-box", fontFamily: "inherit",
};

// ── Coluna esquerda: registro, alergia, hipótese + CID ──────────────────────
function ColunaRegistro({ consulta, onPatch, onAddCid, onDelCid }) {
  const [registro, setRegistro] = useState(consulta.registro_texto || "");
  const [hipotese, setHipotese] = useState(consulta.hipotese_texto || "");
  const [alergiaDetalhe, setAlergiaDetalhe] = useState(consulta.alergia_detalhe || "");
  const [cidTermo, setCidTermo] = useState("");
  const [cidResultados, setCidResultados] = useState(null);
  const cidDebounced = useDebounce(cidTermo, 350);

  useEffect(() => {
    if (cidDebounced.trim().length < 2) { setCidResultados(null); return; }
    let vivo = true;
    fetch(`${API}/api/atendimento/buscar-cid?q=${encodeURIComponent(cidDebounced.trim())}`)
      .then(r => r.json())
      .then(d => { if (vivo) setCidResultados(d.resultados || []); })
      .catch(() => { if (vivo) setCidResultados(null); });
    return () => { vivo = false; };
  }, [cidDebounced]);

  const registroDebounced = useDebounce(registro, 900);
  const hipoteseDebounced = useDebounce(hipotese, 900);
  const alergiaDetalheDebounced = useDebounce(alergiaDetalhe, 900);
  useEffect(() => { onPatch({ registro_texto: registroDebounced }); }, [registroDebounced]);
  useEffect(() => { onPatch({ hipotese_texto: hipoteseDebounced }); }, [hipoteseDebounced]);
  useEffect(() => { onPatch({ alergia_detalhe: alergiaDetalheDebounced }); }, [alergiaDetalheDebounced]);

  return (
    <div style={{ padding: 18, overflowY: "auto", height: "100%", boxSizing: "border-box" }}>
      <Secao titulo="Modelo de atendimento">
        <div style={{ display: "flex", gap: 14 }}>
          {[["livre", "Modelo livre"], ["primeira_consulta", "Primeira consulta"], ["continuidade", "Continuidade"]].map(([v, label]) => (
            <label key={v} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12.5, color: "#334155", cursor: "pointer" }}>
              <input type="radio" checked={consulta.modelo_atendimento === v}
                onChange={() => onPatch({ modelo_atendimento: v })} />
              {label}
            </label>
          ))}
        </div>
      </Secao>

      <Secao titulo="Registro de atendimento" contador={`${registro.length}/3500`}>
        <textarea value={registro} maxLength={3500} rows={6}
          onChange={e => setRegistro(e.target.value)}
          placeholder="Descreva a queixa, exame físico, conduta..."
          style={{ ...inputStyle, resize: "vertical" }} />
      </Secao>

      <Secao titulo="Possui alguma alergia?">
        <div style={{ display: "flex", gap: 14, marginBottom: 8 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12.5, cursor: "pointer" }}>
            <input type="radio" checked={consulta.possui_alergia === "N"} onChange={() => onPatch({ possui_alergia: "N" })} /> Não
          </label>
          <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 12.5, cursor: "pointer" }}>
            <input type="radio" checked={consulta.possui_alergia === "S"} onChange={() => onPatch({ possui_alergia: "S" })} /> Sim
          </label>
        </div>
        {consulta.possui_alergia === "S" && (
          <input value={alergiaDetalhe} onChange={e => setAlergiaDetalhe(e.target.value)}
            placeholder="Qual(is) alergia(s)?" style={inputStyle} />
        )}
      </Secao>

      <Secao titulo="Hipótese(s) diagnóstica(s)" contador={`${hipotese.length}/2000`}>
        <textarea value={hipotese} maxLength={2000} rows={3}
          onChange={e => setHipotese(e.target.value)}
          placeholder="Registre a(s) hipótese(s) diagnóstica(s)."
          style={{ ...inputStyle, resize: "vertical" }} />
      </Secao>

      <Secao titulo="Selecione o CID-10 da hipótese diagnóstica">
        <div style={{ position: "relative" }}>
          <input value={cidTermo} onChange={e => setCidTermo(e.target.value)}
            placeholder="Digite código ou descrição..." style={inputStyle} />
          {cidResultados && cidResultados.length > 0 && (
            <div style={{
              position: "absolute", top: "105%", left: 0, right: 0, zIndex: 50,
              background: "#fff", border: "1px solid #E2E8F0", borderRadius: 8,
              boxShadow: "0 8px 24px rgba(0,0,0,.15)", maxHeight: 220, overflowY: "auto",
            }}>
              {cidResultados.map(r => (
                <div key={r.codigo} onClick={() => { onAddCid(r.codigo, r.nome); setCidTermo(""); setCidResultados(null); }}
                  style={{ padding: "8px 11px", cursor: "pointer", fontSize: 12.5, borderBottom: "1px solid #F8FAFC" }}
                  onMouseEnter={e => e.currentTarget.style.background = "#FEF2F2"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                  <b>{r.codigo}</b> — {r.nome}
                </div>
              ))}
            </div>
          )}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
          {(consulta.cids || []).map(c => (
            <div key={c.id} style={{
              display: "flex", alignItems: "center", gap: 6, padding: "4px 6px 4px 10px",
              borderRadius: 99, background: `${COR}12`, border: `1px solid ${COR}30`, fontSize: 11.5, color: COR, fontWeight: 600,
            }}>
              {c.cid_cod} {c.cid_desc}
              <span onClick={() => onDelCid(c.id)} style={{ cursor: "pointer", fontWeight: 900, color: `${COR}99`, padding: "0 2px" }}>×</span>
            </div>
          ))}
        </div>
      </Secao>
    </div>
  );
}

// ── Abas do meio: Pedidos / Prescrições / Atestados / Encaminhamentos ───────
function GruposMedicamentos({ consulta, login, onAplicar }) {
  const [grupos, setGrupos] = useState(null);
  const [salvando, setSalvando] = useState(false);
  const [nomeGrupo, setNomeGrupo] = useState("");
  const [compartilhado, setCompartilhado] = useState(false);

  const carregar = useCallback(() => {
    if (!login) return;
    fetch(`${API}/api/prontuario/grupos-medicamentos?medico_login=${encodeURIComponent(login)}`)
      .then(r => r.json()).then(d => setGrupos(d.grupos || [])).catch(() => setGrupos([]));
  }, [login]);

  useEffect(() => { carregar(); }, [carregar]);

  const salvarGrupo = () => {
    if (!nomeGrupo.trim() || !(consulta.prescricoes || []).length) return;
    fetch(`${API}/api/prontuario/grupos-medicamentos`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        medico_login: login, nome: nomeGrupo.trim(), compartilhado,
        itens: consulta.prescricoes.map(p => ({
          medicamento: p.medicamento, posologia: p.posologia, quantidade: p.quantidade,
          uso_continuo: p.uso_continuo === "S",
        })),
      }),
    }).then(r => r.json()).then(d => { setGrupos(d.grupos || []); setSalvando(false); setNomeGrupo(""); setCompartilhado(false); });
  };

  const remover = (grupoId) => {
    fetch(`${API}/api/prontuario/grupos-medicamentos/${grupoId}?medico_login=${encodeURIComponent(login)}`, { method: "DELETE" })
      .then(r => r.json()).then(d => setGrupos(d.grupos || []));
  };

  return (
    <div style={{ marginBottom: 14, padding: 10, borderRadius: 8, background: "#F8FAFC", border: "1px solid #F1F5F9" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase" }}>Grupos de medicamentos</div>
        {!salvando && (consulta.prescricoes || []).length > 0 && (
          <span onClick={() => setSalvando(true)} style={{ fontSize: 11.5, color: COR, fontWeight: 700, cursor: "pointer" }}>
            + Salvar os itens atuais como grupo
          </span>
        )}
      </div>

      {salvando && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 8, flexWrap: "wrap" }}>
          <input value={nomeGrupo} onChange={e => setNomeGrupo(e.target.value)} placeholder="Nome do grupo (ex: Protocolo Gripe)"
            style={{ ...inputStyle, flex: 1, minWidth: 180 }} autoFocus />
          <label style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11.5, whiteSpace: "nowrap" }}>
            <input type="checkbox" checked={compartilhado} onChange={e => setCompartilhado(e.target.checked)} /> Compartilhar com todos
          </label>
          <button onClick={salvarGrupo} style={{ padding: "6px 12px", borderRadius: 7, border: "none", background: COR, color: "#fff", fontWeight: 700, fontSize: 11.5, cursor: "pointer" }}>Salvar</button>
          <button onClick={() => { setSalvando(false); setNomeGrupo(""); }} style={{ padding: "6px 12px", borderRadius: 7, border: "1px solid #E2E8F0", background: "#fff", color: "#64748B", fontWeight: 700, fontSize: 11.5, cursor: "pointer" }}>Cancelar</button>
        </div>
      )}

      {grupos === null ? (
        <div style={{ fontSize: 11.5, color: "#CBD5E1" }}>Carregando grupos...</div>
      ) : grupos.length === 0 ? (
        <div style={{ fontSize: 11.5, color: "#CBD5E1" }}>Nenhum grupo salvo ainda.</div>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {grupos.map(g => (
            <div key={g.id} style={{
              display: "flex", alignItems: "center", gap: 6, padding: "5px 6px 5px 11px",
              borderRadius: 99, background: "#fff", border: "1px solid #E2E8F0", fontSize: 11.5,
            }}>
              <span onClick={() => onAplicar(g.itens)} style={{ cursor: "pointer", fontWeight: 700, color: "#334155" }} title={g.itens.map(i => i.medicamento).join(", ")}>
                {g.nome} <span style={{ color: "#94A3B8", fontWeight: 400 }}>({g.itens.length})</span>
              </span>
              {g.compartilhado === "S" && <span style={{ fontSize: 9, color: "#059669" }}>🌐</span>}
              {g.proprio && <span onClick={() => remover(g.id)} style={{ cursor: "pointer", color: "#CBD5E1", fontWeight: 900 }}>×</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function AbaPrescricoes({ consulta, item, medicoInfo, clinica, login, onAdd, onDel }) {
  const [medicamento, setMedicamento] = useState("");
  const [posologia, setPosologia] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [usoContinuo, setUsoContinuo] = useState(false);
  const [sugestoes, setSugestoes] = useState(null);
  const medicamentoDebounced = useDebounce(medicamento, 300);

  useEffect(() => {
    let vivo = true;
    fetch(`${API}/api/atendimento/buscar-medicamento?q=${encodeURIComponent(medicamentoDebounced.trim())}&medico_login=${encodeURIComponent(login || "")}`)
      .then(r => r.json())
      .then(d => { if (vivo) setSugestoes(d.resultados || []); })
      .catch(() => { if (vivo) setSugestoes(null); });
    return () => { vivo = false; };
  }, [medicamentoDebounced, login]);

  const adicionar = () => {
    if (!medicamento.trim()) return;
    onAdd({ medicamento: medicamento.trim(), posologia, quantidade, uso_continuo: usoContinuo });
    setMedicamento(""); setPosologia(""); setQuantidade(""); setUsoContinuo(false);
  };

  return (
    <div>
      <GruposMedicamentos consulta={consulta} login={login} onAplicar={(itens) => itens.forEach(it => onAdd({
        medicamento: it.medicamento, posologia: it.posologia, quantidade: it.quantidade, uso_continuo: it.uso_continuo === "S",
      }))} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <div style={{ position: "relative" }}>
          <input value={medicamento} onChange={e => setMedicamento(e.target.value)} placeholder="Medicamento"
            onFocus={() => setSugestoes(s => s === null ? [] : s)} style={inputStyle} />
          {sugestoes && sugestoes.length > 0 && (
            <div style={{
              position: "absolute", top: "105%", left: 0, right: 0, zIndex: 50,
              background: "#fff", border: "1px solid #E2E8F0", borderRadius: 8,
              boxShadow: "0 8px 24px rgba(0,0,0,.15)", maxHeight: 180, overflowY: "auto",
            }}>
              {sugestoes.map(s => (
                <div key={s.nome} onClick={() => {
                  setMedicamento(s.nome);
                  if (s.ultima_posologia) setPosologia(s.ultima_posologia);
                  if (s.ultima_quantidade) setQuantidade(s.ultima_quantidade);
                  if (s.uso > 0) setUsoContinuo(!!s.ultimo_uso_continuo);
                  setSugestoes(null);
                }}
                  style={{ padding: "7px 11px", cursor: "pointer", fontSize: 12.5, borderBottom: "1px solid #F8FAFC" }}
                  onMouseEnter={e => e.currentTarget.style.background = "#FEF2F2"}
                  onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                  {s.nome}{s.uso > 0 && <span style={{ marginLeft: 6, fontSize: 9.5, color: "#059669", fontWeight: 700 }}>· já usado {s.uso}x — carrega a posologia</span>}
                  {s.principio_ativo && <div style={{ fontSize: 10.5, color: "#94A3B8" }}>{s.principio_ativo}</div>}
                </div>
              ))}
            </div>
          )}
        </div>
        <input value={posologia} onChange={e => setPosologia(e.target.value)} placeholder="Posologia (ex: 1cp 8/8h)" style={inputStyle} />
        <input value={quantidade} onChange={e => setQuantidade(e.target.value)} placeholder="Quantidade" style={inputStyle} />
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12.5 }}>
          <input type="checkbox" checked={usoContinuo} onChange={e => setUsoContinuo(e.target.checked)} /> Uso contínuo
        </label>
      </div>
      <div style={{ display: "flex", gap: 10 }}>
        <button onClick={adicionar} style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: COR, color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: "pointer" }}>
          + Adicionar prescrição
        </button>
        {(consulta.prescricoes || []).length > 0 && (
          <button onClick={() => imprimirReceita(consulta, item, medicoInfo, clinica)} style={{ padding: "8px 16px", borderRadius: 8, border: "1.5px solid #E2E8F0", background: "#fff", color: "#334155", fontWeight: 700, fontSize: 12.5, cursor: "pointer" }}>
            🖨️ Imprimir receita
          </button>
        )}
      </div>
      <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
        {(consulta.prescricoes || []).map(p => (
          <div key={p.id} style={{ padding: "10px 12px", borderRadius: 8, background: "#F8FAFC", border: "1px solid #F1F5F9", display: "flex", justifyContent: "space-between", gap: 8 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{p.medicamento}{p.uso_continuo === "S" && <span style={{ marginLeft: 6, fontSize: 9.5, color: "#059669", background: "#ECFDF5", padding: "1px 6px", borderRadius: 99, fontWeight: 800 }}>USO CONTÍNUO</span>}</div>
              <div style={{ fontSize: 11.5, color: "#64748B" }}>{p.posologia}{p.quantidade ? ` · ${p.quantidade}` : ""}</div>
            </div>
            <span onClick={() => onDel(p.id)} style={{ cursor: "pointer", color: "#CBD5E1", fontWeight: 900 }}>×</span>
          </div>
        ))}
        {(!consulta.prescricoes || consulta.prescricoes.length === 0) && (
          <div style={{ textAlign: "center", color: "#CBD5E1", fontSize: 12.5, padding: 20 }}>Nenhuma prescrição ainda.</div>
        )}
      </div>
    </div>
  );
}

function AbaAtestados({ consulta, item, medicoInfo, clinica, onAdd, onDel }) {
  const [texto, setTexto] = useState("");
  const [dias, setDias] = useState("");
  const [dataInicio, setDataInicio] = useState(new Date().toISOString().slice(0, 10));

  const adicionar = () => {
    if (!texto.trim()) return;
    onAdd({ texto: texto.trim(), dias: dias ? Number(dias) : null, data_inicio: dataInicio, cid_cod: (consulta.cids?.[0]?.cid_cod) || "" });
    setTexto(""); setDias("");
  };

  return (
    <div>
      <textarea value={texto} onChange={e => setTexto(e.target.value)} rows={3}
        placeholder="Texto do atestado..." style={{ ...inputStyle, resize: "vertical", marginBottom: 10 }} />
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <input type="number" min={1} value={dias} onChange={e => setDias(e.target.value)} placeholder="Nº de dias de afastamento" style={inputStyle} />
        <input type="date" value={dataInicio} onChange={e => setDataInicio(e.target.value)} style={inputStyle} />
      </div>
      <button onClick={adicionar} style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: COR, color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: "pointer" }}>
        + Adicionar atestado
      </button>
      <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
        {(consulta.atestados || []).map(a => (
          <div key={a.id} style={{ padding: "10px 12px", borderRadius: 8, background: "#F8FAFC", border: "1px solid #F1F5F9", display: "flex", justifyContent: "space-between", gap: 8 }}>
            <div>
              <div style={{ fontSize: 13, color: "#0F172A" }}>{a.texto}</div>
              <div style={{ fontSize: 11.5, color: "#64748B" }}>{a.dias ? `${a.dias} dia(s) a partir de ${a.data_inicio}` : a.data_inicio}{a.cid_cod ? ` · CID ${a.cid_cod}` : ""}</div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
              <span onClick={() => imprimirAtestado(a, item, medicoInfo, clinica)} title="Imprimir" style={{ cursor: "pointer", fontSize: 14 }}>🖨️</span>
              <span onClick={() => onDel(a.id)} style={{ cursor: "pointer", color: "#CBD5E1", fontWeight: 900 }}>×</span>
            </div>
          </div>
        ))}
        {(!consulta.atestados || consulta.atestados.length === 0) && (
          <div style={{ textAlign: "center", color: "#CBD5E1", fontSize: 12.5, padding: 20 }}>Nenhum atestado ainda.</div>
        )}
      </div>
    </div>
  );
}

function AbaEncaminhamentos({ consulta, item, pacienteDetalhe, medicoInfo, clinica, onAdd, onDel }) {
  const [especialidade, setEspecialidade] = useState("");
  const [texto, setTexto] = useState("");

  const adicionar = () => {
    if (!especialidade.trim()) return;
    onAdd({ especialidade: especialidade.trim(), texto });
    setEspecialidade(""); setTexto("");
  };

  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
        <input value={especialidade} onChange={e => setEspecialidade(e.target.value)} placeholder="Especialidade / profissional" style={inputStyle} />
        <input value={texto} onChange={e => setTexto(e.target.value)} placeholder="Observação (opcional)" style={inputStyle} />
      </div>
      <button onClick={adicionar} style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: COR, color: "#fff", fontWeight: 700, fontSize: 12.5, cursor: "pointer" }}>
        + Adicionar encaminhamento
      </button>
      <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 8 }}>
        {(consulta.encaminhamentos || []).map(e => (
          <div key={e.id} style={{ padding: "10px 12px", borderRadius: 8, background: "#F8FAFC", border: "1px solid #F1F5F9", display: "flex", justifyContent: "space-between", gap: 8 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{e.especialidade}</div>
              {e.texto && <div style={{ fontSize: 11.5, color: "#64748B" }}>{e.texto}</div>}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
              <span onClick={() => imprimirEncaminhamento(e, item, pacienteDetalhe, medicoInfo, clinica)} title="Imprimir" style={{ cursor: "pointer", fontSize: 14 }}>🖨️</span>
              <span onClick={() => onDel(e.id)} style={{ cursor: "pointer", color: "#CBD5E1", fontWeight: 900 }}>×</span>
            </div>
          </div>
        ))}
        {(!consulta.encaminhamentos || consulta.encaminhamentos.length === 0) && (
          <div style={{ textAlign: "center", color: "#CBD5E1", fontSize: 12.5, padding: 20 }}>Nenhum encaminhamento ainda.</div>
        )}
      </div>
    </div>
  );
}

function AbaHistorico({ pacReg, pacienteNome }) {
  const [historico, setHistorico] = useState(null);
  useEffect(() => {
    fetch(`${API}/api/prontuario/paciente/${pacReg}/historico`).then(r => r.json())
      .then(d => setHistorico(d.historico || [])).catch(() => setHistorico([]));
  }, [pacReg]);

  if (historico === null) return <div style={{ color: "#94A3B8", fontSize: 12.5 }}>Carregando...</div>;
  if (historico.length === 0) return <div style={{ textAlign: "center", color: "#CBD5E1", fontSize: 12.5, padding: 20 }}>Sem atendimentos anteriores registrados.</div>;

  const montarPrompt = () => {
    const consultas = historico.map(h => {
      const alergia = h.possui_alergia === "S" ? `Alergia: ${h.alergia_detalhe || "sim, sem detalhe"}.` : "";
      const cids = (h.cids || []).map(c => `${c.cid_cod} ${c.cid_desc || ""}`).join(", ");
      const prescr = (h.prescricoes || []).map(p => p.medicamento).join(", ");
      return `- ${h.iniciado_em} (${h.medico_nome || "médico não identificado"}, ${h.status}): `
        + `registro: ${h.registro_texto || "—"}. Hipótese: ${h.hipotese_texto || "—"}. CID: ${cids || "—"}. `
        + `Prescrito: ${prescr || "nenhum"}. ${alergia}`;
    }).join("\n");
    return `Você é um assistente clínico. Resuma o histórico de atendimentos do paciente ${pacienteNome || ""} abaixo em um parágrafo curto (máx. 6 frases), destacando condições recorrentes, alergias relatadas e medicações já usadas. Seja objetivo, sem markdown.\n\n${consultas}`;
  };

  return (
    <div>
      <BriefingCard cor={COR} cacheKey={`briefing_prontuario_${pacReg}`} promptFn={montarPrompt} />
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
        {historico.map(h => (
          <div key={h.id} style={{ padding: "10px 12px", borderRadius: 8, background: "#F8FAFC", border: "1px solid #F1F5F9" }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#0F172A" }}>{h.iniciado_em} · {h.medico_nome || "—"}</div>
            <div style={{ fontSize: 11.5, color: "#64748B" }}>{h.hipotese_texto || "sem hipótese registrada"} · {h.status}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Coluna do meio: abas ─────────────────────────────────────────────────────
function ColunaMeio({ consulta, patch, item, pacReg, medicoInfo, pacienteDetalhe, clinica, login, aba, setAba }) {
  const abas = [
    ["pedidos", "Pedidos"], ["prescricoes", "Prescrições"], ["atestados", "Atestados"],
    ["encaminhamentos", "Encaminhamentos"], ["historico", "Histórico"],
  ];
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      <div style={{ display: "flex", gap: 2, borderBottom: "1.5px solid #E2E8F0", flexShrink: 0, overflowX: "auto" }}>
        {abas.map(([id, label]) => (
          <button key={id} onClick={() => setAba(id)} style={{
            padding: "10px 14px", border: "none", background: "transparent", cursor: "pointer",
            fontSize: 12.5, fontWeight: 700, whiteSpace: "nowrap",
            color: aba === id ? COR : "#94A3B8",
            borderBottom: aba === id ? `2.5px solid ${COR}` : "2.5px solid transparent",
          }}>{label}</button>
        ))}
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: 18 }}>
        {aba === "pedidos" && <DocGuiaSadt item={item} medicoInfo={medicoInfo} />}
        {aba === "prescricoes" && <AbaPrescricoes consulta={consulta} item={item} medicoInfo={medicoInfo} clinica={clinica} login={login}
          onAdd={d => patch.addPrescricao(d)} onDel={id => patch.delPrescricao(id)} />}
        {aba === "atestados" && <AbaAtestados consulta={consulta} item={item} medicoInfo={medicoInfo} clinica={clinica}
          onAdd={d => patch.addAtestado(d)} onDel={id => patch.delAtestado(id)} />}
        {aba === "encaminhamentos" && <AbaEncaminhamentos consulta={consulta} item={item} pacienteDetalhe={pacienteDetalhe} medicoInfo={medicoInfo} clinica={clinica}
          onAdd={d => patch.addEncaminhamento(d)} onDel={id => patch.delEncaminhamento(id)} />}
        {aba === "historico" && <AbaHistorico pacReg={pacReg} pacienteNome={item?.paciente} />}
      </div>
    </div>
  );
}

// ── Cronômetro ───────────────────────────────────────────────────────────────
function useCronometro(iniciadoEm) {
  const [texto, setTexto] = useState("00:00:00");
  useEffect(() => {
    if (!iniciadoEm) return;
    const inicio = new Date(iniciadoEm.replace(" ", "T")).getTime();
    const tick = () => {
      const diff = Math.max(0, Math.floor((Date.now() - inicio) / 1000));
      const h = String(Math.floor(diff / 3600)).padStart(2, "0");
      const m = String(Math.floor((diff % 3600) / 60)).padStart(2, "0");
      const s = String(diff % 60).padStart(2, "0");
      setTexto(`${h}:${m}:${s}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [iniciadoEm]);
  return texto;
}

// ── Assistente de finalização ────────────────────────────────────────────────
function ModalFinalizar({ consulta, login, onFechar, onFinalizado }) {
  const [passo, setPasso] = useState(1);
  const [retorno, setRetorno] = useState(null); // 'S' | 'N'
  const [retornoQuando, setRetornoQuando] = useState("");
  const [assinar, setAssinar] = useState(null); // true | false
  const [enviando, setEnviando] = useState(false);

  const finalizar = async () => {
    setEnviando(true);
    try {
      const res = await fetch(`${API}/api/prontuario/${consulta.id}/finalizar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          retorno_necessario: retorno, retorno_quando: retorno === "S" ? retornoQuando : "",
          assinar: !!assinar, assinado_por: login,
        }),
      });
      const d = await res.json();
      onFinalizado(d);
    } catch {
      setEnviando(false);
    }
  };

  const steps = ["Retorno de atendimento", "Assinatura", "Resumo"];

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 500, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ background: "#fff", borderRadius: 14, width: 520, maxWidth: "92vw", padding: 24, boxShadow: "0 20px 60px rgba(0,0,0,.3)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
          <div style={{ fontSize: 16, fontWeight: 800, color: "#0F172A" }}>Finalizar atendimento</div>
          <span onClick={onFechar} style={{ cursor: "pointer", color: "#94A3B8", fontSize: 18, fontWeight: 900 }}>×</span>
        </div>
        <div style={{ display: "flex", gap: 6, marginBottom: 20 }}>
          {steps.map((s, i) => (
            <div key={s} style={{ flex: 1 }}>
              <div style={{ height: 3, borderRadius: 2, background: passo > i ? COR : (passo === i + 1 ? COR : "#E2E8F0") }} />
              <div style={{ fontSize: 10.5, color: passo === i + 1 ? COR : "#94A3B8", fontWeight: 700, marginTop: 4 }}>{s}</div>
            </div>
          ))}
        </div>

        {passo === 1 && (
          <div>
            <div style={{ fontSize: 13, color: "#334155", marginBottom: 12 }}>Será necessário marcar retorno de atendimento para o paciente?</div>
            <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13, marginBottom: 8, cursor: "pointer" }}>
              <input type="radio" checked={retorno === "S"} onChange={() => setRetorno("S")} /> Sim, o paciente precisa realizar retorno.
            </label>
            {retorno === "S" && (
              <input value={retornoQuando} onChange={e => setRetornoQuando(e.target.value)} placeholder="Quando (ex: 30 dias, 11/2026)"
                style={{ ...inputStyle, marginBottom: 8 }} />
            )}
            <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13, cursor: "pointer" }}>
              <input type="radio" checked={retorno === "N"} onChange={() => setRetorno("N")} /> Não, o paciente não precisa realizar retorno.
            </label>
          </div>
        )}

        {passo === 2 && (
          <div>
            <div style={{ fontSize: 13, color: "#334155", marginBottom: 4 }}>Você deseja assinar agora o atendimento?</div>
            <div style={{ fontSize: 11, color: "#94A3B8", marginBottom: 12 }}>
              Assinatura eletrônica simples (confirmação com seu login + carimbo de data/hora) — não é um certificado digital ICP-Brasil.
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13, marginBottom: 8, cursor: "pointer" }}>
              <input type="radio" checked={assinar === true} onChange={() => setAssinar(true)} /> Sim, quero assinar agora.
            </label>
            <label style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13, cursor: "pointer" }}>
              <input type="radio" checked={assinar === false} onChange={() => setAssinar(false)} /> Não, deixarei sem assinar por enquanto.
            </label>
          </div>
        )}

        {passo === 3 && (
          <div style={{ fontSize: 13, color: "#334155" }}>
            <div style={{ marginBottom: 8 }}><b>Retorno:</b> {retorno === "S" ? `Sim (${retornoQuando || "a combinar"})` : "Não"}</div>
            <div style={{ marginBottom: 8 }}><b>Assinatura:</b> {assinar ? "Será assinado agora" : "Sem assinatura por enquanto"}</div>
            <div style={{ marginBottom: 8 }}><b>Hipótese diagnóstica:</b> {consulta.hipotese_texto || "—"}</div>
            <div><b>CID:</b> {(consulta.cids || []).map(c => c.cid_cod).join(", ") || "—"}</div>
          </div>
        )}

        <div style={{ display: "flex", gap: 10, marginTop: 22 }}>
          <button onClick={() => passo === 1 ? onFechar() : setPasso(p => p - 1)}
            style={{ flex: 1, padding: "11px", borderRadius: 9, border: "1.5px solid #E2E8F0", background: "#fff", color: "#64748B", fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
            {passo === 1 ? "Voltar para o atendimento" : "Voltar"}
          </button>
          {passo < 3 ? (
            <button disabled={passo === 1 ? retorno === null : assinar === null}
              onClick={() => setPasso(p => p + 1)}
              style={{ flex: 1, padding: "11px", borderRadius: 9, border: "none", background: COR, color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer", opacity: (passo === 1 ? retorno === null : assinar === null) ? .5 : 1 }}>
              Avançar
            </button>
          ) : (
            <button disabled={enviando} onClick={finalizar}
              style={{ flex: 1, padding: "11px", borderRadius: 9, border: "none", background: COR, color: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer" }}>
              {enviando ? "Finalizando..." : "Finalizar atendimento"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Coluna direita: cronômetro, paciente, ações ─────────────────────────────
function ColunaDireita({ consulta, item, login, onFechar, onFinalizado }) {
  const tempo = useCronometro(consulta.iniciado_em);
  const [abaHistorico, setAbaHistorico] = useState(false);
  const [modalFinalizar, setModalFinalizar] = useState(false);
  const finalizado = consulta.status === "finalizado";

  return (
    <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 16, height: "100%", boxSizing: "border-box" }}>
      <div>
        <div style={{ fontSize: 10.5, color: "#94A3B8", fontWeight: 700, textTransform: "uppercase" }}>⏱ Tempo de atendimento</div>
        <div style={{ fontSize: 22, fontWeight: 900, color: "#0F172A" }}>{tempo}</div>
      </div>
      <div>
        <div style={{ fontSize: 10.5, color: "#94A3B8", fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>Dados do Paciente</div>
        <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>{item.paciente}</div>
      </div>
      {finalizado && (
        <div style={{ padding: "10px 12px", borderRadius: 8, background: "#ECFDF5", border: "1px solid #A7F3D0", fontSize: 12, color: "#059669", fontWeight: 700 }}>
          ✓ Atendimento finalizado{consulta.assinado_em ? " e assinado" : ""} em {consulta.finalizado_em}
        </div>
      )}
      <div style={{ marginTop: "auto", display: "flex", flexDirection: "column", gap: 10 }}>
        <button onClick={() => setAbaHistorico(true)} style={{
          padding: "11px", borderRadius: 9, border: "none", background: "#0891B2", color: "#fff",
          fontWeight: 700, fontSize: 13, cursor: "pointer",
        }}>Histórico de atendimento</button>
        <button onClick={onFechar} style={{
          padding: "11px", borderRadius: 9, border: "1.5px solid #E2E8F0", background: "#fff", color: "#64748B",
          fontWeight: 700, fontSize: 13, cursor: "pointer",
        }}>Voltar sem finalizar</button>
        {!finalizado && (
          <button onClick={() => setModalFinalizar(true)} style={{
            padding: "11px", borderRadius: 9, border: "none", background: "#DC2626", color: "#fff",
            fontWeight: 700, fontSize: 13, cursor: "pointer",
          }}>Finalizar atendimento</button>
        )}
      </div>

      {abaHistorico && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", zIndex: 500, display: "flex", alignItems: "center", justifyContent: "center" }}
          onClick={() => setAbaHistorico(false)}>
          <div onClick={e => e.stopPropagation()} style={{ background: "#fff", borderRadius: 14, width: 480, maxWidth: "92vw", maxHeight: "80vh", overflowY: "auto", padding: 20 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 14 }}>
              <div style={{ fontSize: 15, fontWeight: 800 }}>Histórico de atendimento</div>
              <span onClick={() => setAbaHistorico(false)} style={{ cursor: "pointer", fontWeight: 900, color: "#94A3B8" }}>×</span>
            </div>
            <AbaHistorico pacReg={item.pac_reg} pacienteNome={item.paciente} />
          </div>
        </div>
      )}
      {modalFinalizar && (
        <ModalFinalizar consulta={consulta} login={login}
          onFechar={() => setModalFinalizar(false)}
          onFinalizado={(d) => { setModalFinalizar(false); onFinalizado(d); }} />
      )}
    </div>
  );
}

// ── Componente principal ─────────────────────────────────────────────────────
export default function TelaProntuario({ item, medico, medicoNome, login, onCancelar, onFinalizado }) {
  const [consulta, setConsulta] = useState(null);
  const [aba, setAba] = useState("prescricoes");
  const iniciadoRef = useRef(false);
  const [medicoInfo, setMedicoInfo] = useState(null);
  const [pacienteDetalhe, setPacienteDetalhe] = useState(null);
  const [clinica, setClinica] = useState(null);

  useEffect(() => {
    fetch(`${API}/api/atendimento/medico/${medico}`).then(r => r.json()).then(setMedicoInfo).catch(() => {});
  }, [medico]);

  useEffect(() => {
    fetch(`${API}/api/atendimento/paciente/${item.pac_reg}`).then(r => r.json()).then(setPacienteDetalhe).catch(() => {});
  }, [item.pac_reg]);

  useEffect(() => {
    fetch(`${API}/api/atendimento/clinica`).then(r => r.json()).then(setClinica).catch(() => {});
  }, []);

  useEffect(() => {
    if (iniciadoRef.current) return;
    iniciadoRef.current = true;
    fetch(`${API}/api/prontuario/iniciar`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        pac_reg: item.pac_reg, paciente_nome: item.paciente,
        medico_psv_cod: medico, medico_nome: medicoNome || "", medico_login: login,
      }),
    }).then(r => r.json()).then(setConsulta).catch(() => {});
  }, [item.pac_reg]);

  const patchConsulta = useCallback((campos) => {
    setConsulta(c => c ? { ...c, ...campos } : c);
    if (!consulta) return;
    fetch(`${API}/api/prontuario/${consulta.id}`, {
      method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(campos),
    }).catch(() => {});
  }, [consulta?.id]);

  const recarregar = (d) => setConsulta(d);

  const addCid = (cid_cod, cid_desc) => {
    fetch(`${API}/api/prontuario/${consulta.id}/cid`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ cid_cod, cid_desc }),
    }).then(r => r.json()).then(recarregar);
  };
  const delCid = (id) => fetch(`${API}/api/prontuario/${consulta.id}/cid/${id}`, { method: "DELETE" }).then(r => r.json()).then(recarregar);

  const addPrescricao = (d) => fetch(`${API}/api/prontuario/${consulta.id}/prescricao`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d),
  }).then(r => r.json()).then(recarregar);
  const delPrescricao = (id) => fetch(`${API}/api/prontuario/${consulta.id}/prescricao/${id}`, { method: "DELETE" }).then(r => r.json()).then(recarregar);

  const addAtestado = (d) => fetch(`${API}/api/prontuario/${consulta.id}/atestado`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d),
  }).then(r => r.json()).then(recarregar);
  const delAtestado = (id) => fetch(`${API}/api/prontuario/${consulta.id}/atestado/${id}`, { method: "DELETE" }).then(r => r.json()).then(recarregar);

  const addEncaminhamento = (d) => fetch(`${API}/api/prontuario/${consulta.id}/encaminhamento`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d),
  }).then(r => r.json()).then(recarregar);
  const delEncaminhamento = (id) => fetch(`${API}/api/prontuario/${consulta.id}/encaminhamento/${id}`, { method: "DELETE" }).then(r => r.json()).then(recarregar);

  if (!consulta) {
    return <div style={{ padding: 40, textAlign: "center", color: "#94A3B8" }}>Abrindo atendimento...</div>;
  }

  return (
    <div style={{
      height: "100%", display: "grid", gridTemplateColumns: "minmax(300px, 400px) minmax(340px, 1fr) minmax(220px, 260px)",
      background: "#fff", borderRadius: 16, boxShadow: "0 1px 4px rgba(0,0,0,.07), 0 0 0 1px rgba(0,0,0,.03)",
      overflow: "auto", minHeight: 0,
    }}>
      <div style={{ borderRight: "1px solid #F1F5F9", minHeight: 0, minWidth: 0 }}>
        <ColunaRegistro consulta={consulta} onPatch={patchConsulta} onAddCid={addCid} onDelCid={delCid} />
      </div>
      <div style={{ borderRight: "1px solid #F1F5F9", minHeight: 0, minWidth: 0 }}>
        <ColunaMeio consulta={consulta} item={item} pacReg={item.pac_reg} medicoInfo={medicoInfo} pacienteDetalhe={pacienteDetalhe} clinica={clinica} login={login} aba={aba} setAba={setAba}
          patch={{ addPrescricao, delPrescricao, addAtestado, delAtestado, addEncaminhamento, delEncaminhamento }} />
      </div>
      <div style={{ minHeight: 0, minWidth: 0 }}>
        <ColunaDireita consulta={consulta} item={item} login={login}
          onFechar={onCancelar}
          onFinalizado={(d) => { setConsulta(d); onFinalizado?.(d); }} />
      </div>
    </div>
  );
}
