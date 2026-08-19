import { useState, useEffect, Fragment } from "react";
import {
  BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
  PieChart, Pie, LineChart, Line, ComposedChart, LabelList,
} from "recharts";

// Paleta segura para daltonismo (Okabe-Ito) — evita depender de vermelho x
// verde pra distinguir categorias, que é a combinação mais problemática.
const CB = {
  azul: "#0072B2",
  azulClaro: "#56B4E9",
  laranja: "#E69F00",
  vermelhao: "#D55E00",
  verde: "#009E73",
  roxo: "#CC79A7",
  cinza: "#767676",
};

const API = `${window.location.protocol}//${window.location.host}`;

const C = {
  text: "#111827", sub: "#64748B", faint: "#94A3B8", border: "#E5E7EB",
};

function useFetch(path, params = {}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const qs = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== ""))
    );
    fetch(`${API}${path}?${qs}`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [path, JSON.stringify(params)]);

  return { data, loading };
}

const SOMBRA_CARD = "0 1px 2px rgba(15,23,42,.04), 0 6px 18px rgba(15,23,42,.06)";
const sombraGlow = (cor) => `0 1px 2px rgba(15,23,42,.04), 0 8px 20px ${cor}22`;

function Card({ children, title, subtitle, accent }) {
  return (
    <div style={{
      background: "#fff", borderRadius: 18, padding: "20px 22px",
      boxShadow: accent ? sombraGlow(accent) : SOMBRA_CARD, border: "1px solid #F1F5F9",
      position: "relative", overflow: "hidden",
    }}>
      {accent && <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 3.5,
        background: `linear-gradient(90deg, ${accent}, ${accent}99, ${accent})`,
      }} />}
      {title && <div style={{ fontSize: 14.5, fontWeight: 800, color: C.text, letterSpacing: "-.01em" }}>{title}</div>}
      {subtitle && <div style={{ fontSize: 11.5, color: C.faint, marginTop: 2, marginBottom: 12 }}>{subtitle}</div>}
      {children}
    </div>
  );
}

const brl = (v) => v != null
  ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2 }).format(v) : "—";
const brlInteiro = (v) => v != null
  ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }).format(v) : "—";
const brlCompacto = (v) => v != null
  ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", notation: "compact", maximumFractionDigits: 1 }).format(v) : "—";
const brlCompactoInteiro = (v) => v != null
  ? new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", notation: "compact", maximumFractionDigits: 0 }).format(v) : "—";

const CORES_TIPO = { produzido: CB.verde, parcial: CB.azul, previsto: CB.laranja };
const GRADIENTES_TIPO = { produzido: "url(#gradVerde)", parcial: "url(#gradAzul)", previsto: "url(#gradLaranja)" };

// Defs de gradiente reaproveitados em todos os gráficos de barra do módulo
// — dá o acabamento "vidro"/premium sem precisar duplicar a paleta.
const GRADIENTES_SVG = [
  { id: "gradVerde", cor: CB.verde }, { id: "gradAzul", cor: CB.azul },
  { id: "gradLaranja", cor: CB.laranja }, { id: "gradAzulClaro", cor: CB.azulClaro },
  { id: "gradVermelhao", cor: CB.vermelhao }, { id: "gradRoxo", cor: CB.roxo },
  { id: "gradCinza", cor: CB.cinza },
];
function ChartDefs() {
  return (
    <defs>
      {GRADIENTES_SVG.map(g => (
        <linearGradient key={g.id} id={g.id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={g.cor} stopOpacity={1} />
          <stop offset="100%" stopColor={g.cor} stopOpacity={0.62} />
        </linearGradient>
      ))}
    </defs>
  );
}

function KpiCard({ label, valor, cor, destaque, icone, formatar }) {
  return (
    <div style={{
      background: `linear-gradient(160deg, ${cor}${destaque ? "1c" : "0e"} 0%, #fff 65%)`,
      borderRadius: 18, padding: "16px 18px 15px",
      boxShadow: destaque ? sombraGlow(cor) : SOMBRA_CARD, border: `1px solid ${cor}25`,
      position: "relative", overflow: "hidden",
    }}>
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 5,
        background: `linear-gradient(90deg, ${cor}, ${cor}99, ${cor})`,
      }} />
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          width: 24, height: 24, borderRadius: 7, background: `${cor}20`, flexShrink: 0,
          display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12.5,
        }}>{icone || <span style={{ width: 9, height: 9, borderRadius: 3, background: cor, display: "inline-block" }} />}</span>
        <div style={{ fontSize: 10.5, fontWeight: 800, color: "#9CA3AF", textTransform: "uppercase", letterSpacing: ".05em" }}>{label}</div>
      </div>
      <div style={{ fontSize: destaque ? 23 : 19, fontWeight: 900, color: "#111827", marginTop: 8, fontVariantNumeric: "tabular-nums", letterSpacing: "-.01em" }}>{formatar ? formatar(valor) : brl(valor)}</div>
    </div>
  );
}

// Legenda em formato de "chip" bem visível — usada em todo gráfico que
// distingue produzido/em andamento/previsão, sempre com o mesmo código de
// cor (consistência é o que torna um BI fácil de ler rápido).
function LegendaTipos({ itens }) {
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {itens.map((l, i) => (
        <div key={i} style={{
          display: "flex", alignItems: "center", gap: 7, fontSize: 12, fontWeight: 700, color: l.cor,
          background: `${l.cor}14`, border: `1px solid ${l.cor}30`, borderRadius: 99, padding: "5px 12px 5px 8px",
        }}>
          <span style={{
            width: 12, height: 12, borderRadius: "50%", background: l.cor, display: "inline-block",
            boxShadow: `0 0 0 3px ${l.cor}1F`,
          }} />
          {l.label}
        </div>
      ))}
    </div>
  );
}

const LEGENDA_TIPOS_PADRAO = [
  { cor: CB.verde, label: "Já produzido" },
  { cor: CB.azul, label: "Em andamento" },
  { cor: CB.laranja, label: "Previsão" },
];

function GraficoMensal({ meses, titulo, subtitulo }) {
  return (
    <Card accent={CB.azulClaro}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
        <div>
          {titulo && <div style={{ fontSize: 14.5, fontWeight: 800, color: C.text, letterSpacing: "-.01em" }}>{titulo}</div>}
          {subtitulo && <div style={{ fontSize: 11.5, color: C.faint, marginTop: 2 }}>{subtitulo}</div>}
        </div>
        <LegendaTipos itens={LEGENDA_TIPOS_PADRAO} />
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={meses}>
          <ChartDefs />
          <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} axisLine={{ stroke: "#E5E7EB" }} tickLine={false} />
          <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} width={60} axisLine={false} tickLine={false} />
          <Tooltip
            formatter={(v, n, p) => [brl(v), p.payload.tipo_dado === "produzido" ? "Produzido" : p.payload.tipo_dado === "parcial" ? "Em andamento" : "Previsão"]}
            contentStyle={{ borderRadius: 10, border: "1px solid #E5E7EB", fontSize: 12, boxShadow: SOMBRA_CARD }}
            cursor={{ fill: "#F8FAFC" }}
          />
          <Bar dataKey="valor" radius={[6, 6, 0, 0]} maxBarSize={46}>
            {meses.map((m, i) => <Cell key={i} fill={GRADIENTES_TIPO[m.tipo_dado]} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}

// Cabeçalho padrão de cada seção — ícone + título + explicação em linguagem
// simples (o público é o diretor apresentando pros sócios, não analistas),
// com espaço à direita pra filtros específicos daquela seção (ex: setor).
function SectionHeader({ icone, titulo, descricao, children }) {
  return (
    <div style={{
      display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 14,
      marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid #EEF2F7", flexWrap: "wrap",
    }}>
      <div style={{ display: "flex", gap: 12, alignItems: "flex-start", maxWidth: 640 }}>
        {icone && (
          <div style={{
            width: 36, height: 36, borderRadius: 11, background: "linear-gradient(160deg,#F1F5F9,#E9EEF5)",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 17.5, flexShrink: 0,
            boxShadow: "inset 0 0 0 1px rgba(15,23,42,.04)",
          }}>{icone}</div>
        )}
        <div>
          <div style={{ fontSize: 16.5, fontWeight: 800, color: C.text }}>{titulo}</div>
          {descricao && <div style={{ fontSize: 12, color: C.sub, marginTop: 3, lineHeight: 1.4 }}>{descricao}</div>}
        </div>
      </div>
      {children && <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>{children}</div>}
    </div>
  );
}

function Skeleton({ h = 20, w = "100%", radius = 8 }) {
  return (
    <div style={{
      height: h, width: w, borderRadius: radius,
      background: "linear-gradient(90deg,#F1F5F9 25%,#E7ECF3 50%,#F1F5F9 75%)",
      backgroundSize: "200% 100%", animation: "shimmer 1.4s infinite",
    }} />
  );
}

function Carregando({ linhas = 4, grafico = true }) {
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 12, marginBottom: 20 }}>
        {Array.from({ length: linhas }).map((_, i) => <Skeleton key={i} h={78} radius={16} />)}
      </div>
      {grafico && <Skeleton h={260} radius={16} />}
    </div>
  );
}

const estiloSelect = {
  padding: "7px 13px", borderRadius: 10, border: `1px solid ${C.border}`,
  background: "#fff", color: C.text, fontSize: 12.5, fontWeight: 600, cursor: "pointer", outline: "none",
};

const SETORES_FILTRO = [
  { cod: "TODOS", label: "Todos os setores" },
  { cod: "RCN", label: "Recepção Consultórios" },
  { cod: "RDI", label: "Recepção Diagnóstico" },
  { cod: "ROC", label: "Recepção Ocupacional" },
  { cod: "RCI", label: "Recepção Censo Imagem" },
];

const SETORES_RECEPCAO = SETORES_FILTRO.filter(s => s.cod !== "TODOS");

const CNPJ_FILTRO = [
  { cod: "interno", label: "Solicitado Internamente" },
  { cod: "externo", label: "Solicitado Externamente" },
  { cod: "todos", label: "Todos" },
];

function SeletorSetor({ value, onChange, opcoes = SETORES_FILTRO }) {
  return (
    <select value={value} onChange={e => onChange(e.target.value)} style={estiloSelect}>
      {opcoes.map(s => <option key={s.cod} value={s.cod}>{s.label}</option>)}
    </select>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// Painéis — cada um recebe ano/cnpj do filtro global no topo da página;
// "setor" continua local, só faz sentido nos painéis ligados à Hapvida.
// ══════════════════════════════════════════════════════════════════════════

function PainelVisaoGeral({ ano, cnpj }) {
  const [setor, setSetor] = useState("TODOS");
  const { data, loading } = useFetch("/api/financeiro/visao-geral-hapvida", { ano, setor, cnpj });

  return (
    <div>
      <SectionHeader
        icone="📈"
        titulo="Produção Hapvida"
        descricao="Produção total da clínica, participação do Hapvida CECAN e o impacto de retirar as consultas do convênio — mês a mês."
      >
        <SeletorSetor value={setor} onChange={setSetor} />
      </SectionHeader>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(230px,1fr))", gap: 10, marginBottom: 22 }}>
        {[
          { icone: "🏢", cor: CB.cinza, texto: "Produção Total: sempre o valor real (não muda com o CNPJ)" },
          { icone: "⚖️", cor: CB.azul, texto: "Hapvida e Impacto respeitam o filtro de CNPJ" },
          { icone: "🩺", cor: CB.roxo, texto: "Psiquiatria fora do Impacto" },
          { icone: "📉", cor: CB.laranja, texto: "Previsão: média de Mai+Jun+Jul, projetada de forma plana" },
        ].map((n, i) => (
          <div key={i} style={{
            display: "flex", alignItems: "flex-start", gap: 10, fontSize: 11.5, color: C.sub,
            background: "#fff", border: "1px solid #F1F5F9", borderRadius: 14, padding: "11px 13px",
            boxShadow: SOMBRA_CARD, lineHeight: 1.4,
          }}>
            <span style={{
              width: 26, height: 26, borderRadius: 8, background: `${n.cor}18`, flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13,
            }}>{n.icone}</span>
            <span style={{ paddingTop: 3 }}>{n.texto}</span>
          </div>
        ))}
      </div>

      {loading || !data ? <Carregando /> : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12, marginBottom: 20 }}>
            <KpiCard label="Produção Total — Já Produzido" valor={data.producao_total.total_ja_produzido} cor={CB.cinza} destaque />
            <KpiCard label={`Hapvida — Já Produzido (${data.percentual_hapvida_no_ano}% do total)`} valor={data.producao_hapvida.total_ja_produzido} cor={CB.azul} destaque />
            <KpiCard label="Sai (médicos c/ consulta Hapvida) — Já Produzido" valor={data.medicos_com_consulta_hapvida.total_ja_produzido} cor={CB.vermelhao} destaque />
            <KpiCard label="Impacto Retirada das Consultas — Já Produzido" valor={data.impacto_retirada_consultas_hapvida.total_ja_produzido} cor={CB.verde} destaque />
            <KpiCard
              label="% da Produção em Risco (médicos Hapvida)"
              valor={data.medicos_com_consulta_hapvida.total_ja_produzido / data.producao_total.total_ja_produzido * 100}
              formatar={(v) => `${v.toFixed(1)}%`}
              cor={CB.vermelhao}
              destaque
            />
            <KpiCard label="Produção Total — Previsão Out+Nov+Dez" valor={data.producao_total.projecao_out_nov_dez} cor={CB.cinza} />
            <KpiCard label="Hapvida — Previsão Out+Nov+Dez" valor={data.producao_hapvida.projecao_out_nov_dez} cor={CB.azul} />
            <KpiCard label="Impacto Retirada — Previsão Out+Nov+Dez" valor={data.impacto_retirada_consultas_hapvida.projecao_out_nov_dez} cor={CB.verde} />
          </div>

          <Card title="Produção Total x Hapvida — Evolução Mensal" subtitle="Barra cinza = produção total da clínica · barra azul = quanto disso é Hapvida CECAN" accent={CB.azul}>
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={data.meses}>
                <ChartDefs />
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} axisLine={{ stroke: "#E5E7EB" }} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} width={60} axisLine={false} tickLine={false} />
                <Tooltip
                  formatter={(v, n) => [
                    n === "percentual_hapvida" ? `${v}%` : brl(v),
                    n === "producao_total" ? "Produção Total" : n === "producao_hapvida" ? "Hapvida CECAN" : "% Hapvida do Total",
                  ]}
                  contentStyle={{ borderRadius: 10, border: "1px solid #E5E7EB", fontSize: 12, boxShadow: SOMBRA_CARD }}
                  cursor={{ fill: "#F8FAFC" }}
                />
                <Legend
                  iconType="circle" iconSize={11}
                  wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }}
                  payload={[
                    { value: "Produção Total", type: "square", color: CB.cinza },
                    { value: "Hapvida CECAN", type: "square", color: CB.azul },
                  ]}
                />
                <Bar dataKey="producao_total" fill="url(#gradCinza)" radius={[5, 5, 0, 0]} maxBarSize={40} />
                <Bar dataKey="producao_hapvida" fill="url(#gradAzul)" radius={[5, 5, 0, 0]} maxBarSize={40} />
              </ComposedChart>
            </ResponsiveContainer>
          </Card>

          <div style={{ marginTop: 16 }}>
            <Card title="Impacto da Retirada do Hapvida das Consultas — Evolução Mensal" subtitle="Cinza claro = produção total · vermelho = o que sairia (consulta + exames dos médicos que atendem Hapvida) · linha = o que restaria" accent={CB.vermelhao}>
              <ResponsiveContainer width="100%" height={260}>
                <ComposedChart data={data.meses}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} />
                  <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} width={60} />
                  <Tooltip formatter={(v, n) => [brl(v), n === "producao_total" ? "Produção Total" : n === "medicos_com_consulta_hapvida" ? "Sai (médicos c/ consulta Hapvida)" : "Impacto — Restaria"]} />
                  <Legend
                    iconType="circle" iconSize={11}
                    wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }}
                    payload={[
                      { value: "Produção Total", type: "square", color: CB.cinza },
                      { value: "Sai (médicos c/ consulta Hapvida)", type: "square", color: CB.vermelhao },
                      { value: "Restaria", type: "line", color: CB.verde },
                    ]}
                  />
                  <Bar dataKey="producao_total" fill={CB.cinza} radius={[4, 4, 0, 0]} fillOpacity={0.5} />
                  <Bar dataKey="medicos_com_consulta_hapvida" fill={CB.vermelhao} radius={[4, 4, 0, 0]} fillOpacity={0.9} />
                  <Line dataKey="impacto_retirada_consultas" stroke={CB.verde} strokeWidth={2.5} dot={{ r: 3, fill: CB.verde }} />
                </ComposedChart>
              </ResponsiveContainer>
              {(() => {
                const sairiaJa = data.medicos_com_consulta_hapvida.total_ja_produzido;
                const hapJa = data.producao_hapvida.total_ja_produzido;
                const totJa = data.producao_total.total_ja_produzido;
                const foraDoRisco = hapJa - sairiaJa;
                const pctForaDoRisco = hapJa ? (foraDoRisco / hapJa * 100) : 0;
                const pctRisco = totJa ? (sairiaJa / totJa * 100) : 0;
                return (
                  <div style={{
                    marginTop: 12, fontSize: 12.5, lineHeight: 1.5, color: "#334155",
                    background: "#EFF6FF", borderLeft: `3px solid ${CB.azul}`, padding: "10px 14px", borderRadius: 8,
                  }}>
                    🎯 Do total de {brl(hapJa)} que o Hapvida CECAN já produziu no ano, apenas {brl(sairiaJa)} está diretamente
                    ligado aos médicos que fazem consulta pelo convênio — a exposição real ({pctRisco.toFixed(1)}% da produção total)
                    é bem menor que a participação total do Hapvida ({data.percentual_hapvida_no_ano}%). Os outros {brl(foraDoRisco)}{" "}
                    ({pctForaDoRisco.toFixed(0)}% da receita Hapvida) continuariam entrando mesmo nesse cenário de perda.
                  </div>
                );
              })()}
            </Card>
          </div>

          <div style={{ marginTop: 16 }}>
            <Card title="Previsão Detalhada — Outubro / Novembro / Dezembro" subtitle="Média simples de Maio + Junho + Julho, projetada de forma plana" accent={CB.laranja}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: "#F8FAFC" }}>
                    <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}></th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Outubro</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Novembro</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Dezembro</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ["Produção Total", data.producao_total, C.text],
                    ["Hapvida CECAN", data.producao_hapvida, CB.azul],
                    ["Impacto Retirada das Consultas — Restaria", data.impacto_retirada_consultas_hapvida, CB.verde],
                  ].map(([label, t, cor], i) => (
                    <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td style={{ padding: "9px 10px", fontWeight: 700, color: C.text }}>{label}</td>
                      <td style={{ padding: "9px 10px", textAlign: "right" }}>{brl(t.projecao_outubro)}</td>
                      <td style={{ padding: "9px 10px", textAlign: "right" }}>{brl(t.projecao_novembro)}</td>
                      <td style={{ padding: "9px 10px", textAlign: "right" }}>{brl(t.projecao_dezembro)}</td>
                      <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800, color: cor }}>{brl(t.projecao_out_nov_dez)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function PainelHapvidaHonorariosExames({ ano, cnpj }) {
  const [setor, setSetor] = useState("TODOS");
  const { data, loading } = useFetch("/api/financeiro/hapvida-honorarios-exames", { ano, setor, cnpj });
  // Impacto do descredenciamento é sempre da Recepção Consultórios (RCN),
  // independente do filtro de setor selecionado acima pro resto do painel.
  const { data: dataRCN } = useFetch("/api/financeiro/hapvida-honorarios-exames", { ano, setor: "RCN", cnpj });

  return (
    <div>
      <SectionHeader
        icone="🩺"
        titulo="Honorários (Consultas) x Exames Solicitados"
        descricao="Quanto o convênio Hapvida CECAN gera em consultas e em exames pedidos pelos médicos, já produzido no ano e a previsão pro último trimestre."
      >
        <SeletorSetor value={setor} onChange={setSetor} />
      </SectionHeader>

      {loading || !data ? <Carregando /> : (
        <>
          <div style={{
            display: "flex", alignItems: "center", gap: 8, fontSize: 11.5, color: "#92400E",
            background: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 10, padding: "8px 12px", marginBottom: 14,
          }}>
            ℹ️ Previsão: média simples de Maio + Junho + Julho, projetada de forma plana pros meses seguintes — tanto para Honorários (Consultas) quanto para Exames Solicitados.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 12, marginBottom: 20 }}>
            <KpiCard label="Consultas — Total Jan a Jul" valor={data.consulta.total_primeiro_semestre_mais_julho} cor={CB.roxo} />
            <KpiCard label="Exames — Total Jan a Jul" valor={data.exame.total_primeiro_semestre_mais_julho} cor={CB.azul} />
            <KpiCard label="Consultas — Média Jan a Jul" valor={data.consulta.media_primeiro_semestre_mais_julho} cor={CB.roxo} />
            <KpiCard label="Exames — Média (meses c/ produção)" valor={data.exame.media_primeiro_semestre_mais_julho} cor={CB.azulClaro} />
            <KpiCard label="Consultas — Previsão Out+Nov+Dez" valor={data.consulta.projecao_out_nov_dez} cor={CB.laranja} destaque />
            <KpiCard label="Exames — Previsão Out+Nov+Dez" valor={data.exame.projecao_out_nov_dez} cor={CB.laranja} destaque />
          </div>

          {dataRCN && (() => {
            const valorMes = (meses, mes) => meses.find(m => m.mes === mes)?.valor || 0;
            const honJun = valorMes(dataRCN.consulta.meses, 6);
            const honJul = valorMes(dataRCN.consulta.meses, 7);
            const honMedia = (honJun + honJul) / 2;
            const exJun = valorMes(dataRCN.exame.meses, 6);
            const exJul = valorMes(dataRCN.exame.meses, 7);
            const exMedia = (exJun + exJul) / 2;
            return (
              <div style={{ marginBottom: 20 }}>
                <Card
                  title={<span style={{ fontSize: 19 }}>Impacto do Descredenciamento Hapvida — Junho + Julho (Recepção Consultórios)</span>}
                  subtitle="Honorários médicos e exames solicitados do Hapvida CECAN na Recepção Consultórios, mês a mês e média — meses de referência pro cenário de perda do convênio"
                  accent={CB.vermelhao}
                >
                  <div style={{ fontSize: 11.5, fontWeight: 800, color: C.sub, textTransform: "uppercase", letterSpacing: ".04em", margin: "2px 0 8px" }}>Honorários Médicos</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginBottom: 16 }}>
                    <KpiCard label="Honorários — Junho" valor={honJun} cor={CB.roxo} destaque />
                    <KpiCard label="Honorários — Julho" valor={honJul} cor={CB.roxo} destaque />
                    <KpiCard label="Honorários — Média" valor={honMedia} cor={CB.vermelhao} destaque />
                  </div>
                  <div style={{ fontSize: 11.5, fontWeight: 800, color: C.sub, textTransform: "uppercase", letterSpacing: ".04em", margin: "2px 0 8px" }}>Exames Solicitados</div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12 }}>
                    <KpiCard label="Exames — Junho" valor={exJun} cor={CB.azul} destaque />
                    <KpiCard label="Exames — Julho" valor={exJul} cor={CB.azul} destaque />
                    <KpiCard label="Exames — Média" valor={exMedia} cor={CB.vermelhao} destaque />
                  </div>
                </Card>
              </div>
            );
          })()}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(420px,1fr))", gap: 16 }}>
            <GraficoMensal meses={data.consulta.meses} titulo="Honorários (Consultas)" subtitulo={`Já produzido: ${brl(data.consulta.total_ja_produzido)}`} />
            <GraficoMensal meses={data.exame.meses} titulo="Exames Solicitados" subtitulo={`Já produzido: ${brl(data.exame.total_ja_produzido)} · média Mai-Jun-Jul`} />
          </div>

          <div style={{ marginTop: 16 }}>
            <Card title="Previsão Detalhada — Outubro / Novembro / Dezembro" subtitle="Média simples de Maio + Junho + Julho, projetada de forma plana" accent={CB.laranja}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: "#F8FAFC" }}>
                    <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Tipo</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Outubro</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Novembro</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Dezembro</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {[["Honorários (Consultas)", data.consulta], ["Exames Solicitados", data.exame]].map(([label, t], i) => (
                    <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td style={{ padding: "9px 10px", fontWeight: 700, color: C.text }}>{label}</td>
                      <td style={{ padding: "9px 10px", textAlign: "right" }}>{brl(t.projecao_outubro)}</td>
                      <td style={{ padding: "9px 10px", textAlign: "right" }}>{brl(t.projecao_novembro)}</td>
                      <td style={{ padding: "9px 10px", textAlign: "right" }}>{brl(t.projecao_dezembro)}</td>
                      <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800, color: CB.laranja }}>{brl(t.projecao_out_nov_dez)}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: `2px solid ${C.border}`, background: "#FFFBEB" }}>
                    <td style={{ padding: "9px 10px", fontWeight: 800, color: C.text }}>Total Hapvida CECAN</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.consulta.projecao_outubro + data.exame.projecao_outubro)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.consulta.projecao_novembro + data.exame.projecao_novembro)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.consulta.projecao_dezembro + data.exame.projecao_dezembro)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 900, color: CB.laranja }}>{brl(data.consulta.projecao_out_nov_dez + data.exame.projecao_out_nov_dez)}</td>
                  </tr>
                </tbody>
              </table>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function PainelRepasseSemMedicosConsulta({ ano, cnpj }) {
  const [setor, setSetor] = useState("TODOS");
  const { data, loading } = useFetch("/api/financeiro/hapvida-repasse-sem-medicos-consulta", { ano, setor, cnpj });

  const LINHAS = [
    { key: "total_ja_produzido", label: "Já Produzido no Ano" },
    { key: "total_primeiro_semestre_mais_julho", label: "Total Jan a Jul" },
    { key: "media_primeiro_semestre_mais_julho", label: "Média Jan a Jul" },
    { key: "projecao_out_nov_dez", label: "Previsão Out+Nov+Dez" },
  ];

  return (
    <div style={{ marginTop: 32 }}>
      <SectionHeader
        icone="⚖️"
        titulo="Repasse Hapvida Sem Médicos que Fazem Consulta"
        descricao="O quanto do repasse do Hapvida depende dos médicos que fazem consulta pelo convênio, contra o que sobraria vindo de outras fontes (ex: exames pedidos por médicos que não atendem consulta Hapvida). Psiquiatria não entra no grupo que sai — a receita Hapvida dos psiquiatras continua no que sobraria."
      >
        <SeletorSetor value={setor} onChange={setSetor} />
      </SectionHeader>

      {loading || !data ? <Carregando /> : (
        <Card title={`Setor: ${data.setor_nome}`} accent={CB.azul}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
            <thead>
              <tr style={{ background: "#F8FAFC" }}>
                <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}></th>
                <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Total Hapvida</th>
                <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Médicos c/ Consulta</th>
                <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Repasse Sem Eles</th>
              </tr>
            </thead>
            <tbody>
              {LINHAS.map((l, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                  <td style={{ padding: "9px 10px", fontWeight: 700, color: C.text }}>{l.label}</td>
                  <td style={{ padding: "9px 10px", textAlign: "right" }}>{brl(data.total_hapvida[l.key])}</td>
                  <td style={{ padding: "9px 10px", textAlign: "right", color: CB.vermelhao }}>− {brl(data.medicos_com_consulta[l.key])}</td>
                  <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800, color: CB.azul }}>{brl(data.repasse_sem_medicos_consulta[l.key])}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div style={{ fontSize: 10.5, color: C.faint, marginTop: 10 }}>
            "Médicos c/ Consulta" = todos os médicos que têm pelo menos uma consulta Hapvida registrada, somando consulta + todos os exames que ELES solicitaram (não só a consulta).
          </div>
        </Card>
      )}

      {!loading && data && (
        <div style={{ display: "grid", gridTemplateColumns: "minmax(240px,320px) 1fr", gap: 16, marginTop: 16 }}>
          <Card title="Composição — Já Produzido" subtitle="Médicos c/ consulta x resto do repasse" accent={CB.vermelhao}>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie
                  data={[
                    { nome: "Médicos c/ Consulta", valor: data.medicos_com_consulta.total_ja_produzido, cor: CB.vermelhao },
                    { nome: "Repasse Sem Eles", valor: data.repasse_sem_medicos_consulta.total_ja_produzido, cor: CB.azul },
                  ]}
                  dataKey="valor" nameKey="nome" cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={2}
                >
                  <Cell fill={CB.vermelhao} />
                  <Cell fill={CB.azul} />
                </Pie>
                <Tooltip formatter={(v) => brl(v)} />
                <Legend iconType="circle" iconSize={11} wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }} />
              </PieChart>
            </ResponsiveContainer>
            <div style={{ textAlign: "center", fontSize: 12, color: C.sub, marginTop: 4 }}>
              {data.total_hapvida.total_ja_produzido > 0
                ? `${((data.medicos_com_consulta.total_ja_produzido / data.total_hapvida.total_ja_produzido) * 100).toFixed(1)}% depende de médicos que fazem consulta Hapvida`
                : ""}
            </div>
          </Card>

          <Card title="Evolução Mensal — Total Hapvida x Médicos c/ Consulta x Repasse Sem Eles" subtitle="Barras = já produzido/em andamento/previsão · linha = repasse sem médicos c/ consulta" accent={CB.azulClaro}>
            <ResponsiveContainer width="100%" height={260}>
              <ComposedChart data={data.meses}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} />
                <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} width={60} />
                <Tooltip formatter={(v, n) => [brl(v), n === "total_hapvida" ? "Total Hapvida" : n === "medicos_com_consulta" ? "Médicos c/ Consulta" : "Repasse Sem Eles"]} />
                <Legend
                  iconType="circle" iconSize={11}
                  wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }}
                  payload={[
                    { value: "Total Hapvida", type: "square", color: CB.azulClaro },
                    { value: "Médicos c/ Consulta", type: "square", color: CB.vermelhao },
                    { value: "Repasse Sem Eles", type: "line", color: CB.azul },
                  ]}
                />
                <Bar dataKey="total_hapvida" fill={CB.azulClaro} radius={[4, 4, 0, 0]} fillOpacity={0.9} />
                <Bar dataKey="medicos_com_consulta" fill={CB.vermelhao} radius={[4, 4, 0, 0]} fillOpacity={0.9} />
                <Line dataKey="repasse_sem_medicos_consulta" stroke={CB.azul} strokeWidth={2.5} dot={{ r: 3, fill: CB.azul }} />
              </ComposedChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}

      {!loading && data && (
        <div style={{ marginTop: 16 }}>
          <Card title="Repasse Sem Médicos c/ Consulta — Tendência Mensal" subtitle="Verde = já produzido/em andamento · laranja = média de Mai+Jun+Jul, projetada de forma plana" accent={CB.verde}>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.meses}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} />
                <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} width={60} />
                <Tooltip formatter={(v) => brl(v)} />
                <Bar dataKey="repasse_sem_medicos_consulta" radius={[6, 6, 0, 0]}>
                  {data.meses.map((m, i) => <Cell key={i} fill={CORES_TIPO[m.tipo_dado]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Card>
        </div>
      )}
    </div>
  );
}

const COLUNAS_MEDICOS = [
  { key: "medico", label: "Médico", align: "left" },
  { key: "total_ja_produzido", label: "Já Produzido", align: "right" },
  { key: "media_primeiro_semestre_mais_julho", label: "Média (meses c/ produção)", align: "right" },
  { key: "projecao_outubro", label: "Out", align: "right" },
  { key: "projecao_novembro", label: "Nov", align: "right" },
  { key: "projecao_dezembro", label: "Dez", align: "right" },
  { key: "projecao_out_nov_dez", label: "Previsão Trimestre", align: "right" },
];

function PainelExamesPorMedico({ ano, cnpj }) {
  const [setor, setSetor] = useState("TODOS");
  const [sortKey, setSortKey] = useState("total_ja_produzido");
  const [sortDir, setSortDir] = useState("desc");
  const { data, loading } = useFetch("/api/financeiro/hapvida-exames-por-medico", { ano, setor, cnpj });

  const totalGeral = data?.medicos?.reduce((s, m) => s + m.total_ja_produzido, 0) || 0;
  const totalProjecao = data?.medicos?.reduce((s, m) => s + m.projecao_out_nov_dez, 0) || 0;

  const alternarOrdenacao = (key) => {
    if (sortKey === key) { setSortDir(d => d === "desc" ? "asc" : "desc"); }
    else { setSortKey(key); setSortDir("desc"); }
  };

  const medicosOrdenados = data?.medicos ? [...data.medicos].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    const cmp = typeof va === "string" ? va.localeCompare(vb) : va - vb;
    return sortDir === "asc" ? cmp : -cmp;
  }) : [];

  return (
    <div style={{ marginTop: 32 }}>
      <SectionHeader
        icone="👨‍⚕️"
        titulo="Exames Solicitados por Médico"
        descricao="Ranking dos médicos que mais geram exames Hapvida CECAN, com o já produzido no ano e a previsão pro último trimestre — média dos últimos 3 meses do médico com produção, projetada de forma plana."
      >
        <SeletorSetor value={setor} onChange={setSetor} />
      </SectionHeader>

      {loading || !data ? <Carregando /> : (
        <Card
          title={`Médicos que atenderam em ${data.setor_nome} — Hapvida CECAN`}
          subtitle="Exames solicitados (não inclui honorários de consulta) · clique numa coluna para ordenar · role a lista com o mouse"
          accent={CB.roxo}
        >
          <div style={{ maxHeight: 380, overflowY: "auto", overflowX: "auto", border: `1px solid ${C.border}`, borderRadius: 8 }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 700 }}>
              <thead>
                <tr>
                  {COLUNAS_MEDICOS.map(col => (
                    <th key={col.key} onClick={() => alternarOrdenacao(col.key)} style={{
                      padding: "8px 10px", textAlign: col.align, color: sortKey === col.key ? CB.roxo : C.faint,
                      fontSize: 10.5, textTransform: "uppercase", cursor: "pointer", userSelect: "none",
                      position: "sticky", top: 0, background: "#F8FAFC", zIndex: 1, whiteSpace: "nowrap",
                    }}>
                      {col.label}{sortKey === col.key ? (sortDir === "desc" ? " ▼" : " ▲") : ""}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {medicosOrdenados.map((m, i) => (
                  <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                    <td style={{ padding: "8px 10px", fontWeight: 700, color: C.text, whiteSpace: "nowrap" }}>{m.medico}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right" }}>{brl(m.total_ja_produzido)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color: C.sub }}>{brl(m.media_primeiro_semestre_mais_julho)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color: C.sub }}>{brl(m.projecao_outubro)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color: C.sub }}>{brl(m.projecao_novembro)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", color: C.sub }}>{brl(m.projecao_dezembro)}</td>
                    <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 800, color: CB.laranja }}>{brl(m.projecao_out_nov_dez)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 10, padding: "8px 10px", background: "#FFFBEB", borderRadius: 8, fontSize: 12.5 }}>
            <span style={{ fontWeight: 800, color: C.text }}>Total ({data.medicos.length} médicos)</span>
            <span style={{ fontWeight: 800 }}>{brl(totalGeral)}</span>
            <span style={{ fontWeight: 900, color: CB.laranja }}>Previsão trimestre: {brl(totalProjecao)}</span>
          </div>
          <div style={{ fontSize: 10.5, color: C.faint, marginTop: 10 }}>
            Nota: Out/Nov/Dez aparecem com o mesmo valor — média dos últimos 3 meses do médico com produção real, projetada de forma plana, sem ajuste sazonal.
          </div>
        </Card>
      )}
    </div>
  );
}

function PainelObstetricia({ ano, cnpj }) {
  const { data, loading } = useFetch("/api/financeiro/obstetricia-servicos", { ano, cnpj });
  const { data: dataExames } = useFetch("/api/financeiro/exames-solicitados-medicas-obstetricia", { ano, cnpj });

  const CORES_CONVENIO = [CB.azul, CB.laranja, CB.verde, CB.roxo, CB.vermelhao, CB.azulClaro, CB.cinza];

  // O convênio principal costuma dominar a produção — se colocar todos no
  // mesmo gráfico, os menores viram barras de ~1px, praticamente invisíveis
  // ao lado do maior. Mostra só os top 5 + soma do resto em "Outros"; a
  // tabela abaixo continua trazendo todos os convênios, um por um.
  const MAX_CONVENIOS_GRAFICO = 5;
  const porConvenioGrafico = (() => {
    if (!data?.por_convenio) return [];
    if (data.por_convenio.length <= MAX_CONVENIOS_GRAFICO) return data.por_convenio;
    const top = data.por_convenio.slice(0, MAX_CONVENIOS_GRAFICO);
    const resto = data.por_convenio.slice(MAX_CONVENIOS_GRAFICO);
    const outros = {
      convenio: `Outros (${resto.length})`,
      producao: resto.reduce((s, c) => s + c.producao, 0),
      qtd_atendimentos: resto.reduce((s, c) => s + c.qtd_atendimentos, 0),
      valor_honorario: resto.reduce((s, c) => s + c.valor_honorario, 0),
    };
    return [...top, outros];
  })();

  return (
    <div>
      <SectionHeader
        icone="🤰"
        titulo="Serviços de Ginecologia"
        descricao="Produção, número de atendimentos e valor de honorário (90% da produção) dos serviços de ginecologia, agregados por convênio."
      />

      {loading || !data ? <Carregando /> : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 12, marginBottom: 16 }}>
            <KpiCard label="Produção Total" valor={data.producao_total} cor={CB.azul} destaque />
            <KpiCard label={`Valor Honorários (${(data.percentual_honorario * 100).toFixed(0)}%)`} valor={data.valor_honorario_total} cor={CB.laranja} destaque />
            <div style={{ background: "#fff", borderRadius: 14, padding: "16px 18px", boxShadow: "0 1px 4px rgba(0,0,0,.07)", borderLeft: `4px solid ${CB.roxo}` }}>
              <div style={{ fontSize: 10.5, fontWeight: 800, color: "#9CA3AF", textTransform: "uppercase", letterSpacing: ".04em" }}>Número de Atendimentos</div>
              <div style={{ fontSize: 19, fontWeight: 900, color: "#111827", marginTop: 5 }}>{data.qtd_atendimentos_total}</div>
            </div>
          </div>

          {(() => {
            const meses5a7 = data.por_mes.filter(m => [5, 6, 7].includes(m.mes));
            const producaoTrimestre = meses5a7.reduce((s, m) => s + m.producao, 0);
            const atendimentosTrimestre = meses5a7.reduce((s, m) => s + m.qtd_atendimentos, 0);
            const honorarioTrimestre = producaoTrimestre * data.percentual_honorario;
            const exameTrimestre = dataExames
              ? dataExames.meses.filter(m => [5, 6, 7].includes(m.mes)).reduce((s, m) => s + m.valor, 0)
              : null;
            return (
              <div style={{ marginBottom: 20 }}>
                <Card title="Maio + Junho + Julho — Serviços de Ginecologia" subtitle="Soma e média mensal dos três meses mais recentes com produção fechada" accent={CB.roxo}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12 }}>
                    <KpiCard label="Produção (Mai+Jun+Jul)" valor={producaoTrimestre} cor={CB.azul} destaque />
                    <KpiCard label={`Honorários ${(data.percentual_honorario * 100).toFixed(0)}% (Mai+Jun+Jul)`} valor={honorarioTrimestre} cor={CB.laranja} destaque />
                    {exameTrimestre != null && <KpiCard label="Exames Solicitados (Mai+Jun+Jul)" valor={exameTrimestre} cor={CB.verde} destaque />}
                    <KpiCard label="Produção — Média Mensal" valor={producaoTrimestre / 3} cor={CB.azul} />
                    <KpiCard label="Honorários — Média Mensal" valor={honorarioTrimestre / 3} cor={CB.laranja} />
                    {exameTrimestre != null && <KpiCard label="Exames Solicitados — Média Mensal" valor={exameTrimestre / 3} cor={CB.verde} />}
                    <div style={{ background: "#fff", borderRadius: 18, padding: "16px 18px 15px", boxShadow: SOMBRA_CARD, border: `1px solid ${CB.roxo}25`, position: "relative", overflow: "hidden" }}>
                      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 5, background: `linear-gradient(90deg, ${CB.roxo}, ${CB.roxo}99, ${CB.roxo})` }} />
                      <div style={{ fontSize: 10.5, fontWeight: 800, color: "#9CA3AF", textTransform: "uppercase", letterSpacing: ".05em" }}>Atendimentos (Mai+Jun+Jul)</div>
                      <div style={{ fontSize: 19, fontWeight: 900, color: "#111827", marginTop: 8 }}>{atendimentosTrimestre}</div>
                    </div>
                  </div>
                </Card>
              </div>
            );
          })()}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(420px,1fr))", gap: 16 }}>
            <Card title="Produção Mensal" subtitle="US obstétrica, curvas glicêmicas de gestante e demais serviços de obstetrícia" accent={CB.azul}>
              <ResponsiveContainer width="100%" height={240}>
                <ComposedChart data={data.por_mes}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} />
                  <YAxis yAxisId="valor" tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} width={60} />
                  <YAxis yAxisId="qtd" orientation="right" tick={{ fontSize: 10, fill: "#94A3B8" }} width={35} />
                  <Tooltip formatter={(v, n) => n === "qtd_atendimentos" ? [v, "Atendimentos"] : [brl(v), "Produção"]} />
                  <Legend iconType="circle" iconSize={11} wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }} />
                  <Bar yAxisId="valor" dataKey="producao" name="Produção" fill={CB.azul} radius={[4, 4, 0, 0]} />
                  <Line yAxisId="qtd" dataKey="qtd_atendimentos" name="Nº Atendimentos" stroke={CB.laranja} strokeWidth={2.5} dot={{ r: 3, fill: CB.laranja }} />
                </ComposedChart>
              </ResponsiveContainer>
            </Card>

            <Card title="Produção Agregada por Convênio" subtitle={`Top ${MAX_CONVENIOS_GRAFICO} + Outros · valor de honorário = ${(data.percentual_honorario * 100).toFixed(0)}% da produção · tabela abaixo traz todos individualmente`} accent={CB.roxo}>
              <ResponsiveContainer width="100%" height={Math.max(240, porConvenioGrafico.length * 42)}>
                <BarChart data={porConvenioGrafico} layout="vertical" margin={{ left: 10, right: 50 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis type="number" tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} />
                  <YAxis type="category" dataKey="convenio" tick={{ fontSize: 10.5, fill: "#64748B" }} width={130} />
                  <Tooltip formatter={(v) => brl(v)} />
                  <Bar dataKey="producao" radius={[0, 4, 4, 0]} minPointSize={3}>
                    {porConvenioGrafico.map((c, i) => <Cell key={i} fill={CORES_CONVENIO[i % CORES_CONVENIO.length]} />)}
                    <LabelList dataKey="producao" position="right" formatter={brlCompacto} style={{ fontSize: 10.5, fill: "#64748B" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <div style={{ marginTop: 16 }}>
            <Card title="Detalhamento por Convênio" subtitle="Produção, atendimentos e valor de honorário por convênio" accent={CB.laranja}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: "#F8FAFC" }}>
                    <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Convênio</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Atendimentos</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Produção</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Honorário ({(data.percentual_honorario * 100).toFixed(0)}%)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.por_convenio.map((c, i) => (
                    <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td style={{ padding: "8px 10px", fontWeight: 700, color: C.text }}>{c.convenio}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>{c.qtd_atendimentos}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>{brl(c.producao)}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 800, color: CB.laranja }}>{brl(c.valor_honorario)}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: `2px solid ${C.border}`, background: "#FFFBEB" }}>
                    <td style={{ padding: "9px 10px", fontWeight: 800, color: C.text }}>Total</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{data.qtd_atendimentos_total}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.producao_total)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 900, color: CB.laranja }}>{brl(data.valor_honorario_total)}</td>
                  </tr>
                </tbody>
              </table>
            </Card>
          </div>

          <div style={{ marginTop: 16 }}>
            <Card title="Serviços de Ginecologia" subtitle="US obstétrica, curvas glicêmicas de gestante e demais procedimentos identificados" accent={CB.roxo}>
              <div style={{ maxHeight: 280, overflowY: "auto", border: `1px solid ${C.border}`, borderRadius: 8 }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                  <thead>
                    <tr>
                      <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase", position: "sticky", top: 0, background: "#F8FAFC" }}>Serviço</th>
                      <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase", position: "sticky", top: 0, background: "#F8FAFC" }}>Qtd</th>
                      <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase", position: "sticky", top: 0, background: "#F8FAFC" }}>Produção</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.por_servico.map((s, i) => (
                      <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                        <td style={{ padding: "8px 10px", fontWeight: 700, color: C.text }}>{s.servico}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right" }}>{s.qtd}</td>
                        <td style={{ padding: "8px 10px", textAlign: "right" }}>{brl(s.producao)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function PainelExamesMedicasObstetricia({ ano, cnpj }) {
  const { data, loading } = useFetch("/api/financeiro/exames-solicitados-medicas-obstetricia", { ano, cnpj });

  const CORES_MEDICA = [CB.roxo, CB.azul, CB.laranja, CB.verde];

  return (
    <div style={{ marginTop: 32 }}>
      <SectionHeader
        icone="🔬"
        titulo="Exames Solicitados — Médicas de Ginecologia"
        descricao={data ? `Médicas consideradas: ${data.medicos.map(m => m.charAt(0) + m.slice(1).toLowerCase()).join(", ")} — só os exames que elas solicitaram, sem contar a consulta em si.` : "Exames solicitados pelas médicas que atendem consultas de ginecologia."}
      />

      {loading || !data ? <Carregando /> : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 12, marginBottom: 16 }}>
            <KpiCard label="Já Produzido no Ano" valor={data.total_ja_produzido} cor={CB.azul} destaque />
            <KpiCard label="Total Jan a Jul" valor={data.total_primeiro_semestre_mais_julho} cor={CB.roxo} />
            <KpiCard label="Média Jan a Jul" valor={data.media_primeiro_semestre_mais_julho} cor={CB.azulClaro} />
            <KpiCard label="Previsão Out+Nov+Dez" valor={data.projecao_out_nov_dez} cor={CB.laranja} destaque />
          </div>

          {(() => {
            const somaMeses = (meses, alvo) => meses.filter(m => alvo.includes(m.mes)).reduce((s, m) => s + m.valor, 0);
            const exameTrimestre = somaMeses(data.meses, [5, 6, 7]);
            return (
              <div style={{ marginBottom: 20 }}>
                <Card title="Maio + Junho + Julho — Exames Solicitados" subtitle="Soma e média mensal dos três meses mais recentes com produção fechada" accent={CB.roxo}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12 }}>
                    <KpiCard label="Exames Solicitados (Mai+Jun+Jul)" valor={exameTrimestre} cor={CB.azul} destaque />
                    <KpiCard label="Média Mensal" valor={exameTrimestre / 3} cor={CB.laranja} destaque />
                  </div>
                </Card>
              </div>
            );
          })()}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(420px,1fr))", gap: 16 }}>
            <GraficoMensal meses={data.meses} titulo="Evolução Mensal" subtitulo={`Já produzido: ${brl(data.total_ja_produzido)}`} />

            <Card title="Por Médica" subtitle="Exames solicitados no ano, por médica" accent={CB.roxo}>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={data.por_medica} layout="vertical" margin={{ left: 10, right: 50 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                  <XAxis type="number" tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} />
                  <YAxis type="category" dataKey="medica" tick={{ fontSize: 10.5, fill: "#64748B" }} width={130} />
                  <Tooltip formatter={(v) => brl(v)} />
                  <Bar dataKey="producao" radius={[0, 4, 4, 0]}>
                    {data.por_medica.map((m, i) => <Cell key={i} fill={CORES_MEDICA[i % CORES_MEDICA.length]} />)}
                    <LabelList dataKey="producao" position="right" formatter={brlCompacto} style={{ fontSize: 10.5, fill: "#64748B" }} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Card>
          </div>

          <div style={{ marginTop: 16 }}>
            <Card title="Por Convênio" subtitle="Exames solicitados pelas duas médicas, agregado por convênio" accent={CB.azulClaro}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: "#F8FAFC" }}>
                    <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Convênio</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Atendimentos</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Produção</th>
                  </tr>
                </thead>
                <tbody>
                  {data.por_convenio.map((c, i) => (
                    <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td style={{ padding: "8px 10px", fontWeight: 700, color: C.text }}>{c.convenio}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>{c.qtd_atendimentos}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>{brl(c.producao)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>

          <div style={{ marginTop: 16 }}>
            <Card
              title="💡 Estudo de Viabilidade — Comissão de 2% sobre Exames"
              subtitle="Simulação: quanto custaria ceder 2% do valor dos exames solicitados como comissão/incentivo às médicas de ginecologia — calculado sobre os mesmos exames do painel acima."
              accent={CB.roxo}
            >
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 12, marginBottom: 16 }}>
                <KpiCard label="Comissão 2% — Já Produzido" valor={data.total_ja_produzido * 0.02} cor={CB.roxo} destaque />
                <KpiCard label="Comissão 2% — Média Jan a Jul" valor={data.media_primeiro_semestre_mais_julho * 0.02} cor={CB.azulClaro} />
                <KpiCard label="Comissão 2% — Previsão Out+Nov+Dez" valor={data.projecao_out_nov_dez * 0.02} cor={CB.laranja} destaque />
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: "#F8FAFC" }}>
                    <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Médica</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Exames Solicitados (Ano)</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Comissão 2%</th>
                  </tr>
                </thead>
                <tbody>
                  {data.por_medica.map((m, i) => (
                    <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td style={{ padding: "8px 10px", fontWeight: 700, color: C.text }}>{m.medica}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>{brl(m.producao)}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 800, color: CB.roxo }}>{brl(m.producao * 0.02)}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: `2px solid ${C.border}`, background: "#FFFBEB" }}>
                    <td style={{ padding: "9px 10px", fontWeight: 800, color: C.text }}>Total ({data.medicos.length} médicas)</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.total_ja_produzido)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 900, color: CB.roxo }}>{brl(data.total_ja_produzido * 0.02)}</td>
                  </tr>
                </tbody>
              </table>
              <div style={{ fontSize: 10.5, color: C.faint, marginTop: 10 }}>
                Simulação simples (2% linear sobre o valor de exame solicitado) — não considera custos operacionais adicionais nem eventuais mudanças de comportamento de solicitação após a implantação da comissão.
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function PainelProducaoRecepcao({ ano, cnpj }) {
  const [setor, setSetor] = useState("RCI");
  const { data, loading } = useFetch("/api/financeiro/producao-mensal-por-setor", { ano, setor, cnpj });

  return (
    <div>
      <SectionHeader
        icone="🧪"
        titulo="Produção por Recepção"
        descricao="Valor produzido mês a mês num ponto de recepção específico, com média Jan-Jul e previsão pro último trimestre (média de Mai+Jun+Jul, projetada de forma plana)."
      >
        <SeletorSetor value={setor} onChange={setSetor} opcoes={SETORES_RECEPCAO} />
      </SectionHeader>

      {loading || !data ? <Carregando /> : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(200px,1fr))", gap: 12, marginBottom: 16 }}>
            <KpiCard label="Já Produzido no Ano" valor={data.total_ja_produzido} cor={CB.azul} destaque />
            <KpiCard label="Total Jan a Jul" valor={data.total_primeiro_semestre_mais_julho} cor={CB.roxo} />
            <KpiCard label="Média Jan a Jul" valor={data.media_primeiro_semestre_mais_julho} cor={CB.azulClaro} />
            <KpiCard label="Previsão Out+Nov+Dez" valor={data.projecao_out_nov_dez} cor={CB.laranja} destaque />
          </div>

          <GraficoMensal meses={data.meses} titulo={`Produção Mensal — ${data.setor_nome}`} subtitulo={`Já produzido: ${brl(data.total_ja_produzido)}`} />

          <div style={{ marginTop: 16 }}>
            <Card
              title="Previsão Detalhada — Outubro / Novembro / Dezembro"
              subtitle="Média simples de Maio + Junho + Julho, projetada de forma plana"
              accent={CB.laranja}
            >
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: "#F8FAFC" }}>
                    <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}></th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Outubro</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Novembro</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Dezembro</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderTop: `2px solid ${C.border}`, background: "#FFFBEB" }}>
                    <td style={{ padding: "9px 10px", fontWeight: 800, color: C.text }}>{data.setor_nome}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.projecao_outubro)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.projecao_novembro)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.projecao_dezembro)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 900, color: CB.laranja }}>{brl(data.projecao_out_nov_dez)}</td>
                  </tr>
                </tbody>
              </table>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

function PainelEstudoNovoColeta({ ano, cnpj }) {
  const { data, loading } = useFetch("/api/financeiro/estudo-novo-ponto-coleta", { ano, cnpj });

  return (
    <div style={{ marginTop: 32 }}>
      <SectionHeader
        icone="🔬"
        titulo="Estudo — Novo Ponto de Coleta Laboratorial (Consultórios)"
        descricao={data
          ? `A partir de ${data.mes_inicio_operacao_label}/${data.ano} a Recepção Consultórios passou a executar exames laboratoriais (Análises Clínicas) em escala — o volume saltou de poucas dezenas/mês pra milhares. Quanto foi arrecadado de fato x quanto teria sido arrecadado se esse ponto já operasse nesse ritmo desde janeiro.`
          : "Quanto foi arrecadado com exames laboratoriais na Recepção Consultórios x quanto teria sido arrecadado se o ponto de coleta já operasse desde janeiro."}
      />

      {loading || !data ? <Carregando /> : (
        <>
          <div style={{
            display: "flex", alignItems: "center", gap: 8, fontSize: 11.5, color: "#92400E",
            background: "#FFFBEB", border: "1px solid #FDE68A", borderRadius: 10, padding: "8px 12px", marginBottom: 14,
          }}>
            ℹ️ O estudo de oportunidade perdida é só sobre exames laboratoriais (Análises Clínicas) — as consultas de {data.setor_nome} já vinham crescendo organicamente antes de junho (sem salto de operação), então aparecem à parte, como contexto.
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(220px,1fr))", gap: 12, marginBottom: 20 }}>
            <KpiCard label="Exames Lab. — Arrecadado (Real)" valor={data.total_real} cor={CB.azul} destaque />
            <KpiCard label="Exames Lab. — Se Operasse Desde Janeiro" valor={data.total_hipotetico} cor={CB.roxo} destaque />
            <KpiCard label="Exames Lab. — Oportunidade Perdida (Jan-Mai)" valor={data.diferenca_oportunidade_perdida} cor={CB.vermelhao} destaque />
            <KpiCard label={`Exames Lab. — Média Mensal em Operação Plena (${data.mes_inicio_operacao_label}+)`} valor={data.media_mensal_operacao_plena} cor={CB.laranja} />
            <KpiCard label="Consultas — Total Jan a Jul (contexto)" valor={data.total_consulta} cor={CB.cinza} />
          </div>

          <Card
            title="Real x Hipotético — Evolução Mensal"
            subtitle={`Barra = arrecadado de fato (cinza = antes de ${data.mes_inicio_operacao_label}, azul = em operação plena) · linha tracejada = se operasse desde janeiro`}
            accent={CB.roxo}
          >
            <ResponsiveContainer width="100%" height={280}>
              <ComposedChart data={data.meses}>
                <ChartDefs />
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} axisLine={{ stroke: "#E5E7EB" }} tickLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} width={60} axisLine={false} tickLine={false} />
                <Tooltip
                  formatter={(v, n) => [brl(v), n === "real" ? "Arrecadado (real)" : "Hipotético (desde janeiro)"]}
                  contentStyle={{ borderRadius: 10, border: "1px solid #E5E7EB", fontSize: 12, boxShadow: SOMBRA_CARD }}
                  cursor={{ fill: "#F8FAFC" }}
                />
                <Legend
                  iconType="circle" iconSize={11}
                  wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }}
                  payload={[
                    { value: "Arrecadado (real)", type: "square", color: CB.azul },
                    { value: "Hipotético (desde janeiro)", type: "line", color: CB.roxo },
                  ]}
                />
                <Bar dataKey="real" radius={[5, 5, 0, 0]} maxBarSize={46}>
                  {data.meses.map((m, i) => <Cell key={i} fill={m.em_operacao_plena ? "url(#gradAzul)" : "url(#gradCinza)"} />)}
                </Bar>
                <Line dataKey="hipotetico" stroke={CB.roxo} strokeWidth={2.5} strokeDasharray="6 4" dot={{ r: 3, fill: CB.roxo }} />
              </ComposedChart>
            </ResponsiveContainer>
          </Card>

          <div style={{ marginTop: 16 }}>
            <Card title="Detalhamento Mensal" subtitle="Exames laboratoriais: real x hipotético · Consultas: só contexto, não entra na diferença" accent={CB.vermelhao}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
                <thead>
                  <tr style={{ background: "#F8FAFC" }}>
                    <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Mês</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Qtd Exames Lab.</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Exames Lab. — Real</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Exames Lab. — Hipotético</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Diferença</th>
                    <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Consultas (contexto)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.meses.map((m, i) => (
                    <tr key={i} style={{ borderTop: `1px solid ${C.border}` }}>
                      <td style={{ padding: "8px 10px", fontWeight: 700, color: C.text }}>
                        {m.label}{!m.em_operacao_plena && <span style={{ fontSize: 10, color: C.faint, marginLeft: 6, fontWeight: 600 }}>(antes)</span>}
                      </td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>{m.qtd_exames}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>{brl(m.real)}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right" }}>{brl(m.hipotetico)}</td>
                      <td style={{ padding: "8px 10px", textAlign: "right", fontWeight: 800, color: m.hipotetico > m.real ? CB.vermelhao : C.faint }}>
                        {m.hipotetico > m.real ? `+${brl(m.hipotetico - m.real)}` : "—"}
                      </td>
                      <td style={{ padding: "8px 10px", textAlign: "right", color: C.faint }}>{brl(m.consulta)}</td>
                    </tr>
                  ))}
                  <tr style={{ borderTop: `2px solid ${C.border}`, background: "#FFFBEB" }}>
                    <td style={{ padding: "9px 10px", fontWeight: 800, color: C.text }}>Total</td>
                    <td></td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.total_real)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 800 }}>{brl(data.total_hipotetico)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 900, color: CB.vermelhao }}>+{brl(data.diferenca_oportunidade_perdida)}</td>
                    <td style={{ padding: "9px 10px", textAlign: "right", fontWeight: 700, color: C.sub }}>{brl(data.total_consulta)}</td>
                  </tr>
                </tbody>
              </table>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════
// Navegação por abas — agrupa os painéis em blocos temáticos pra reduzir
// rolagem e deixar mais fácil de guiar a apresentação pros sócios.
// ══════════════════════════════════════════════════════════════════════════
// Versão enxuta, mostrando só o impacto do descredenciamento Hapvida (RCN) —
// módulo está sendo reconstruído por partes, o resto fica oculto por enquanto
// (painéis completos continuam definidos acima, prontos pra voltar).
function PainelImpactoDescredenciamento({ ano, cnpj }) {
  const { data: dataRCN, loading } = useFetch("/api/financeiro/hapvida-honorarios-exames", { ano, setor: "RCN", cnpj });
  const { data: dataVG, loading: loadingVG } = useFetch("/api/financeiro/visao-geral-hapvida", { ano, cnpj });
  const { data: dataVGSetor, loading: loadingVGSetor } = useFetch("/api/financeiro/visao-geral-hapvida", { ano, cnpj, setor: "RCN" });

  if (loading || loadingVG || loadingVGSetor || !dataRCN || !dataVG || !dataVGSetor) return <Carregando />;

  const valorMes = (meses, mes) => meses.find(m => m.mes === mes)?.valor || 0;
  const honJun = valorMes(dataRCN.consulta.meses, 6);
  const honJul = valorMes(dataRCN.consulta.meses, 7);
  const honMedia = (honJun + honJul) / 2;
  const exJun = valorMes(dataRCN.exame.meses, 6);
  const exJul = valorMes(dataRCN.exame.meses, 7);
  const exMedia = (exJun + exJul) / 2;

  const producaoTotalJun = dataVG.meses.find(m => m.mes === 6)?.producao_total || 0;
  const producaoTotalJul = dataVG.meses.find(m => m.mes === 7)?.producao_total || 0;
  const producaoTotalMedia = (producaoTotalJun + producaoTotalJul) / 2;
  const impactoMensal = honMedia + exMedia;
  const pctImpacto = producaoTotalMedia ? (impactoMensal / producaoTotalMedia * 100) : 0;
  const receitaRestante = producaoTotalMedia - impactoMensal;

  const receitaSetorJun = dataVGSetor.meses.find(m => m.mes === 6)?.producao_total || 0;
  const receitaSetorJul = dataVGSetor.meses.find(m => m.mes === 7)?.producao_total || 0;
  const receitaSetorMedia = (receitaSetorJun + receitaSetorJul) / 2;
  const pctImpactoSetor = receitaSetorMedia ? (impactoMensal / receitaSetorMedia * 100) : 0;
  const receitaSetorRestante = receitaSetorMedia - impactoMensal;

  return (
    <Card
      title={<span style={{ fontSize: 19 }}>Impacto do Descredenciamento Hapvida — Junho + Julho (Recepção Consultórios)</span>}
      subtitle="Honorários médicos e exames solicitados do Hapvida CECAN na Recepção Consultórios, mês a mês e média — meses de referência pro cenário de perda do convênio"
      accent={CB.vermelhao}
    >
      <div style={{ fontSize: 11.5, fontWeight: 800, color: C.sub, textTransform: "uppercase", letterSpacing: ".04em", margin: "2px 0 8px" }}>Honorários Médicos</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginBottom: 16 }}>
        <KpiCard label="Honorários — Junho" valor={honJun} cor={CB.roxo} destaque />
        <KpiCard label="Honorários — Julho" valor={honJul} cor={CB.roxo} destaque />
        <KpiCard label="Honorários — Média" valor={honMedia} cor={CB.vermelhao} destaque />
      </div>
      <div style={{ fontSize: 11.5, fontWeight: 800, color: C.sub, textTransform: "uppercase", letterSpacing: ".04em", margin: "2px 0 8px" }}>Exames Solicitados</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginBottom: 16 }}>
        <KpiCard label="Exames — Junho" valor={exJun} cor={CB.azul} destaque />
        <KpiCard label="Exames — Julho" valor={exJul} cor={CB.azul} destaque />
        <KpiCard label="Exames — Média" valor={exMedia} cor={CB.vermelhao} destaque />
      </div>

      <div style={{ fontSize: 11.5, fontWeight: 800, color: C.sub, textTransform: "uppercase", letterSpacing: ".04em", margin: "2px 0 8px" }}>Receita Total da Clínica x Impacto Mensal</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginBottom: 16 }}>
        <KpiCard label="Receita Média Produção — Jun/Jul (Total Clínica)" valor={producaoTotalMedia} cor={CB.cinza} destaque />
        <KpiCard label="Impacto Mensal (Hapvida RCN — Jun/Jul)" valor={impactoMensal} cor={CB.vermelhao} destaque />
        <KpiCard label="% Impacto sobre a Receita Total" valor={pctImpacto} formatar={(v) => `${v.toFixed(1)}%`} cor={CB.vermelhao} destaque />
        <KpiCard label="Restaria (Receita sem Hapvida RCN)" valor={receitaRestante} cor={CB.verde} destaque />
      </div>

      <div style={{ fontSize: 11.5, fontWeight: 800, color: C.sub, textTransform: "uppercase", letterSpacing: ".04em", margin: "2px 0 8px" }}>Receita da Recepção Consultórios x Impacto Direto no Setor</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12 }}>
        <KpiCard label="Receita Média — Jun/Jul (Recepção Consultórios, todos os convênios)" valor={receitaSetorMedia} cor={CB.cinza} destaque />
        <KpiCard label="% Impacto Direto no Setor" valor={pctImpactoSetor} formatar={(v) => `${v.toFixed(1)}%`} cor={CB.vermelhao} destaque />
        <KpiCard label="Restaria no Setor (sem Hapvida)" valor={receitaSetorRestante} cor={CB.verde} destaque />
      </div>
    </Card>
  );
}

// Demonstrativo de receita por centro de resultado (= ponto de recepção) no
// semestre — Jan a Jun, top 5 + Outros.
function PainelReceitaPorCentroResultado({ ano }) {
  // Não passa cnpj de propósito: este demonstrativo sempre mostra o valor
  // real por centro (o backend ignora o filtro interno/externo), porque
  // Ocupacional é majoritariamente faturado fora do CNPJ interno.
  const { data, loading } = useFetch("/api/financeiro/receita-por-centro-resultado", { ano, top: 5 });
  const CORES = [CB.verde, CB.azul, CB.laranja, CB.roxo, CB.vermelhao, CB.cinza];

  if (loading || !data) return <Carregando />;

  const MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  const rotuloPeriodo = `${MESES_ABREV[data.mes_ini - 1]} a ${MESES_ABREV[data.mes_fim - 1]}`;

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title={<span style={{ fontSize: 19 }}>Receita por Centro de Resultado — Total do Semestre ({rotuloPeriodo}/{data.ano})</span>}
        subtitle={`5 maiores centros de resultado (recepções) + Outros · total do período: ${brl(data.total_geral)} (${data.n_meses} meses, semestre) · ${data.qtd_centros_total} centros no total · sempre valor real, não muda com o filtro de CNPJ`}
        accent={CB.verde}
      >
        <ResponsiveContainer width="100%" height={Math.max(240, data.itens.length * 46)}>
          <BarChart data={data.itens} layout="vertical" margin={{ left: 10, right: 90 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis type="number" tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompactoInteiro} />
            <YAxis type="category" dataKey="centro" tick={{ fontSize: 11, fill: "#64748B" }} width={150} />
            <Tooltip formatter={(v, n, p) => [`${brlInteiro(v)} (${p.payload.percentual}% · média mensal: ${brlInteiro(p.payload.media_mensal)})`, `Total ${rotuloPeriodo}`]} />
            <Bar dataKey="total" radius={[0, 4, 4, 0]} minPointSize={3}>
              {data.itens.map((c, i) => <Cell key={i} fill={CORES[i % CORES.length]} />)}
              <LabelList
                dataKey="total"
                content={({ x, y, width, height, value, index }) => {
                  const item = data.itens[index];
                  const pctTexto = `${Math.round(item.percentual)}%`;
                  const valorTexto = brlInteiro(value);
                  const cabeDentro = width >= pctTexto.length * 7 + 14;
                  const centerY = y + height / 2 + 4;
                  if (cabeDentro) {
                    return (
                      <g>
                        <text x={x + width - 8} y={centerY} textAnchor="end" fontSize={11} fontWeight={800} fill="#fff">{pctTexto}</text>
                        <text x={x + width + 8} y={centerY} textAnchor="start" fontSize={11} fontWeight={700} fill="#374151">{valorTexto}</text>
                      </g>
                    );
                  }
                  return (
                    <text x={x + width + 8} y={centerY} textAnchor="start" fontSize={11} fontWeight={700} fill="#374151">
                      {pctTexto} · {valorTexto}
                    </text>
                  );
                }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}

// Demonstrativo Resultados 2026 — Receitas x Despesas x Resultado. Dado de
// controle manual (planilha externa "RE 2026" da equipe financeira, mesma
// origem do card de Descontos e Glosas) — Despesas não estão conectadas a
// nenhum modulo deste dashboard hoje (viriam de contas a pagar/CPG-IPG, uma
// integração maior, ainda não construída). Atualizar os valores abaixo
// manualmente quando a planilha for revisada.
const RESULTADOS_2026_DADOS = [
  { mes: "Janeiro", receitas: 1020254.05, despesas: 836904.66 },
  { mes: "Fevereiro", receitas: 996583.30, despesas: 889699.99 },
  { mes: "Março", receitas: 1125144.90, despesas: 989416.45 },
  { mes: "Abril", receitas: 1021751.47, despesas: 916659.01 },
  { mes: "Maio", receitas: 1057705.14, despesas: 1060484.95 },
  { mes: "Junho", receitas: 1117729.15, despesas: 1054301.61 },
];

// Cores da marca Clínica Censo (mesmas usadas em todo o app como accent
// principal — App.jsx), em vez da paleta genérica de gráfico, pra ficar mais
// no padrão visual da clínica e com mais contraste pro texto branco.
const COR_CLINICA_RECEITAS = "#8B1A1A";
const COR_CLINICA_DESPESAS = "#D97706";

function PainelDemonstrativoResultados2026() {
  const dadosGrafico = RESULTADOS_2026_DADOS.map(m => ({ ...m, resultado: m.receitas - m.despesas }));
  const n = dadosGrafico.length;
  const mediaReceitas = dadosGrafico.reduce((s, m) => s + m.receitas, 0) / n;
  const mediaDespesas = dadosGrafico.reduce((s, m) => s + m.despesas, 0) / n;
  const mediaResultado = mediaReceitas - mediaDespesas;

  // Resultado desenhado num eixo próprio (escondido), sempre empurrado pra
  // cima da barra mais alta — assim o rótulo dele nunca fica em cima do
  // valor da barra, mesmo o resultado sendo bem menor que receitas/despesas.
  const maxBarra = Math.max(...dadosGrafico.flatMap(m => [m.receitas, m.despesas]));
  const eixoResultadoMax = maxBarra * 1.35;
  const dadosComPlot = dadosGrafico.map(m => ({ ...m, resultadoPlot: maxBarra * 1.18 }));

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title={<span style={{ fontSize: 19 }}>Demonstrativo Resultados 2026 — Receitas x Despesas</span>}
        subtitle="Receitas, despesas e resultado (receitas - despesas) por mês · dado de controle manual (planilha externa), Despesas não conectadas ao banco Smart — atualizar manualmente"
        accent={COR_CLINICA_RECEITAS}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 12, marginBottom: 16 }}>
          <KpiCard label="Média Mensal — Receitas" valor={mediaReceitas} cor={COR_CLINICA_RECEITAS} destaque />
          <KpiCard label="Média Mensal — Despesas" valor={mediaDespesas} cor={COR_CLINICA_DESPESAS} destaque />
          <KpiCard label="Média Mensal — Resultado" valor={mediaResultado} cor={mediaResultado >= 0 ? CB.verde : CB.vermelhao} destaque />
        </div>

        <ResponsiveContainer width="100%" height={420}>
          <ComposedChart data={dadosComPlot}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis dataKey="mes" tick={{ fontSize: 11, fill: "#64748B" }} />
            <YAxis yAxisId="valor" tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompactoInteiro} width={60} domain={[0, maxBarra * 1.35]} />
            <YAxis yAxisId="resultado" hide domain={[0, eixoResultadoMax]} />
            <Tooltip formatter={(v, n, p) => n === "resultadoPlot" ? [brlInteiro(p.payload.resultado), "Resultado"] : [brlInteiro(v), n === "receitas" ? "Receitas" : "Despesas"]} />
            <Legend
              iconType="circle" iconSize={11}
              wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }}
              payload={[
                { value: "Receitas", type: "square", color: COR_CLINICA_RECEITAS },
                { value: "Despesas", type: "square", color: COR_CLINICA_DESPESAS },
                { value: "Resultado", type: "line", color: CB.verde },
              ]}
            />
            <Bar yAxisId="valor" dataKey="receitas" name="Receitas" fill={COR_CLINICA_RECEITAS} radius={[4, 4, 0, 0]}>
              <LabelList dataKey="receitas" position="center" formatter={brlInteiro} style={{ fontSize: 13, fill: "#fff", fontWeight: 800 }} angle={-90} />
            </Bar>
            <Bar yAxisId="valor" dataKey="despesas" name="Despesas" fill={COR_CLINICA_DESPESAS} radius={[4, 4, 0, 0]}>
              <LabelList dataKey="despesas" position="center" formatter={brlInteiro} style={{ fontSize: 13, fill: "#fff", fontWeight: 800 }} angle={-90} />
            </Bar>
            <Line yAxisId="resultado" dataKey="resultadoPlot" name="Resultado" stroke={CB.verde} strokeWidth={2.5} dot={{ r: 4, fill: CB.verde }}>
              <LabelList
                dataKey="resultadoPlot"
                content={({ x, y, index }) => {
                  const real = dadosGrafico[index].resultado;
                  const texto = brlInteiro(real);
                  const largura = texto.length * 8 + 16;
                  const corFundo = real >= 0 ? CB.verde : CB.vermelhao;
                  return (
                    <g>
                      <rect x={x - largura / 2} y={y - 27} width={largura} height={22} rx={5} fill={corFundo} />
                      <text x={x} y={y - 12} textAnchor="middle" fontSize={13} fontWeight={800} fill="#fff">
                        {texto}
                      </text>
                    </g>
                  );
                }}
              />
            </Line>
          </ComposedChart>
        </ResponsiveContainer>

        <div style={{ marginTop: 16, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 560 }}>
            <thead>
              <tr style={{ background: "#F8FAFC" }}>
                <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}></th>
                {dadosGrafico.map(m => (
                  <th key={m.mes} style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>{m.mes}</th>
                ))}
                <th style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Média</th>
              </tr>
            </thead>
            <tbody>
              <tr style={{ borderTop: `1px solid ${C.border}` }}>
                <td style={{ padding: "7px 10px", fontWeight: 700, color: COR_CLINICA_RECEITAS }}>Receitas</td>
                {dadosGrafico.map(m => <td key={m.mes} style={{ padding: "7px 10px", textAlign: "right" }}>{brl(m.receitas)}</td>)}
                <td style={{ padding: "7px 10px", textAlign: "right", fontWeight: 800 }}>{brl(mediaReceitas)}</td>
              </tr>
              <tr>
                <td style={{ padding: "7px 10px", fontWeight: 700, color: COR_CLINICA_DESPESAS }}>Despesas</td>
                {dadosGrafico.map(m => <td key={m.mes} style={{ padding: "7px 10px", textAlign: "right" }}>{brl(m.despesas)}</td>)}
                <td style={{ padding: "7px 10px", textAlign: "right", fontWeight: 800 }}>{brl(mediaDespesas)}</td>
              </tr>
              <tr style={{ background: mediaResultado >= 0 ? "#DCFCE7" : "#FEF2F2", fontWeight: 800 }}>
                <td style={{ padding: "7px 10px", color: mediaResultado >= 0 ? "#166534" : "#991B1B" }}>Resultado</td>
                {dadosGrafico.map(m => (
                  <td key={m.mes} style={{ padding: "7px 10px", textAlign: "right", color: m.resultado >= 0 ? "#166534" : "#991B1B" }}>{brl(m.resultado)}</td>
                ))}
                <td style={{ padding: "7px 10px", textAlign: "right", color: mediaResultado >= 0 ? "#166534" : "#991B1B" }}>{brl(mediaResultado)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// Comparativo 1º Semestre 2025 x 2026 — dado de controle manual (mesma
// planilha "RE 2026" da contabilidade, slide "Resultado Comparativo —
// 2025-2026" do PPTX de prestação de contas). 2026 já bate com o card
// Demonstrativo Resultados 2026 acima (mesma fonte); 2025 é informação nova.
const COMPARATIVO_2025_2026 = {
  2025: { receitas: 3535046.00, despesas: 3832810.72 },
  2026: { receitas: 6339168.01, despesas: 5747466.67 },
};

function PainelComparativo2025x2026() {
  const r2025 = COMPARATIVO_2025_2026[2025].receitas;
  const d2025 = COMPARATIVO_2025_2026[2025].despesas;
  const res2025 = r2025 - d2025;
  const r2026 = COMPARATIVO_2025_2026[2026].receitas;
  const d2026 = COMPARATIVO_2025_2026[2026].despesas;
  const res2026 = r2026 - d2026;

  const linhas = [
    { label: "Receitas", v2025: r2025, v2026: r2026, cor: COR_CLINICA_RECEITAS },
    { label: "Despesas", v2025: d2025, v2026: d2026, cor: COR_CLINICA_DESPESAS },
    { label: "Resultado", v2025: res2025, v2026: res2026, cor: res2026 >= 0 ? CB.verde : CB.vermelhao },
  ];
  const dadosGrafico = linhas.map(l => ({ label: l.label, 2025: l.v2025, 2026: l.v2026, cor: l.cor }));

  const variacao = (v2026, v2025) => v2025 !== 0 ? ((v2026 - v2025) / Math.abs(v2025) * 100) : null;

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title={<span style={{ fontSize: 19 }}>Resultado Comparativo — 1º Semestre 2025 x 2026</span>}
        subtitle="Receitas, despesas e resultado do semestre, ano a ano · dado de controle manual (planilha da contabilidade)"
        accent={CB.roxo}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 12, marginBottom: 16 }}>
          <KpiCard label="Resultado 2025" valor={res2025} formatar={brlInteiro} cor={res2025 >= 0 ? CB.verde : CB.vermelhao} destaque />
          <KpiCard label="Resultado 2026" valor={res2026} formatar={brlInteiro} cor={res2026 >= 0 ? CB.verde : CB.vermelhao} destaque />
          <KpiCard label="Variação Receitas" valor={r2026 - r2025} formatar={(v) => `${v >= 0 ? "+" : ""}${brlInteiro(v)} (${variacao(r2026, r2025).toFixed(1)}%)`} cor={CB.azul} destaque />
          <KpiCard label="Variação Despesas" valor={d2026 - d2025} formatar={(v) => `${v >= 0 ? "+" : ""}${brlInteiro(v)} (${variacao(d2026, d2025).toFixed(1)}%)`} cor={CB.laranja} destaque />
        </div>

        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={dadosGrafico}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#64748B", fontWeight: 700 }} />
            <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompactoInteiro} width={60} />
            <Tooltip formatter={(v) => brlInteiro(v)} />
            <Legend iconType="circle" iconSize={11} wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }} />
            <Bar dataKey="2025" name="1º Sem 2025" fill="#B0B0B0" radius={[4, 4, 0, 0]}>
              <LabelList dataKey="2025" position="top" formatter={brlCompactoInteiro} style={{ fontSize: 10.5, fill: "#374151", fontWeight: 700 }} />
            </Bar>
            <Bar dataKey="2026" name="1º Sem 2026" fill={CB.roxo} radius={[4, 4, 0, 0]}>
              <LabelList dataKey="2026" position="top" formatter={brlCompactoInteiro} style={{ fontSize: 10.5, fill: "#374151", fontWeight: 700 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        {res2025 < 0 && res2026 >= 0 && (
          <div style={{
            marginTop: 12, fontSize: 12.5, lineHeight: 1.5, color: "#166534",
            background: "#F0FDF4", borderLeft: `3px solid ${CB.verde}`, padding: "10px 14px", borderRadius: 8,
          }}>
            💡 A clínica reverteu um resultado negativo de {brlInteiro(res2025)} no 1º semestre de 2025 para um resultado positivo de {brlInteiro(res2026)} em 2026 — uma melhora de {brlInteiro(res2026 - res2025)}.
          </div>
        )}
      </Card>
    </div>
  );
}

// Demonstrativo Ciclo de Receita — Descontos e Glosas. Dado de controle
// manual (planilha externa da equipe financeira) — não existe no banco
// Smart (SMM_VLR_DESCONTO do Hapvida está zerado nos 3 anos e as tabelas de
// glosa do Smart, NFS_LOTE_GLOSAS_GUIAS/PROC, estão vazias). Atualizar os
// valores abaixo manualmente quando a planilha for revisada.
const DESCONTOS_GLOSAS_DADOS = [
  {
    grupo: "HAPVIDA",
    anos: {
      2024: { descontos: 108622.41, glosas: 0 },
      2025: { descontos: 19680.00, glosas: 0 },
      2026: { descontos: 10035.00, glosas: 66157.00 },
    },
  },
  {
    grupo: "A.M.S",
    anos: {
      2024: { descontos: 0, glosas: 0 },
      2025: { descontos: 0, glosas: 0 },
      2026: { descontos: 0, glosas: 5021.00 },
    },
  },
  {
    grupo: "EMPRESAS/CONVÊNIOS",
    anos: {
      2024: { descontos: 0, glosas: 0 },
      2025: { descontos: 0, glosas: 0 },
      2026: { descontos: 8413.00, glosas: 0 },
    },
  },
];
const DESCONTOS_GLOSAS_ANOS = [2024, 2025, 2026];

function PainelDescontosGlosas() {
  const totalPorAno = {};
  DESCONTOS_GLOSAS_ANOS.forEach(ano => {
    totalPorAno[ano] = DESCONTOS_GLOSAS_DADOS.reduce((s, g) => s + g.anos[ano].descontos + g.anos[ano].glosas, 0);
  });
  const totalGeral = DESCONTOS_GLOSAS_ANOS.reduce((s, ano) => s + totalPorAno[ano], 0);

  const dadosGrafico = DESCONTOS_GLOSAS_DADOS.map(g => ({
    grupo: g.grupo,
    2024: g.anos[2024].descontos + g.anos[2024].glosas,
    2025: g.anos[2025].descontos + g.anos[2025].glosas,
    2026: g.anos[2026].descontos + g.anos[2026].glosas,
  }));
  const CORES_ANO = { 2024: CB.cinza, 2025: CB.laranja, 2026: CB.vermelhao };

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title={<span style={{ fontSize: 19 }}>Demonstrativo Ciclo de Receita — Descontos e Glosas</span>}
        subtitle="Descontos e glosas com impacto no fluxo de caixa, por convênio e ano · dado de controle manual (planilha externa), não conectado ao banco Smart — atualizar manualmente"
        accent={CB.vermelhao}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(160px,1fr))", gap: 12, marginBottom: 16 }}>
          {DESCONTOS_GLOSAS_ANOS.map(ano => (
            <KpiCard key={ano} label={`Total Geral ${ano}`} valor={totalPorAno[ano]} cor={CORES_ANO[ano]} destaque />
          ))}
          <KpiCard label="Total Geral (2024-2026)" valor={totalGeral} cor={CB.vermelhao} destaque />
        </div>

        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={dadosGrafico}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis dataKey="grupo" tick={{ fontSize: 11, fill: "#64748B" }} />
            <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompacto} width={60} />
            <Tooltip formatter={(v) => brl(v)} />
            <Legend iconType="circle" iconSize={11} wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }} />
            <Bar dataKey="2024" name="2024" fill={CORES_ANO[2024]} radius={[4, 4, 0, 0]}>
              <LabelList dataKey="2024" position="top" formatter={brlCompacto} style={{ fontSize: 10, fill: "#374151", fontWeight: 700 }} />
            </Bar>
            <Bar dataKey="2025" name="2025" fill={CORES_ANO[2025]} radius={[4, 4, 0, 0]}>
              <LabelList dataKey="2025" position="top" formatter={brlCompacto} style={{ fontSize: 10, fill: "#374151", fontWeight: 700 }} />
            </Bar>
            <Bar dataKey="2026" name="2026" fill={CORES_ANO[2026]} radius={[4, 4, 0, 0]}>
              <LabelList dataKey="2026" position="top" formatter={brlCompacto} style={{ fontSize: 10, fill: "#374151", fontWeight: 700 }} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>

        <div style={{ marginTop: 16, overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5, minWidth: 480 }}>
            <thead>
              <tr style={{ background: "#F8FAFC" }}>
                <th style={{ padding: "8px 10px", textAlign: "left", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>Conta</th>
                {DESCONTOS_GLOSAS_ANOS.map(ano => (
                  <th key={ano} style={{ padding: "8px 10px", textAlign: "right", color: C.faint, fontSize: 10.5, textTransform: "uppercase" }}>{ano}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {DESCONTOS_GLOSAS_DADOS.map(g => (
                <Fragment key={g.grupo}>
                  <tr style={{ background: "#FEF9C3" }}>
                    <td colSpan={DESCONTOS_GLOSAS_ANOS.length + 1} style={{ padding: "7px 10px", fontWeight: 800, color: "#713F12" }}>{g.grupo}</td>
                  </tr>
                  <tr style={{ borderTop: `1px solid ${C.border}` }}>
                    <td style={{ padding: "7px 10px", color: C.text }}>Descontos</td>
                    {DESCONTOS_GLOSAS_ANOS.map(ano => (
                      <td key={ano} style={{ padding: "7px 10px", textAlign: "right" }}>{g.anos[ano].descontos ? brl(g.anos[ano].descontos) : "—"}</td>
                    ))}
                  </tr>
                  <tr>
                    <td style={{ padding: "7px 10px", color: C.text }}>Glosas</td>
                    {DESCONTOS_GLOSAS_ANOS.map(ano => (
                      <td key={ano} style={{ padding: "7px 10px", textAlign: "right" }}>{g.anos[ano].glosas ? brl(g.anos[ano].glosas) : "—"}</td>
                    ))}
                  </tr>
                  <tr style={{ background: "#DCFCE7", fontWeight: 800 }}>
                    <td style={{ padding: "7px 10px", color: "#166534" }}>Total</td>
                    {DESCONTOS_GLOSAS_ANOS.map(ano => (
                      <td key={ano} style={{ padding: "7px 10px", textAlign: "right", color: "#166534" }}>{brl(g.anos[ano].descontos + g.anos[ano].glosas)}</td>
                    ))}
                  </tr>
                </Fragment>
              ))}
              <tr style={{ borderTop: `2px solid ${C.border}` }}>
                <td style={{ padding: "9px 10px", fontWeight: 900, color: C.text }}>Total Geral</td>
                {DESCONTOS_GLOSAS_ANOS.map(ano => (
                  <td key={ano} style={{ padding: "9px 10px", textAlign: "right", fontWeight: 900, color: C.text }}>{brl(totalPorAno[ano])}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// Demonstrativo do semestre por tipo de serviço: Exames de Sangue, Exames
// de Imagem, Honorários Médicos e Outros — sempre valor real (mesma lógica
// do Centro de Resultado), soma bate exatamente com o total geral do
// módulo.
function PainelReceitaPorTipoServico({ ano }) {
  const { data, loading } = useFetch("/api/financeiro/receita-por-tipo-servico", { ano });
  const CORES = { "Laboratorio de Analises Clinicas": "#8B1A1A", "Exames de Imagem": CB.azul, "Honorarios Medicos": CB.laranja, "Honorários Médicos": CB.laranja, "Medicina Ocupacional": CB.roxo, "Outros": CB.cinza };

  if (loading || !data) return <Carregando />;

  const MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  const rotuloPeriodo = `${MESES_ABREV[data.mes_ini - 1]} a ${MESES_ABREV[data.mes_fim - 1]}`;

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title={<span style={{ fontSize: 19 }}>Receita por Tipo de Serviço — Semestre ({rotuloPeriodo}/{data.ano})</span>}
        subtitle={`Laboratório de Análises Clínicas, Exames de Imagem, Honorários Médicos e Outros · total do período: ${brl(data.total_geral)} (${data.n_meses} meses) · sempre valor real, não muda com o filtro de CNPJ · soma bate com o total geral do módulo`}
        accent={CB.roxo}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginBottom: 16 }}>
          {data.itens.map(it => (
            <KpiCard key={it.categoria} label={`${it.categoria} — Média Mensal`} valor={it.media_mensal} cor={CORES[it.categoria] || CB.cinza} destaque />
          ))}
        </div>
        <ResponsiveContainer width="100%" height={Math.max(200, data.itens.length * 50)}>
          <BarChart data={data.itens} layout="vertical" margin={{ left: 10, right: 90 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis type="number" tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompactoInteiro} />
            <YAxis type="category" dataKey="categoria" tick={{ fontSize: 11, fill: "#64748B" }} width={150} />
            <Tooltip formatter={(v, n, p) => [`${brlInteiro(v)} (${p.payload.percentual}% · média mensal: ${brlInteiro(p.payload.media_mensal)})`, `Total ${rotuloPeriodo}`]} />
            <Bar dataKey="total" radius={[0, 4, 4, 0]} minPointSize={3}>
              {data.itens.map((c, i) => <Cell key={i} fill={CORES[c.categoria] || CB.cinza} />)}
              <LabelList
                dataKey="total"
                content={({ x, y, width, height, value, index }) => {
                  const item = data.itens[index];
                  const pctTexto = `${Math.round(item.percentual)}%`;
                  const valorTexto = brlInteiro(value);
                  const cabeDentro = width >= pctTexto.length * 7 + 14;
                  const centerY = y + height / 2 + 4;
                  if (cabeDentro) {
                    return (
                      <g>
                        <text x={x + width - 8} y={centerY} textAnchor="end" fontSize={11} fontWeight={800} fill="#fff">{pctTexto}</text>
                        <text x={x + width + 8} y={centerY} textAnchor="start" fontSize={11} fontWeight={700} fill="#374151">{valorTexto}</text>
                      </g>
                    );
                  }
                  return (
                    <text x={x + width + 8} y={centerY} textAnchor="start" fontSize={11} fontWeight={700} fill="#374151">
                      {pctTexto} · {valorTexto}
                    </text>
                  );
                }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}

// Demonstrativo do semestre por linha: Assistencial x Ocupacional — mesma
// classificação de osm_atend já usada no painel Home (Faturamento diário
// Ocupacional x Assistencial). As duas linhas cobrem 100% da produção.
function PainelReceitaAssistencialOcupacional({ ano }) {
  const { data, loading } = useFetch("/api/financeiro/receita-assistencial-ocupacional", { ano });
  const CORES_LINHA = { "Assistencial": CB.azul, "Ocupacional": "#722F37", "Outros": CB.cinza };

  if (loading || !data) return <Carregando />;

  const MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  const rotuloPeriodo = `${MESES_ABREV[data.mes_ini - 1]} a ${MESES_ABREV[data.mes_fim - 1]}`;

  // Monta uma linha por mês, com uma coluna por linha de negócio, pro gráfico mensal.
  const mesesChart = data.itens.length
    ? data.itens[0].meses.map((m, i) => {
        const linha = { mes: m.mes, label: m.label };
        data.itens.forEach(it => { linha[it.linha] = it.meses[i].valor; });
        return linha;
      })
    : [];

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title={<span style={{ fontSize: 19 }}>Receita por Linha — Assistencial x Ocupacional — Semestre ({rotuloPeriodo}/{data.ano})</span>}
        subtitle={`Assistencial (consultas/exames de convênio e particular) x Ocupacional (medicina do trabalho/empresas) · total do período: ${brl(data.total_geral)} (${data.n_meses} meses) · sempre valor real · as duas linhas somam 100% do módulo`}
        accent={CB.roxo}
      >
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(180px,1fr))", gap: 12, marginBottom: 16 }}>
          {data.itens.map(it => (
            <KpiCard key={it.linha} label={`${it.linha} — Total do Semestre (${it.percentual}%)`} valor={it.total} formatar={brlInteiro} cor={CORES_LINHA[it.linha] || CB.cinza} destaque />
          ))}
        </div>

        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={mesesChart} margin={{ top: 30, right: 45, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748B" }} />
            <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompactoInteiro} width={60} />
            <Tooltip formatter={(v, n) => [brlInteiro(v), n]} />
            <Legend
              iconType="circle" iconSize={11}
              wrapperStyle={{ fontSize: 12.5, fontWeight: 700, paddingTop: 10 }}
              payload={data.itens.map(it => ({ value: it.linha, type: "line", color: CORES_LINHA[it.linha] || CB.cinza }))}
            />
            {data.itens.map(it => (
              <Line
                key={it.linha}
                dataKey={it.linha}
                name={it.linha}
                stroke={CORES_LINHA[it.linha] || CB.cinza}
                strokeWidth={2.5}
                dot={{ r: 4, fill: CORES_LINHA[it.linha] || CB.cinza }}
              >
                <LabelList
                  dataKey={it.linha}
                  position="top"
                  formatter={brlInteiro}
                  style={{ fontSize: 11, fontWeight: 800, fill: CORES_LINHA[it.linha] || CB.cinza }}
                />
              </Line>
            ))}
          </LineChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}

// Demonstrativo de receita por convênio no ano — só planos de saúde de
// verdade (o backend já filtra fora os convênios de empresa/medicina
// ocupacional), top 5 + Outros.
function PainelReceitaPorConvenio({ ano, cnpj }) {
  // Semestre (Jan a Jun) em vez do ano inteiro.
  const { data, loading } = useFetch("/api/financeiro/receita-por-convenio", { ano, cnpj, top: 5, mes_ini: 1, mes_fim: 6 });
  const CORES = [CB.azul, CB.laranja, CB.verde, CB.roxo, CB.vermelhao, CB.cinza];

  if (loading || !data) return <Carregando />;

  const MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  const rotuloPeriodo = `${MESES_ABREV[data.mes_ini - 1]} a ${MESES_ABREV[data.mes_fim - 1]}`;

  return (
    <div style={{ marginTop: 16 }}>
      <Card
        title={<span style={{ fontSize: 19 }}>Receita por Convênio — Total do Semestre ({rotuloPeriodo}/{data.ano})</span>}
        subtitle={`5 maiores convênios (planos de saúde, exclui empresas) + Outros · total do período: ${brl(data.total_geral)} (${data.n_meses} meses) · ${data.qtd_convenios_total} convênios no total`}
        accent={CB.azul}
      >
        <ResponsiveContainer width="100%" height={Math.max(240, data.itens.length * 46)}>
          <BarChart data={data.itens} layout="vertical" margin={{ left: 10, right: 90 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
            <XAxis type="number" tick={{ fontSize: 10, fill: "#94A3B8" }} tickFormatter={brlCompactoInteiro} />
            <YAxis type="category" dataKey="convenio" tick={{ fontSize: 11, fill: "#64748B" }} width={150} />
            <Tooltip formatter={(v, n, p) => [`${brlInteiro(v)} (${p.payload.percentual}% · média mensal: ${brlInteiro(p.payload.media_mensal)})`, `Total ${rotuloPeriodo}`]} />
            <Bar dataKey="total" radius={[0, 4, 4, 0]} minPointSize={3}>
              {data.itens.map((c, i) => <Cell key={i} fill={CORES[i % CORES.length]} />)}
              {/* Percentual dentro da barra quando cabe; nas barras pequenas
                  demais (ex: 1-2%) o percentual vai na frente do valor, fora. */}
              <LabelList
                dataKey="total"
                content={({ x, y, width, height, value, index }) => {
                  const item = data.itens[index];
                  const pctTexto = `${Math.round(item.percentual)}%`;
                  const valorTexto = brlInteiro(value);
                  const cabeDentro = width >= pctTexto.length * 7 + 14;
                  const centerY = y + height / 2 + 4;
                  if (cabeDentro) {
                    return (
                      <g>
                        <text x={x + width - 8} y={centerY} textAnchor="end" fontSize={11} fontWeight={800} fill="#fff">{pctTexto}</text>
                        <text x={x + width + 8} y={centerY} textAnchor="start" fontSize={11} fontWeight={700} fill="#374151">{valorTexto}</text>
                      </g>
                    );
                  }
                  return (
                    <text x={x + width + 8} y={centerY} textAnchor="start" fontSize={11} fontWeight={700} fill="#374151">
                      {pctTexto} · {valorTexto}
                    </text>
                  );
                }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}

const ABAS_RESULTADOS = [
  { id: "visao_geral",  label: "Visão Geral",   emoji: "📈", cor: CB.cinza },
  { id: "hapvida",      label: "Hapvida CECAN", emoji: "🩺", cor: CB.azul },
  { id: "obstetricia",  label: "Ginecologia",   emoji: "🤰", cor: CB.roxo },
  { id: "recepcoes",    label: "Recepções",     emoji: "🧪", cor: CB.verde },
];

export default function ResultadosFinanceiros() {
  const hoje = new Date();
  const [ano, setAno] = useState(hoje.getFullYear());
  const [cnpj, setCnpj] = useState("interno");
  const [aba, setAba] = useState("visao_geral");

  const anosDisponiveis = [hoje.getFullYear() - 1, hoje.getFullYear()];
  const abaAtual = ABAS_RESULTADOS.find(a => a.id === aba);

  return (
    <div style={{
      background: "#F3F5F9",
      backgroundImage: "radial-gradient(circle, #DCE3EE 1.2px, transparent 1.2px)",
      backgroundSize: "22px 22px", backgroundPosition: "-11px -11px",
      borderRadius: 24, padding: "20px 20px 28px",
      boxShadow: "inset 0 1px 3px rgba(15,23,42,.05), inset 0 0 0 1px rgba(15,23,42,.03)",
    }}>
      {/* Cabeçalho executivo + filtros globais (valem pra todas as abas) */}
      <div style={{
        background: "linear-gradient(120deg, #0B1220 0%, #16294A 40%, #0B4A73 75%, #0891B2 100%)",
        borderRadius: 20, padding: "26px 28px", marginBottom: 22,
        boxShadow: "0 16px 36px rgba(3,105,161,.22), 0 4px 10px rgba(15,23,42,.18)",
        display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 16,
        position: "relative", overflow: "hidden",
      }}>
        <div style={{
          position: "absolute", inset: 0, opacity: 0.5,
          backgroundImage: "radial-gradient(circle, rgba(255,255,255,.10) 1px, transparent 1px)",
          backgroundSize: "16px 16px",
        }} />
        <div style={{
          position: "absolute", top: -70, right: -50, width: 260, height: 260, borderRadius: "50%",
          background: "radial-gradient(circle, rgba(56,189,248,.28) 0%, rgba(56,189,248,0) 70%)",
        }} />
        <div style={{
          position: "absolute", bottom: 0, left: 0, right: 0, height: 3,
          background: "linear-gradient(90deg, transparent, #38BDF8, #A78BFA, #38BDF8, transparent)",
        }} />
        <div style={{ position: "relative" }}>
          <div style={{ fontSize: 21, fontWeight: 900, color: "#fff", display: "flex", alignItems: "center", gap: 11 }}>
            <span style={{
              width: 40, height: 40, borderRadius: 13, background: "rgba(255,255,255,.12)",
              display: "flex", alignItems: "center", justifyContent: "center", fontSize: 19,
              boxShadow: "inset 0 0 0 1px rgba(255,255,255,.18), 0 0 20px rgba(56,189,248,.25)",
            }}>📊</span>
            Resultados Financeiros
          </div>
          <div style={{ fontSize: 13, color: "#BFDBFE", marginTop: 6, marginLeft: 1 }}>Visão executiva para apresentação aos sócios</div>
        </div>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", position: "relative" }}>
          <select value={cnpj} onChange={e => setCnpj(e.target.value)} style={{
            padding: "9px 16px", borderRadius: 11, border: "1px solid rgba(255,255,255,.16)",
            background: "rgba(255,255,255,.10)", color: "#fff", fontSize: 12.5, fontWeight: 700,
            cursor: "pointer", outline: "none", backdropFilter: "blur(4px)",
          }}>
            {CNPJ_FILTRO.map(c => <option key={c.cod} value={c.cod} style={{ color: "#111827" }}>{c.label}</option>)}
          </select>
          <select value={ano} onChange={e => setAno(Number(e.target.value))} style={{
            padding: "9px 16px", borderRadius: 11, border: "1px solid rgba(255,255,255,.16)",
            background: "rgba(255,255,255,.10)", color: "#fff", fontSize: 12.5, fontWeight: 700,
            cursor: "pointer", outline: "none", backdropFilter: "blur(4px)",
          }}>
            {anosDisponiveis.map(a => <option key={a} value={a} style={{ color: "#111827" }}>{a}</option>)}
          </select>
        </div>
      </div>

      {/* Módulo sendo reconstruído por partes — só o impacto do
          descredenciamento Hapvida por enquanto. Abas e demais painéis
          (visão geral, ginecologia, recepções etc.) ficam definidos acima,
          prontos pra voltar conforme o resto for sendo montado. */}
      <PainelImpactoDescredenciamento ano={ano} cnpj={cnpj} />
      <PainelReceitaPorConvenio ano={ano} cnpj={cnpj} />
      <PainelReceitaPorCentroResultado ano={ano} />
      <PainelReceitaPorTipoServico ano={ano} />
      <PainelReceitaAssistencialOcupacional ano={ano} />
      <PainelDescontosGlosas />
      <PainelDemonstrativoResultados2026 />
      <PainelComparativo2025x2026 />
    </div>
  );
}
