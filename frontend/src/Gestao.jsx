import { useState, useEffect, useCallback, useMemo } from "react";
import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from "recharts";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;
const COR = "#4F46E5";
const COR2 = "#4338CA";

const STATUS_OPCOES = [
  { valor: "dentro_meta", label: "Dentro da meta", cor: "#059669", bg: "#ECFDF5" },
  { valor: "atencao", label: "Atenção", cor: "#D97706", bg: "#FFFBEB" },
  { valor: "fora_meta", label: "Fora da meta", cor: "#DC2626", bg: "#FEF2F2" },
];
const SEM_LANCAMENTO = { valor: "sem_lancamento", label: "Sem lançamento", cor: "#94A3B8", bg: "#F1F5F9" };

function statusInfo(status) {
  return STATUS_OPCOES.find(s => s.valor === status) || SEM_LANCAMENTO;
}

const REGEX_DIACRITICOS = new RegExp("[̀-ͯ]", "g");
function slugSetor(nome) {
  const semAcentos = (nome || "").normalize("NFD").replace(REGEX_DIACRITICOS, "");
  return semAcentos.replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_+|_+$/g, "").toLowerCase();
}

function periodoAtual() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function mesLabel(periodo) {
  const [y, m] = periodo.split("-");
  const nomes = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  return `${nomes[parseInt(m, 10) - 1]}/${y.slice(2)}`;
}

const Card = ({ children, style }) => (
  <div style={{
    background: "#fff", borderRadius: 14,
    boxShadow: "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
    ...style,
  }}>
    {children}
  </div>
);

const campoStyle = { width: "100%", padding: "8px 10px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 13, boxSizing: "border-box" };
const labelStyle = { fontSize: 11.5, fontWeight: 700, color: "#64748B", marginBottom: 4, display: "block" };

// Gestão da fórmula de cálculo automático de um indicador: variáveis
// (automáticas = vêm de um cálculo já validado contra o Smart; manuais =
// alguém digita o número, mas quem soma/divide é o sistema) + a expressão
// que combina elas. Só aparece ao editar um indicador já existente (precisa
// do id, que só existe depois do primeiro "Salvar").
function SecaoFormula({ indicadorId, expressaoInicial }) {
  const [aberta, setAberta] = useState(!!expressaoInicial);
  const [expressao, setExpressao] = useState(expressaoInicial || "");
  const [variaveis, setVariaveis] = useState([]);
  const [calculos, setCalculos] = useState([]);
  const [novaVar, setNovaVar] = useState({ chave: "", label: "", tipo: "manual", calculo_id: "" });
  const [salvandoExpressao, setSalvandoExpressao] = useState(false);
  const [preview, setPreview] = useState(null);
  const [testando, setTestando] = useState(false);
  const [erro, setErro] = useState(null);

  const carregarVariaveis = useCallback(() => {
    fetch(`${API}/api/indicadores/${indicadorId}/variaveis`).then(r => r.json()).then(setVariaveis).catch(() => setVariaveis([]));
  }, [indicadorId]);

  useEffect(() => { carregarVariaveis(); }, [carregarVariaveis]);
  useEffect(() => {
    fetch(`${API}/api/indicadores/calculos-automaticos`).then(r => r.json()).then(setCalculos).catch(() => setCalculos([]));
  }, []);

  const salvarExpressao = async () => {
    setSalvandoExpressao(true); setErro(null);
    try {
      const resp = await fetch(`${API}/api/indicadores/${indicadorId}/expressao`, {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expressao: expressao.trim() || null }),
      });
      if (!resp.ok) { const d = await resp.json(); throw new Error(d.detail || "Erro ao salvar fórmula."); }
      setPreview(null);
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setSalvandoExpressao(false);
    }
  };

  const adicionarVariavel = async () => {
    if (!novaVar.chave.trim() || !novaVar.label.trim()) { setErro("Preencha chave e nome da variável."); return; }
    if (novaVar.tipo === "automatico" && !novaVar.calculo_id) { setErro("Escolha o cálculo automático."); return; }
    setErro(null);
    try {
      const resp = await fetch(`${API}/api/indicadores/${indicadorId}/variaveis`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...novaVar, calculo_id: novaVar.tipo === "automatico" ? novaVar.calculo_id : null, ordem: variaveis.length }),
      });
      if (!resp.ok) { const d = await resp.json(); throw new Error(d.detail || "Erro ao criar variável."); }
      setNovaVar({ chave: "", label: "", tipo: "manual", calculo_id: "" });
      carregarVariaveis();
    } catch (e) {
      setErro(String(e.message || e));
    }
  };

  const removerVariavel = async (id) => {
    try {
      await fetch(`${API}/api/indicadores/variaveis/${id}`, { method: "DELETE" });
      carregarVariaveis();
    } catch (e) {
      setErro(String(e.message || e));
    }
  };

  const testarCalculo = async () => {
    setTestando(true); setErro(null);
    try {
      const resp = await fetch(`${API}/api/indicadores/${indicadorId}/calcular?periodo=${periodoAtual()}`);
      const d = await resp.json();
      setPreview(d);
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setTestando(false);
    }
  };

  if (!aberta) {
    return (
      <button type="button" onClick={() => setAberta(true)} style={{
        marginTop: 4, border: "none", background: "transparent", color: COR, fontWeight: 700, fontSize: 12.5, cursor: "pointer", padding: 0,
      }}>⚙ Configurar cálculo automático (fórmula)</button>
    );
  }

  return (
    <div style={{ marginTop: 4, padding: 14, background: "#F8FAFC", borderRadius: 10, border: "1px solid #E2E8F0" }}>
      <div style={{ fontSize: 12.5, fontWeight: 800, color: "#334155", marginBottom: 8 }}>⚙ Cálculo automático</div>

      <div style={{ marginBottom: 10 }}>
        <label style={labelStyle}>Variáveis</label>
        {variaveis.length === 0 && <div style={{ fontSize: 11.5, color: "#94A3B8", marginBottom: 6 }}>Nenhuma variável ainda.</div>}
        {variaveis.map(v => (
          <div key={v.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", background: "#fff", border: "1px solid #F1F5F9", borderRadius: 8, marginBottom: 4 }}>
            <code style={{ fontSize: 11, fontWeight: 800, color: COR, background: `${COR}12`, padding: "2px 6px", borderRadius: 5 }}>{v.chave}</code>
            <span style={{ fontSize: 11.5, color: "#334155", flex: 1 }}>{v.label}</span>
            <span style={{ fontSize: 10, fontWeight: 700, color: v.tipo === "automatico" ? "#0369A1" : "#B45309" }}>
              {v.tipo === "automatico" ? `auto: ${calculos.find(c => c.id === v.calculo_id)?.label || v.calculo_id}` : "manual"}
            </span>
            <button type="button" onClick={() => removerVariavel(v.id)} style={{ border: "none", background: "transparent", color: "#94A3B8", cursor: "pointer", fontSize: 13 }}>🗑</button>
          </div>
        ))}

        <div style={{ display: "flex", gap: 6, marginTop: 8, flexWrap: "wrap", alignItems: "center" }}>
          <input value={novaVar.chave} onChange={e => setNovaVar(p => ({ ...p, chave: e.target.value.replace(/[^a-zA-Z0-9_]/g, "") }))}
            placeholder="chave (ex: coletas)" style={{ ...campoStyle, width: 130 }} />
          <input value={novaVar.label} onChange={e => setNovaVar(p => ({ ...p, label: e.target.value }))}
            placeholder="Nome amigável" style={{ ...campoStyle, flex: 1, minWidth: 120 }} />
          <select value={novaVar.tipo} onChange={e => setNovaVar(p => ({ ...p, tipo: e.target.value }))} style={{ ...campoStyle, width: 100 }}>
            <option value="manual">Manual</option>
            <option value="automatico">Automático</option>
          </select>
          {novaVar.tipo === "automatico" && (
            <select value={novaVar.calculo_id} onChange={e => setNovaVar(p => ({ ...p, calculo_id: e.target.value }))} style={{ ...campoStyle, width: 200 }}>
              <option value="">Escolha o cálculo...</option>
              {calculos.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}
            </select>
          )}
          <button type="button" onClick={adicionarVariavel} style={{
            padding: "8px 12px", borderRadius: 8, border: "none", background: COR, color: "#fff", fontWeight: 700, fontSize: 12, cursor: "pointer",
          }}>+ Variável</button>
        </div>
      </div>

      <div>
        <label style={labelStyle}>Expressão (use as chaves das variáveis: + - * / ( ))</label>
        <div style={{ display: "flex", gap: 6 }}>
          <input value={expressao} onChange={e => setExpressao(e.target.value)} style={campoStyle} placeholder="ex.: coletas / meta_coletas * 100" />
          <button type="button" onClick={salvarExpressao} disabled={salvandoExpressao} style={{
            padding: "8px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", background: "#fff", fontWeight: 700, fontSize: 12, cursor: "pointer", whiteSpace: "nowrap",
          }}>{salvandoExpressao ? "Salvando..." : "Salvar fórmula"}</button>
        </div>
      </div>

      <button type="button" onClick={testarCalculo} disabled={testando} style={{
        marginTop: 10, border: "none", background: "transparent", color: COR, fontWeight: 700, fontSize: 12, cursor: "pointer", padding: 0,
      }}>{testando ? "Calculando..." : `▶ Testar cálculo (${periodoAtual()})`}</button>

      {preview && (
        <div style={{ marginTop: 8, fontSize: 12, padding: 10, background: "#fff", borderRadius: 8, border: "1px solid #F1F5F9" }}>
          {preview.resultado != null ? (
            <div style={{ color: "#059669", fontWeight: 800 }}>Resultado: {preview.resultado}</div>
          ) : (
            <div style={{ color: "#D97706", fontWeight: 700 }}>{preview.erro}</div>
          )}
          {preview.variaveis?.map(v => (
            <div key={v.id} style={{ color: "#64748B", fontSize: 11 }}>{v.label}: {v.pendente ? "sem valor" : v.valor}</div>
          ))}
        </div>
      )}

      {erro && <div style={{ color: "#DC2626", fontSize: 11.5, marginTop: 8 }}>⚠ {erro}</div>}
    </div>
  );
}

function ModalIndicador({ indicador, setores, onFechar, onSalvar }) {
  const [form, setForm] = useState({
    setor: indicador?.setor || "",
    indicador: indicador?.indicador || "",
    objetivo: indicador?.objetivo || "",
    formula: indicador?.formula || "",
    meta: indicador?.meta || "",
    periodicidade: indicador?.periodicidade || "Mensal",
    responsavel: indicador?.responsavel || "",
  });
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);

  const campo = (k) => (e) => setForm(prev => ({ ...prev, [k]: e.target.value }));

  const salvar = async () => {
    if (!form.setor.trim() || !form.indicador.trim()) { setErro("Setor e indicador são obrigatórios."); return; }
    setSalvando(true); setErro(null);
    try {
      await onSalvar(form);
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }} onClick={onFechar}>
      <div style={{ background: "#fff", borderRadius: 16, padding: 24, width: 480, maxWidth: "92vw", maxHeight: "88vh", overflowY: "auto" }} onClick={e => e.stopPropagation()}>
        <div style={{ fontSize: 16, fontWeight: 900, color: "#0F172A", marginBottom: 16 }}>
          {indicador ? "Editar indicador" : "Novo indicador"}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div>
            <label style={labelStyle}>Setor *</label>
            <input list="setores-sugestoes" value={form.setor} onChange={campo("setor")} style={campoStyle} placeholder="Ex.: Laboratório" />
            <datalist id="setores-sugestoes">
              {setores.map(s => <option key={s} value={s} />)}
            </datalist>
          </div>
          <div>
            <label style={labelStyle}>Indicador *</label>
            <input value={form.indicador} onChange={campo("indicador")} style={campoStyle} placeholder="Nome do indicador" />
          </div>
          <div>
            <label style={labelStyle}>Objetivo</label>
            <input value={form.objetivo} onChange={campo("objetivo")} style={campoStyle} placeholder="O que ele mede" />
          </div>
          <div>
            <label style={labelStyle}>Fórmula / Critério</label>
            <input value={form.formula} onChange={campo("formula")} style={campoStyle} placeholder="Como calcular" />
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <div>
              <label style={labelStyle}>Meta sugerida</label>
              <input value={form.meta} onChange={campo("meta")} style={campoStyle} />
            </div>
            <div>
              <label style={labelStyle}>Periodicidade</label>
              <select value={form.periodicidade} onChange={campo("periodicidade")} style={campoStyle}>
                <option>Diário</option>
                <option>Diário/Mensal</option>
                <option>Semanal</option>
                <option>Semanal/Mensal</option>
                <option>Mensal</option>
                <option>Mensal/Trimestral</option>
                <option>Trimestral</option>
              </select>
            </div>
          </div>
          <div>
            <label style={labelStyle}>Responsável</label>
            <input value={form.responsavel} onChange={campo("responsavel")} style={campoStyle} placeholder="Quem acompanha o indicador" />
          </div>
        </div>

        {indicador?.id && <SecaoFormula indicadorId={indicador.id} expressaoInicial={indicador.expressao} />}

        {erro && <div style={{ color: "#DC2626", fontSize: 12.5, marginTop: 12 }}>⚠ {erro}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 20, justifyContent: "flex-end" }}>
          <button onClick={onFechar} style={{ padding: "9px 16px", borderRadius: 10, border: "1.5px solid #E2E8F0", background: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer" }}>Cancelar</button>
          <button onClick={salvar} disabled={salvando} style={{
            padding: "9px 18px", borderRadius: 10, border: "none",
            background: salvando ? "#CBD5E1" : `linear-gradient(135deg,${COR},${COR2})`,
            color: "#fff", fontWeight: 800, fontSize: 13, cursor: salvando ? "not-allowed" : "pointer",
          }}>{salvando ? "Salvando..." : "Salvar"}</button>
        </div>
      </div>
    </div>
  );
}

function ModalResultado({ indicador, periodo, usuario, onFechar, onSalvar }) {
  const temFormula = !!indicador.expressao;
  const [resultado, setResultado] = useState(indicador.resultado || "");
  const [status, setStatus] = useState(indicador.status || "");
  const [planoAcao, setPlanoAcao] = useState(indicador.plano_acao || "");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState(null);

  const [variaveis, setVariaveis] = useState(null);
  const [valoresManuais, setValoresManuais] = useState({});
  const [calc, setCalc] = useState(null);
  const [calculando, setCalculando] = useState(false);

  const recalcular = useCallback(() => {
    if (!temFormula) return;
    setCalculando(true);
    fetch(`${API}/api/indicadores/${indicador.id}/calcular?periodo=${periodo}`)
      .then(r => r.json())
      .then(d => {
        setCalc(d);
        setVariaveis(d.variaveis);
        const manuais = {};
        d.variaveis.forEach(v => { if (v.tipo === "manual") manuais[v.id] = v.valor ?? ""; });
        setValoresManuais(prev => ({ ...manuais, ...prev }));
        if (d.resultado != null) setResultado(String(d.resultado));
      })
      .catch(() => setErro("Não foi possível calcular."))
      .finally(() => setCalculando(false));
  }, [indicador.id, periodo, temFormula]);

  useEffect(() => { recalcular(); }, [recalcular]);

  const salvarVariaveisECalcular = async () => {
    setCalculando(true); setErro(null);
    try {
      for (const v of variaveis) {
        if (v.tipo !== "manual") continue;
        const valor = valoresManuais[v.id];
        await fetch(`${API}/api/indicadores/variaveis/${v.id}/valor`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ periodo, valor: valor === "" ? null : Number(valor), usuario }),
        });
      }
      const resp = await fetch(`${API}/api/indicadores/${indicador.id}/calcular?periodo=${periodo}`);
      const d = await resp.json();
      setCalc(d);
      setVariaveis(d.variaveis);
      if (d.resultado != null) setResultado(String(d.resultado));
      return d;
    } finally {
      setCalculando(false);
    }
  };

  const salvar = async () => {
    setSalvando(true); setErro(null);
    try {
      let resultadoFinal = resultado;
      if (temFormula) {
        const d = await salvarVariaveisECalcular();
        if (d.resultado == null) { setErro(d.erro || "Ainda há variáveis sem valor — não dá pra calcular o resultado."); setSalvando(false); return; }
        resultadoFinal = String(d.resultado);
      }
      await onSalvar({ resultado: resultadoFinal, status, plano_acao: planoAcao });
    } catch (e) {
      setErro(String(e.message || e));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(15,23,42,.45)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }} onClick={onFechar}>
      <div style={{ background: "#fff", borderRadius: 16, padding: 24, width: 460, maxWidth: "92vw" }} onClick={e => e.stopPropagation()}>
        <div style={{ fontSize: 15, fontWeight: 900, color: "#0F172A" }}>{indicador.indicador}</div>
        <div style={{ fontSize: 12, color: "#94A3B8", marginBottom: 4 }}>período {periodo}</div>
        {indicador.meta && <div style={{ fontSize: 12, color: "#64748B", marginBottom: 16 }}>Meta: {indicador.meta}</div>}

        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {temFormula ? (
            <div>
              <label style={labelStyle}>Cálculo automático</label>
              {(variaveis || []).map(v => (
                <div key={v.id} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span style={{ fontSize: 12, color: "#334155", flex: 1 }}>{v.label}</span>
                  {v.tipo === "automatico" ? (
                    <span style={{ fontSize: 12.5, fontWeight: 800, color: "#0369A1", minWidth: 80, textAlign: "right" }}>{v.valor ?? "—"}</span>
                  ) : (
                    <input type="number" value={valoresManuais[v.id] ?? ""} onChange={e => setValoresManuais(prev => ({ ...prev, [v.id]: e.target.value }))}
                      style={{ ...campoStyle, width: 90, textAlign: "right" }} />
                  )}
                </div>
              ))}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 8, paddingTop: 8, borderTop: "1px solid #F1F5F9" }}>
                <button type="button" onClick={salvarVariaveisECalcular} disabled={calculando} style={{ border: "none", background: "transparent", color: COR, fontWeight: 700, fontSize: 11.5, cursor: "pointer", padding: 0 }}>
                  {calculando ? "Calculando..." : "↻ Recalcular"}
                </button>
                <span style={{ fontSize: 14, fontWeight: 900, color: calc?.resultado != null ? "#059669" : "#D97706" }}>
                  {calc?.resultado != null ? `= ${calc.resultado}` : (calc?.erro || "calculando...")}
                </span>
              </div>
            </div>
          ) : (
            <div>
              <label style={labelStyle}>Resultado do período</label>
              <input value={resultado} onChange={e => setResultado(e.target.value)} style={campoStyle} placeholder="Ex.: 92%, 34 exames..." />
            </div>
          )}
          <div>
            <label style={labelStyle}>Status</label>
            <div style={{ display: "flex", gap: 8 }}>
              {STATUS_OPCOES.map(s => (
                <button key={s.valor} onClick={() => setStatus(s.valor)} type="button" style={{
                  flex: 1, padding: "8px 6px", borderRadius: 8, fontSize: 11.5, fontWeight: 800, cursor: "pointer",
                  border: status === s.valor ? `2px solid ${s.cor}` : "1.5px solid #E2E8F0",
                  background: status === s.valor ? s.bg : "#fff", color: status === s.valor ? s.cor : "#94A3B8",
                }}>{s.label}</button>
              ))}
            </div>
          </div>
          <div>
            <label style={labelStyle}>Plano de ação {status && status !== "dentro_meta" ? "(recomendado)" : ""}</label>
            <textarea value={planoAcao} onChange={e => setPlanoAcao(e.target.value)} rows={3} style={{ ...campoStyle, resize: "vertical", fontFamily: "inherit" }} placeholder="Ação corretiva quando necessário" />
          </div>
        </div>

        {erro && <div style={{ color: "#DC2626", fontSize: 12.5, marginTop: 12 }}>⚠ {erro}</div>}

        <div style={{ display: "flex", gap: 8, marginTop: 20, justifyContent: "flex-end" }}>
          <button onClick={onFechar} style={{ padding: "9px 16px", borderRadius: 10, border: "1.5px solid #E2E8F0", background: "#fff", fontWeight: 700, fontSize: 13, cursor: "pointer" }}>Cancelar</button>
          <button onClick={salvar} disabled={salvando} style={{
            padding: "9px 18px", borderRadius: 10, border: "none",
            background: salvando ? "#CBD5E1" : `linear-gradient(135deg,${COR},${COR2})`,
            color: "#fff", fontWeight: 800, fontSize: 13, cursor: salvando ? "not-allowed" : "pointer",
          }}>{salvando ? "Salvando..." : "Salvar lançamento"}</button>
        </div>
      </div>
    </div>
  );
}

// Faixa de 12 quadradinhos coloridos por status — "gráfico" universal que
// funciona mesmo com `resultado` sendo texto livre (não dá pra plotar linha
// numérica confiável quando um indicador é "87 exames" e outro é "92%").
function TimelineStatus({ historico }) {
  return (
    <div style={{ display: "flex", gap: 3 }}>
      {historico.map(h => {
        const st = statusInfo(h.status);
        return (
          <div key={h.periodo} title={`${mesLabel(h.periodo)}: ${h.resultado ?? "sem lançamento"}`} style={{
            width: 12, height: 16, borderRadius: 3, background: st.cor,
            opacity: h.status ? 1 : 0.25,
          }} />
        );
      })}
    </div>
  );
}

function DonutStatus({ indicadores }) {
  const dados = useMemo(() => {
    const contagem = { dentro_meta: 0, atencao: 0, fora_meta: 0, sem_lancamento: 0 };
    indicadores.forEach(i => { contagem[i.status || "sem_lancamento"]++; });
    return [...STATUS_OPCOES, SEM_LANCAMENTO].map(s => ({ name: s.label, value: contagem[s.valor], cor: s.cor })).filter(d => d.value > 0);
  }, [indicadores]);

  if (indicadores.length === 0) return null;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
      <div style={{ width: 180, height: 180 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie data={dados} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75} paddingAngle={2}>
              {dados.map((d, i) => <Cell key={i} fill={d.cor} />)}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {[...STATUS_OPCOES, SEM_LANCAMENTO].map(s => {
          const qtd = indicadores.filter(i => (i.status || "sem_lancamento") === s.valor).length;
          return (
            <div key={s.valor} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}>
              <div style={{ width: 10, height: 10, borderRadius: 3, background: s.cor }} />
              <span style={{ color: "#334155" }}>{s.label}</span>
              <span style={{ fontWeight: 800, color: "#0F172A" }}>{qtd}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TelaSetores({ setores, resumoPorSetor, onEscolher, onVoltar }) {
  return (
    <div>
      <button onClick={onVoltar} style={{ border: "none", background: "transparent", color: COR, fontWeight: 700, fontSize: 13, cursor: "pointer", marginBottom: 14, padding: 0 }}>← Voltar</button>
      <div style={{ fontSize: 15, fontWeight: 800, color: "#0F172A", marginBottom: 14 }}>Escolha o setor</div>
      {setores.length === 0 ? (
        <Card style={{ padding: 40, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>
          Nenhum setor liberado para o seu usuário ainda. Peça para um administrador liberar em Permissões.
        </Card>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 14 }}>
          {setores.map(s => {
            const r = resumoPorSetor[s] || { total: 0, dentro_meta: 0, atencao: 0, fora_meta: 0 };
            return (
              <Card key={s} style={{ padding: 18, cursor: "pointer" }}>
                <div onClick={() => onEscolher(s)}>
                  <div style={{ fontSize: 14, fontWeight: 800, color: "#0F172A", marginBottom: 10 }}>{s}</div>
                  <div style={{ fontSize: 11, color: "#94A3B8", marginBottom: 10 }}>{r.total} indicador{r.total !== 1 ? "es" : ""}</div>
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                    {r.dentro_meta > 0 && <span style={{ fontSize: 10.5, fontWeight: 800, color: "#059669", background: "#ECFDF5", padding: "3px 8px", borderRadius: 99 }}>{r.dentro_meta} ok</span>}
                    {r.atencao > 0 && <span style={{ fontSize: 10.5, fontWeight: 800, color: "#D97706", background: "#FFFBEB", padding: "3px 8px", borderRadius: 99 }}>{r.atencao} atenção</span>}
                    {r.fora_meta > 0 && <span style={{ fontSize: 10.5, fontWeight: 800, color: "#DC2626", background: "#FEF2F2", padding: "3px 8px", borderRadius: 99 }}>{r.fora_meta} fora</span>}
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function TelaDashboardSetor({ setor, periodo, setPeriodo, usuario, onVoltar }) {
  const [indicadores, setIndicadores] = useState([]);
  const [setores, setSetores] = useState([]);
  const [carregando, setCarregando] = useState(false);
  const [modalIndicador, setModalIndicador] = useState(null);
  const [modalResultado, setModalResultado] = useState(null);
  const [erro, setErro] = useState(null);

  const carregar = useCallback(() => {
    setCarregando(true);
    fetch(`${API}/api/indicadores/dashboard-setor?setor=${encodeURIComponent(setor)}&periodo=${periodo}`)
      .then(r => r.json()).then(setIndicadores).catch(() => setIndicadores([]))
      .finally(() => setCarregando(false));
  }, [setor, periodo]);

  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => {
    fetch(`${API}/api/indicadores/setores`).then(r => r.json()).then(setSetores).catch(() => setSetores([]));
  }, []);

  const salvarIndicador = async (form) => {
    const editando = modalIndicador && modalIndicador.id;
    const url = editando ? `${API}/api/indicadores/${modalIndicador.id}` : `${API}/api/indicadores`;
    const resp = await fetch(url, {
      method: editando ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Erro ao salvar indicador.");
    setModalIndicador(null);
    carregar();
  };

  const excluirIndicador = async (ind) => {
    if (!window.confirm(`Remover o indicador "${ind.indicador}"? O histórico de resultados já lançado será preservado.`)) return;
    setErro(null);
    try {
      const resp = await fetch(`${API}/api/indicadores/${ind.id}`, { method: "DELETE" });
      if (!resp.ok) { const d = await resp.json(); throw new Error(d.detail || "Erro ao remover."); }
      carregar();
    } catch (e) {
      setErro(String(e.message || e));
    }
  };

  const salvarResultado = async (campos) => {
    const resp = await fetch(`${API}/api/indicadores/${modalResultado.id}/resultados`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ periodo, usuario, ...campos }),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.detail || "Erro ao lançar resultado.");
    setModalResultado(null);
    carregar();
  };

  return (
    <div>
      <button onClick={onVoltar} style={{ border: "none", background: "transparent", color: COR, fontWeight: 700, fontSize: 13, cursor: "pointer", marginBottom: 14, padding: 0 }}>← Setores</button>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 14 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 900, color: "#0F172A" }}>{setor}</div>
          <div style={{ fontSize: 12, color: "#94A3B8" }}>Indicadores de gestão</div>
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "flex-end" }}>
          <div>
            <label style={labelStyle}>Período</label>
            <input type="month" value={periodo} onChange={e => setPeriodo(e.target.value)} style={campoStyle} />
          </div>
          <button onClick={() => setModalIndicador({})} style={{
            padding: "9px 16px", borderRadius: 10, border: "none",
            background: `linear-gradient(135deg,${COR},${COR2})`, color: "#fff", fontWeight: 800, fontSize: 13, cursor: "pointer",
            height: 37,
          }}>+ Novo indicador</button>
        </div>
      </div>

      {erro && (
        <div style={{ background: "#FEF2F2", border: "1px solid #FECACA", color: "#DC2626", borderRadius: 10, padding: "10px 14px", fontSize: 12.5, marginBottom: 12 }}>
          ⚠ {erro}
        </div>
      )}

      {carregando ? (
        <Card style={{ padding: 40, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Carregando...</Card>
      ) : indicadores.length === 0 ? (
        <Card style={{ padding: 40, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>Nenhum indicador cadastrado nesse setor ainda.</Card>
      ) : (
        <>
          <Card style={{ padding: 20, marginBottom: 14 }}>
            <div style={{ fontSize: 12.5, fontWeight: 800, color: "#64748B", marginBottom: 12 }}>STATUS NO PERÍODO</div>
            <DonutStatus indicadores={indicadores} />
          </Card>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {indicadores.map(ind => {
              const st = statusInfo(ind.status);
              return (
                <Card key={ind.id} style={{ padding: 16 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                    <div style={{ flex: 1, minWidth: 220 }}>
                      <div style={{ fontSize: 13.5, fontWeight: 800, color: "#0F172A" }}>{ind.indicador}</div>
                      <div style={{ fontSize: 11, color: "#94A3B8" }}>
                        {ind.meta ? `Meta: ${ind.meta}` : ""}{ind.periodicidade ? ` · ${ind.periodicidade}` : ""}{ind.responsavel ? ` · ${ind.responsavel}` : ""}
                      </div>
                      {ind.plano_acao && <div style={{ fontSize: 11, color: "#B45309", marginTop: 4 }}>Plano de ação: {ind.plano_acao}</div>}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{ fontSize: 12.5, color: "#334155", textAlign: "right", minWidth: 70 }}>{ind.resultado || "—"}</div>
                      <span style={{ fontSize: 10.5, fontWeight: 800, color: st.cor, background: st.bg, padding: "3px 10px", borderRadius: 99, whiteSpace: "nowrap" }}>{st.label}</span>
                      <button onClick={() => setModalResultado(ind)} style={{
                        border: "none", background: `${COR}15`, color: COR, cursor: "pointer", fontSize: 11.5, fontWeight: 700,
                        padding: "7px 12px", borderRadius: 8, whiteSpace: "nowrap",
                      }}>Lançar</button>
                      <button onClick={() => setModalIndicador(ind)} title="Editar indicador" style={{ border: "none", background: "transparent", color: "#94A3B8", cursor: "pointer", fontSize: 14, padding: "4px 6px" }}>✎</button>
                      <button onClick={() => excluirIndicador(ind)} title="Remover indicador" style={{ border: "none", background: "transparent", color: "#94A3B8", cursor: "pointer", fontSize: 14, padding: "4px 6px" }}>🗑</button>
                    </div>
                  </div>
                  <div style={{ marginTop: 10 }}>
                    <TimelineStatus historico={ind.historico} />
                  </div>
                </Card>
              );
            })}
          </div>
        </>
      )}

      {modalIndicador !== null && (
        <ModalIndicador
          indicador={modalIndicador.id ? modalIndicador : (modalIndicador.setor ? null : { setor })}
          setores={setores}
          onFechar={() => setModalIndicador(null)}
          onSalvar={salvarIndicador}
        />
      )}
      {modalResultado !== null && (
        <ModalResultado
          indicador={modalResultado}
          periodo={periodo}
          usuario={usuario}
          onFechar={() => setModalResultado(null)}
          onSalvar={salvarResultado}
        />
      )}
    </div>
  );
}

export default function Gestao() {
  const { user, podeVer } = useAuth();
  const usuario = user?.login || "";

  const [view, setView] = useState("landing"); // landing | setores | dashboard
  const [setorAtual, setSetorAtual] = useState(null);
  const [periodo, setPeriodo] = useState(periodoAtual());
  const [todosSetores, setTodosSetores] = useState([]);
  const [resumo, setResumo] = useState([]);

  useEffect(() => {
    fetch(`${API}/api/indicadores/setores`).then(r => r.json()).then(setTodosSetores).catch(() => setTodosSetores([]));
  }, []);

  useEffect(() => {
    if (view !== "setores") return;
    fetch(`${API}/api/indicadores?periodo=${periodo}`).then(r => r.json()).then(setResumo).catch(() => setResumo([]));
  }, [view, periodo]);

  const setoresPermitidos = useMemo(
    () => todosSetores.filter(s => podeVer?.(`indicadores_${slugSetor(s)}`)),
    [todosSetores, podeVer]
  );

  const resumoPorSetor = useMemo(() => {
    const mapa = {};
    resumo.forEach(i => {
      if (!mapa[i.setor]) mapa[i.setor] = { total: 0, dentro_meta: 0, atencao: 0, fora_meta: 0 };
      mapa[i.setor].total++;
      if (i.status === "dentro_meta") mapa[i.setor].dentro_meta++;
      if (i.status === "atencao") mapa[i.setor].atencao++;
      if (i.status === "fora_meta") mapa[i.setor].fora_meta++;
    });
    return mapa;
  }, [resumo]);

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{
        background: `linear-gradient(135deg, ${COR} 0%, ${COR2} 100%)`,
        borderRadius: 20, padding: "24px 30px", marginBottom: 18, color: "#fff",
      }}>
        <div style={{ fontSize: 20, fontWeight: 900 }}>📊 Gestão</div>
        <div style={{ fontSize: 13, opacity: .85 }}>Indicadores de gestão por setor</div>
      </div>

      {view === "landing" && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 14 }}>
          <Card style={{ padding: 24, cursor: "pointer" }}>
            <div onClick={() => setView("setores")}>
              <div style={{ fontSize: 30, marginBottom: 8 }}>📈</div>
              <div style={{ fontSize: 15, fontWeight: 800, color: "#0F172A" }}>Indicadores</div>
              <div style={{ fontSize: 12, color: "#94A3B8", marginTop: 4 }}>Cadastro e acompanhamento de indicadores por setor</div>
            </div>
          </Card>
        </div>
      )}

      {view === "setores" && (
        <TelaSetores
          setores={setoresPermitidos}
          resumoPorSetor={resumoPorSetor}
          onEscolher={(s) => { setSetorAtual(s); setView("dashboard"); }}
          onVoltar={() => setView("landing")}
        />
      )}

      {view === "dashboard" && setorAtual && (
        <TelaDashboardSetor
          setor={setorAtual}
          periodo={periodo}
          setPeriodo={setPeriodo}
          usuario={usuario}
          onVoltar={() => setView("setores")}
        />
      )}
    </div>
  );
}
