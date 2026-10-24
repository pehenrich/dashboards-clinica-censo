import { useState, useEffect, useCallback } from "react";
import { Tooltip, ResponsiveContainer, Treemap } from "recharts";

const API = `${window.location.protocol}//${window.location.host}`;
const COR = "#F97316";
const COR2 = "#C2410C";

const Card = ({ children, style }) => (
  <div style={{
    background: "#fff", borderRadius: 18,
    boxShadow: "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
    ...style,
  }}>
    {children}
  </div>
);

function InfoTip({ texto }) {
  const [show, setShow] = useState(false);
  return (
    <span
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
      onClick={(e) => { e.stopPropagation(); setShow(s => !s); }}
      style={{ position: "relative", display: "inline-flex", marginLeft: 5 }}
    >
      <span style={{
        display: "inline-flex", alignItems: "center", justifyContent: "center",
        width: 13, height: 13, borderRadius: "50%", background: "#94A3B8", color: "#fff",
        fontSize: 9, fontWeight: 800, cursor: "help", userSelect: "none", fontStyle: "normal",
      }}>i</span>
      {show && (
        <span style={{
          position: "absolute", bottom: "130%", left: 0, transform: "translateX(-10%)",
          background: "#0F172A", color: "#F1F5F9", fontSize: 11, fontWeight: 500, lineHeight: 1.45,
          padding: "9px 11px", borderRadius: 8, width: 250, zIndex: 80,
          boxShadow: "0 6px 18px rgba(0,0,0,.3)", textAlign: "left", textTransform: "none", letterSpacing: "normal",
        }}>{texto}</span>
      )}
    </span>
  );
}

function corPorNivel(aguardando) {
  if (aguardando >= 15) return "#DC2626";
  if (aguardando >= 8)  return "#D97706";
  if (aguardando > 0)   return "#059669";
  return "#94A3B8";
}

// Cor por tempo de espera (em vez de quantidade) — usado no treemap, onde o
// tamanho do bloco já mostra a quantidade, então a cor fica livre pra mostrar
// outra dimensão (urgência da espera).
function corPorEspera(min) {
  if (min >= 60) return "#B91C1C";
  if (min >= 30) return "#DC2626";
  if (min >= 15) return "#F59E0B";
  return "#10B981";
}

// Texto sempre com contorno escuro (text-shadow em várias direções) pra
// garantir leitura em cima de qualquer cor do treemap (verde, âmbar, vermelho).
const SOMBRA_TEXTO = "0 1px 2px rgba(0,0,0,.85), 0 -1px 2px rgba(0,0,0,.6), 1px 0 2px rgba(0,0,0,.6), -1px 0 2px rgba(0,0,0,.6)";

function BlocoTreemap({ x, y, width, height, nome, aguardando, esperaMedia, ativo, onClick }) {
  const minusculo = width < 26 || height < 20;
  const pequeno = width < 90 || height < 44;
  return (
    <g onClick={onClick} style={{ cursor: "pointer" }}>
      <rect x={x} y={y} width={width} height={height}
        fill={corPorEspera(esperaMedia)} stroke="#fff" strokeWidth={2}
        rx={6}
        style={{ filter: ativo ? "brightness(1.15)" : "none" }} />
      {ativo && (
        <rect x={x + 1.5} y={y + 1.5} width={width - 3} height={height - 3}
          fill="none" stroke="#0F172A" strokeWidth={2.5} rx={5} />
      )}
      {minusculo ? null : pequeno ? (
        // Bloco pequeno demais pro nome caber: mostra só a quantidade,
        // grande e centralizada, pra dar pra identificar sem precisar passar o mouse.
        <text x={x + width / 2} y={y + height / 2 + 5} fontSize={Math.min(17, height / 2.2)} fontWeight={900}
          fill="#fff" textAnchor="middle" style={{ pointerEvents: "none", textShadow: SOMBRA_TEXTO }}>
          {aguardando}
        </text>
      ) : (
        <>
          <text x={x + 10} y={y + 20} fontSize={13} fontWeight={800} fill="#fff" style={{ pointerEvents: "none", textShadow: SOMBRA_TEXTO }}>
            {nome.length > (width / 7) ? nome.slice(0, Math.max(3, Math.floor(width / 7))) + "…" : nome}
          </text>
          <text x={x + 10} y={y + height - 10} fontSize={12} fontWeight={800} fill="#fff" style={{ pointerEvents: "none", textShadow: SOMBRA_TEXTO }}>
            {aguardando} aguardando
          </text>
          {height > 58 && (
            <text x={x + 10} y={y + 39} fontSize={11} fontWeight={700} fill="#fff" style={{ pointerEvents: "none", textShadow: SOMBRA_TEXTO }}>
              espera {Math.round(esperaMedia)} min
            </text>
          )}
        </>
      )}
    </g>
  );
}

// O Treemap do Recharts sempre inclui um nó-raiz (depth 0) representando a
// área toda — só os nós depth>=1 (as filas de verdade) devem virar bloco.
function BlocoTreemapWrapper({ filaSelecionada, onSelecionar, depth, x, y, width, height, name, fila_cod, aguardando, espera_media_min }) {
  if (depth === 0) return null;
  return (
    <BlocoTreemap
      x={x} y={y} width={width} height={height}
      nome={name} aguardando={aguardando} esperaMedia={espera_media_min}
      ativo={filaSelecionada === fila_cod}
      onClick={() => onSelecionar(fila_cod)}
    />
  );
}

// Uma linha de métrica dentro do card de setor: rótulo, valor em minutos e
// uma barrinha horizontal (escala relativa ao maior valor entre todos os
// setores pra essa mesma métrica) pra comparação visual rápida.
function MetricaBarra({ icone, label, valorMin, maxEscala, sublinha, cor }) {
  const semDado = valorMin == null;
  const pct = semDado ? 0 : Math.max(4, Math.min(100, (valorMin / Math.max(1, maxEscala)) * 100));
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 3 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#64748B", display: "flex", alignItems: "center", gap: 5 }}>
          <span style={{ fontSize: 12 }}>{icone}</span>{label}
        </span>
        <span style={{ fontSize: 13, fontWeight: 900, color: semDado ? "#CBD5E1" : cor }}>
          {semDado ? "—" : `${Math.round(valorMin)} min`}
        </span>
      </div>
      <div style={{ background: "#F1F5F9", borderRadius: 99, height: 7, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: semDado ? "#E2E8F0" : cor, borderRadius: 99, transition: "width .4s" }} />
      </div>
      {sublinha && <div style={{ fontSize: 10, color: "#B6C0CC", marginTop: 2 }}>{sublinha}</div>}
    </div>
  );
}

function SetorCard({ s, maxEspera, maxEsperaTotal, maxOs }) {
  return (
    <Card style={{ padding: "16px 18px", border: "1.5px solid #F1F5F9" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <span style={{ fontSize: 13.5, fontWeight: 800, color: "#0F172A" }}>{s.setor_nome}</span>
        <span style={{
          fontSize: 11, fontWeight: 900, color: "#fff", background: corPorNivel(s.aguardando),
          padding: "3px 10px", borderRadius: 99,
        }}>{s.aguardando} aguardando</span>
      </div>
      <MetricaBarra icone="⏱️" label="Espera ao vivo (quem ainda aguarda)" valorMin={s.espera_media_min} maxEscala={maxEspera} cor="#F97316" />
      <MetricaBarra icone="📅" label="Espera média do dia (todos)" valorMin={s.espera_total_media_min} maxEscala={maxEsperaTotal} cor="#7C3AED"
        sublinha={s.total_dia_considerado ? `${s.total_dia_considerado} atendimento(s) considerado(s) hoje` : "sem atendimentos hoje ainda"} />
      <MetricaBarra icone="📋" label="Abertura de OS" valorMin={s.abertura_os_media_min} maxEscala={maxOs} cor="#2563EB"
        sublinha={s.com_os_aberta ? `${s.com_os_aberta} com OS aberta` : "sem OS aberta ainda"} />
    </Card>
  );
}

export default function FluxoFilas() {
  const [resumo, setResumo] = useState(null);
  const [carregandoResumo, setCarregandoResumo] = useState(true);
  const [filaSelecionada, setFilaSelecionada] = useState(null);
  const [detalhe, setDetalhe] = useState(null);
  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);
  const origem = "totem"; // fila só do totem (pedido explícito do usuário — não precisa mais do toggle "Todas")
  const [porSetor, setPorSetor] = useState(null);
  const [carregandoSetor, setCarregandoSetor] = useState(true);

  const carregarPorSetor = useCallback((silencioso) => {
    if (!silencioso) setCarregandoSetor(true);
    fetch(`${API}/api/fila/por-setor?origem=${origem}`)
      .then(r => r.json())
      .then(d => setPorSetor(d.setores || []))
      .catch(() => setPorSetor(null))
      .finally(() => setCarregandoSetor(false));
  }, [origem]);

  useEffect(() => {
    carregarPorSetor(false);
    const id = setInterval(() => carregarPorSetor(true), 20000);
    return () => clearInterval(id);
  }, [carregarPorSetor]);

  const carregarResumo = useCallback((silencioso) => {
    if (!silencioso) setCarregandoResumo(true);
    fetch(`${API}/api/fila/resumo?origem=${origem}`)
      .then(r => r.json())
      .then(d => {
        setResumo(d);
        // Mantém a fila selecionada (ou escolhe a mais cheia no primeiro load)
        setFilaSelecionada(prev => {
          if (prev && (d.filas || []).some(f => f.fila_cod === prev)) return prev;
          return d.filas?.[0]?.fila_cod ?? null;
        });
      })
      .catch(() => setResumo(null))
      .finally(() => setCarregandoResumo(false));
  }, [origem]);

  useEffect(() => {
    carregarResumo(false);
    const id = setInterval(() => carregarResumo(true), 20000);
    return () => clearInterval(id);
  }, [carregarResumo]);

  useEffect(() => {
    if (filaSelecionada == null) { setDetalhe(null); return; }
    setCarregandoDetalhe(true);
    fetch(`${API}/api/fila/detalhe?fila=${filaSelecionada}&origem=${origem}`)
      .then(r => r.json())
      .then(setDetalhe)
      .catch(() => setDetalhe(null))
      .finally(() => setCarregandoDetalhe(false));
  }, [filaSelecionada, origem]);

  // Refresca o detalhe junto com o resumo (mesmo intervalo), sem piscar loading
  useEffect(() => {
    const id = setInterval(() => {
      if (filaSelecionada == null) return;
      fetch(`${API}/api/fila/detalhe?fila=${filaSelecionada}&origem=${origem}`)
        .then(r => r.json()).then(setDetalhe).catch(() => {});
    }, 20000);
    return () => clearInterval(id);
  }, [filaSelecionada, origem]);

  const filas = resumo?.filas || [];
  const total = resumo?.total_aguardando ?? 0;
  const maxAguardando = Math.max(1, ...filas.map(f => f.aguardando));
  const totalPreferenciais = filas.reduce((a, f) => a + (f.preferenciais || 0), 0);
  const filaMaisCheia = filas[0];

  // Agrupa as filas por setor de recepção, pra render um treemap por setor
  // (em vez de um só misturando tudo) — pedido explícito do usuário.
  const gruposPorSetor = Object.values(
    filas.reduce((acc, f) => {
      const cod = f.setor_cod || "?";
      if (!acc[cod]) acc[cod] = { setor_cod: cod, setor_nome: f.setor_nome || cod, filas: [], aguardando: 0 };
      acc[cod].filas.push(f);
      acc[cod].aguardando += f.aguardando;
      return acc;
    }, {})
  ).sort((a, b) => b.aguardando - a.aguardando);

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }}>
      <div style={{
        background: `linear-gradient(135deg, ${COR} 0%, ${COR2} 100%)`,
        borderRadius: 20, padding: "24px 30px", marginBottom: 18, color: "#fff",
        display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10,
      }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 900 }}>📊 Fluxo de Filas</div>
          <div style={{ fontSize: 13, opacity: .85 }}>Quantas senhas estão aguardando agora e em qual fila está maior</div>
        </div>
        <div style={{ fontSize: 12, opacity: .85, textAlign: "right" }}>
          Atualizado às {resumo?.hora_atual || "--:--:--"}<br/>
          <span style={{ opacity: .7 }}>Atualiza automaticamente a cada 20s</span>
        </div>
      </div>

      {/* KPIs */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 14, marginBottom: 18 }}>
        <Card style={{ padding: "18px 20px", display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ fontSize: 26 }}>🧍</span>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase" }}>Aguardando agora</div>
            <div style={{ fontSize: 32, fontWeight: 900, color: "#0F172A" }}>{carregandoResumo ? "…" : total}</div>
          </div>
        </Card>
        <Card style={{ padding: "18px 20px", display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ fontSize: 26 }}>⭐</span>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase" }}>Preferenciais na fila</div>
            <div style={{ fontSize: 32, fontWeight: 900, color: "#DC2626" }}>{carregandoResumo ? "…" : totalPreferenciais}</div>
          </div>
        </Card>
        <Card style={{ padding: "18px 20px", display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ fontSize: 26 }}>🔥</span>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase" }}>Fila com mais gente</div>
            <div style={{ fontSize: 18, fontWeight: 900, color: "#0F172A" }}>
              {carregandoResumo ? "…" : filaMaisCheia
                ? `${filaMaisCheia.fila_nome} (${filaMaisCheia.aguardando})`
                : "Nenhuma fila agora"}
            </div>
          </div>
        </Card>
      </div>

      {/* Gráfico — quais filas estão com mais pacientes, pra ter uma noção visual rápida */}
      <Card style={{ padding: 18, marginBottom: 16 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: "#0F172A" }}>
            Quais filas estão com mais pacientes
          </div>
          <span style={{
            padding: "5px 14px", borderRadius: 20, fontSize: 11.5, fontWeight: 700,
            background: COR, color: "#fff",
          }}>Só Totem</span>
        </div>
        {carregandoResumo ? (
          <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Carregando...</div>
        ) : filas.length === 0 ? (
          <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Ninguém aguardando em nenhuma fila no momento.</div>
        ) : (
          <>
            <div style={{ display: "flex", gap: 14, marginBottom: 10, fontSize: 10.5, color: "#64748B", alignItems: "center", flexWrap: "wrap" }}>
              <span style={{ fontWeight: 700 }}>Tamanho = quantidade aguardando</span>
              <span style={{ fontWeight: 700 }}>Cor = tempo de espera:</span>
              {[["#10B981", "< 15 min"], ["#F59E0B", "15–30 min"], ["#DC2626", "30–60 min"], ["#B91C1C", "60+ min"]].map(([c, l]) => (
                <span key={l} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ width: 10, height: 10, borderRadius: 3, background: c, display: "inline-block" }} />{l}
                </span>
              ))}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 14 }}>
              {gruposPorSetor.map(g => (
                <div key={g.setor_cod} style={{ border: "1.5px solid #F1F5F9", borderRadius: 14, padding: "12px 12px 8px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 800, color: "#0F172A" }}>{g.setor_nome}</span>
                    <span style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8" }}>{g.aguardando} aguardando</span>
                  </div>
                  <ResponsiveContainer width="100%" height={Math.max(130, Math.min(260, g.filas.length * 46))}>
                    <Treemap
                      data={g.filas.map(f => ({ ...f, name: f.fila_nome, size: f.aguardando }))}
                      dataKey="size" aspectRatio={4 / 3} stroke="#fff" isAnimationActive={false}
                      content={
                        <BlocoTreemapWrapper filaSelecionada={filaSelecionada} onSelecionar={setFilaSelecionada} />
                      }
                    >
                      <Tooltip
                        formatter={(v, _n, p) => [`${v} aguardando · espera média ${Math.round(p.payload.espera_media_min)} min`, p.payload.fila_nome]}
                        contentStyle={{ borderRadius: 10, border: "1px solid #E5E7EB", fontSize: 12 }}
                      />
                    </Treemap>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>
          </>
        )}
      </Card>

      {/* Cards por setor — espera ao vivo, espera média do dia todo e abertura de OS */}
      <div style={{ marginBottom: 18 }}>
        <div style={{ fontSize: 13, fontWeight: 800, color: "#0F172A", marginBottom: 4, display: "flex", alignItems: "center" }}>
          Por recepção — espera e abertura de OS
          <InfoTip texto="Espera ao vivo: chegada até agora, só de quem AINDA está na fila (sobe ao longo do dia mesmo indo bem, porque só reflete quem ficou pra trás). Espera média do dia: chegada até ser chamado (ou até a OS abrir, se nunca foi chamado), incluindo quem já foi atendido — essa é a métrica real do dia. Abertura de OS: chegada até a OS abrir, de quem ainda aguarda — ajuda a ver se o gargalo é abrir a OS ou chamar a senha." />
        </div>
        {carregandoSetor ? (
          <Card style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Carregando...</Card>
        ) : !porSetor || porSetor.length === 0 ? (
          <Card style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Ninguém aguardando em nenhum setor no momento.</Card>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 14, marginTop: 10 }}>
            {porSetor.map(s => (
              <SetorCard key={s.setor_cod} s={s}
                maxEspera={Math.max(1, ...porSetor.map(x => x.espera_media_min || 0))}
                maxEsperaTotal={Math.max(1, ...porSetor.map(x => x.espera_total_media_min || 0))}
                maxOs={Math.max(1, ...porSetor.map(x => x.abertura_os_media_min || 0))} />
            ))}
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, alignItems: "start" }}>
        {/* Ranking por fila */}
        <Card style={{ padding: 18 }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: "#0F172A", marginBottom: 12, display: "flex", alignItems: "center" }}>
            Onde estão aguardando
            <InfoTip texto="Espera de quem AINDA está na fila agora (chegada até agora) — diferente do tempo médio histórico do Painel TV e do módulo Recepção, que medem espera de atendimentos já concluídos." />
          </div>
          {carregandoResumo ? (
            <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Carregando...</div>
          ) : filas.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Ninguém aguardando em nenhuma fila no momento.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {filas.map(f => {
                const cor = corPorNivel(f.aguardando);
                const ativo = filaSelecionada === f.fila_cod;
                return (
                  <div key={f.fila_cod} onClick={() => setFilaSelecionada(f.fila_cod)} style={{
                    cursor: "pointer", padding: "10px 12px", borderRadius: 10,
                    border: ativo ? `2px solid ${cor}` : "1.5px solid #F1F5F9",
                    background: ativo ? `${cor}0D` : "#FAFBFC",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color: "#0F172A" }}>
                        {f.fila_nome}
                      </span>
                      <span style={{ fontSize: 15, fontWeight: 900, color: cor }}>{f.aguardando}</span>
                    </div>
                    <div style={{ background: "#F1F5F9", borderRadius: 99, height: 8, overflow: "hidden" }}>
                      <div style={{
                        width: `${Math.max(4, (f.aguardando / maxAguardando) * 100)}%`,
                        height: "100%", background: cor, borderRadius: 99,
                      }}/>
                    </div>
                    <div style={{ fontSize: 11, color: "#94A3B8", marginTop: 4 }}>
                      espera média {Math.round(f.espera_media_min)} min · máxima {f.espera_max_min} min
                      {f.preferenciais > 0 ? ` · ${f.preferenciais} preferencial(is)` : ""}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        {/* Detalhe nominal da fila selecionada */}
        <Card style={{ padding: 18, minHeight: 200 }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: "#0F172A", marginBottom: 12 }}>
            {filaSelecionada != null
              ? `Fila — ${filas.find(f => f.fila_cod === filaSelecionada)?.fila_nome || filaSelecionada}`
              : "Fila"}
          </div>
          {filaSelecionada == null ? (
            <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Selecione uma fila ao lado.</div>
          ) : carregandoDetalhe && !detalhe ? (
            <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Carregando...</div>
          ) : !detalhe || detalhe.fila.length === 0 ? (
            <div style={{ padding: 20, textAlign: "center", color: "#94A3B8", fontSize: 12.5 }}>Ninguém aguardando nessa fila agora.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 480, overflowY: "auto" }}>
              {detalhe.fila.map((p, i) => (
                <div key={i} style={{
                  padding: "9px 12px", borderRadius: 10, background: "#FAFBFC", border: "1px solid #F1F5F9",
                  display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8,
                }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 700, color: "#0F172A", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {p.paciente || "(sem nome)"}
                      {p.preferencial === "S" && <span style={{ fontSize: 9, fontWeight: 800, color: "#DC2626", background: "#FEF2F2", padding: "1px 6px", borderRadius: 99, marginLeft: 6 }}>PREF</span>}
                    </div>
                    <div style={{ fontSize: 11, color: "#94A3B8" }}>
                      {p.senha ? `senha ${p.senha} · ` : ""}{p.prestador}{p.especialidade ? ` (${p.especialidade})` : ""} · chegou {p.chegada}
                    </div>
                  </div>
                  <div style={{
                    fontSize: 12, fontWeight: 800, whiteSpace: "nowrap",
                    color: p.espera_min >= 30 ? "#DC2626" : p.espera_min >= 15 ? "#D97706" : "#059669",
                  }}>
                    {p.espera_min} min
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
