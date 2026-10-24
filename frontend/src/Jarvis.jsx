import { useState, useRef, useCallback, useEffect } from "react";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { useAuth } from "./Login";

const API = `${window.location.protocol}//${window.location.host}`;
// Vermelho/bordô da marca Clínica Censo (mesmo usado no resto do Dashboard,
// ver App.jsx) -- a primeira versão usava azul genérico de "assistente de
// IA" que destoava de todo o resto do app (cabeçalho, botões, módulos todos
// usam essa paleta vermelha/dourada). Cores funcionais de estado (ouvindo=
// ciano, pensando=roxo) continuam distintas de propósito -- ajudam a
// reconhecer o estado à primeira vista -- só o "padrão" (idle/falando/chrome
// geral) passou a usar a cor da marca.
const COR = "#8B1A1A";
const COR2 = "#4A0E0E";
const DOURADO = "#B8860B";

// STT (voz->texto) e TTS (texto->voz) acontecem no NAVEGADOR (Web Speech API
// / SpeechSynthesis) — sem instalar Whisper no servidor de produção. A CIA
// fica sempre ouvindo em busca da wake word "CIA", sem precisar clicar em
// nada (como o modo de voz do ChatGPT).
const SpeechRecognitionAPI = window.SpeechRecognition || window.webkitSpeechRecognition;
const TEM_TTS = "speechSynthesis" in window;
// "CIA" (Censo + IA) -- nome escolhido pelo usuário em vez de "Jarvis"
// (evita usar nome de personagem registrado da Marvel/Disney). Aceita "cia"
// e "sia" como grafias alternativas, já que o reconhecimento de voz às
// vezes transcreve o som "ci" como "si".
const WAKE_WORD = /\b[cs]ia\b[,.]?\s*(.*)/i;
// Depois de responder, fica ouvindo direto (sem exigir "CIA" de novo)
// por essa janela -- pedido do usuario, pra poder fazer uma pergunta de
// seguimento sem repetir a wake word toda vez.
const JANELA_SEGUIMENTO_MS = 12000;
// Quem decide quando a fala "terminou" normalmente e o proprio navegador
// (heuristica interna de pausa, nao configuravel) -- pra nao depender só
// disso (inconsistente entre navegadores), se ficar esse tanto sem NENHUMA
// atualizacao no texto reconhecido, assume que a pessoa parou de falar e
// manda a pergunta mesmo sem o navegador ter marcado como "final".
const SILENCIO_FIM_FALA_MS = 1200;

// A 1a chamada de getVoices() costuma vir vazia (as vozes carregam async
// via o evento "voiceschanged") -- sem aguardar isso, o navegador cai no
// fallback mais robotizado dele. Também prioriza vozes "Natural"/"Online"/
// Google (sintese neural, bem mais natural) sobre a voz offline padrão do
// Windows (SAPI), que é a que soa robotizada.
let _vozesCache = [];
if (TEM_TTS) {
  const atualizarVozes = () => { _vozesCache = window.speechSynthesis.getVoices(); };
  atualizarVozes();
  window.speechSynthesis.onvoiceschanged = atualizarVozes;
}

function escolherMelhorVozPt() {
  const vozes = _vozesCache.length ? _vozesCache : window.speechSynthesis.getVoices();
  const ptBr = vozes.filter((v) => /pt-br/i.test(v.lang));
  const pt = ptBr.length ? ptBr : vozes.filter((v) => v.lang?.toLowerCase().startsWith("pt"));
  if (!pt.length) return null;
  return (
    pt.find((v) => /natural|online|neural/i.test(v.name)) ||
    pt.find((v) => /google/i.test(v.name)) ||
    pt[0]
  );
}

function formatarValor(chave, valor) {
  if (valor == null) return "—";
  if (typeof valor === "number") {
    if (/^ano$|_ano$|^hora$|^mes$/i.test(chave)) return String(valor);
    const pareceReais = /vlr|valor|total|faturamento|producao|receita|ticket/i.test(chave) && !/_os$|^total_os$|percentual|pct|atendimentos|pacientes|registros/i.test(chave);
    if (pareceReais) return valor.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    if (/percentual|variac/i.test(chave)) return `${valor}%`;
    return valor.toLocaleString("pt-BR");
  }
  return String(valor);
}

const ICONES_KPI = {
  producao: "📈", faturamento: "💰", receita: "💰", ticket: "🎟️", total: "Σ",
  marcacoes: "📅", atendidos: "✅", faltantes: "⚠️", cancelados: "✕",
  medicos: "🩺", pacientes: "🧑‍🤝‍🧑", previsto: "🔮", real: "📍",
};
function iconePara(chave) {
  const k = chave.toLowerCase();
  for (const termo in ICONES_KPI) if (k.includes(termo)) return ICONES_KPI[termo];
  return "•";
}

// ── Mini-gráfico automático pra listas em formato de série (hora / mês /
// setor) -- detecta a forma dos dados e escolhe os eixos, em vez de só
// jogar tudo numa tabela crua (pedido explícito: "front-end mais robusto").
function detectarSerie(itens) {
  if (!itens?.length) return null;
  const chaves = Object.keys(itens[0]);
  if (chaves.includes("hora") && (chaves.includes("real") || chaves.includes("previsto"))) {
    return { eixoX: "hora", series: ["real", "previsto"].filter((k) => chaves.includes(k)), rotular: (v) => `${v}h` };
  }
  if (chaves.includes("label") && chaves.includes("valor")) {
    return { eixoX: "label", series: ["valor"], rotular: (v) => v };
  }
  if (chaves.includes("setor_nome")) {
    const candidatas = ["previsto", "atendimentos", "total_projetado_ano", "total_ja_produzido"];
    const series = candidatas.filter((k) => chaves.includes(k));
    if (series.length) return { eixoX: "setor_nome", series, rotular: (v) => String(v).replace("Recepção ", "") };
  }
  return null;
}

const CORES_SERIE = [COR, "#D97706", "#0E7490", "#7C3AED"];

function GraficoSerie({ itens }) {
  const serie = detectarSerie(itens);
  if (!serie) return null;
  const dados = itens.map((it) => ({ ...it, [serie.eixoX]: serie.rotular(it[serie.eixoX]) }));
  return (
    <div style={{ marginTop: 14, background: "#FAFBFC", border: "1px solid #F1F5F9", borderRadius: 12, padding: "12px 8px 4px" }}>
      {serie.series.length > 1 && (
        <div style={{ display: "flex", gap: 12, fontSize: 10.5, color: "#64748B", marginBottom: 2, paddingLeft: 6 }}>
          {serie.series.map((s, i) => (
            <span key={s} style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: CORES_SERIE[i % CORES_SERIE.length], display: "inline-block" }} />
              {s}
            </span>
          ))}
        </div>
      )}
      <ResponsiveContainer width="100%" height={160}>
        <BarChart data={dados} margin={{ top: 4, right: 10, left: -18, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" vertical={false} />
          <XAxis dataKey={serie.eixoX} tick={{ fontSize: 10, fill: "#94A3B8" }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 10, fill: "#94A3B8" }} axisLine={false} tickLine={false} width={40}
            tickFormatter={(v) => v >= 1000 ? `${Math.round(v / 1000)}k` : v} />
          <Tooltip
            contentStyle={{ borderRadius: 10, border: "1px solid #E5E7EB", fontSize: 11.5 }}
            formatter={(v, nome) => [formatarValor(nome, v), nome.replace(/_/g, " ")]}
          />
          {serie.series.map((s, i) => (
            // fill no próprio <Bar> colore a série inteira (caso "hora": 2
            // séries, 1 cor cada). <Cell> por ponto só entra no caso
            // "setor_nome" (1 série só, mas 1 cor por setor) -- sem essa
            // distinção, um <Cell> sozinho (sem 1 por ponto) só pinta a
            // PRIMEIRA barra e deixa o resto na cor padrão do Recharts
            // (bug real, visto na captura: só a barra das 6h saía colorida).
            <Bar key={s} dataKey={s} radius={[5, 5, 0, 0]} maxBarSize={28} fill={CORES_SERIE[i % CORES_SERIE.length]}>
              {serie.eixoX === "setor_nome" && dados.map((_, di) => <Cell key={di} fill={CORES_SERIE[di % CORES_SERIE.length]} />)}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function TabelaLista({ nome, itens }) {
  if (!itens || itens.length === 0) return null;
  const colunas = Object.keys(itens[0]);
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 800, color: "#64748B", textTransform: "uppercase", letterSpacing: .3, marginBottom: 8 }}>
        {nome.replace(/_/g, " ")} ({itens.length})
      </div>
      <GraficoSerie itens={itens} />
      <div style={{ maxHeight: 280, overflowY: "auto", border: "1px solid #F1F5F9", borderRadius: 10, marginTop: 10 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12.5 }}>
          <thead>
            <tr style={{ background: "#F8FAFC", position: "sticky", top: 0 }}>
              {colunas.map((c) => (
                <th key={c} style={{ textAlign: "left", padding: "8px 10px", color: "#64748B", fontSize: 10.5, textTransform: "uppercase" }}>{c.replace(/_/g, " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {itens.map((item, i) => (
              <tr key={i} style={{ borderTop: "1px solid #F1F5F9", background: i % 2 ? "#FCFCFD" : "#fff" }}>
                {colunas.map((c) => (
                  <td key={c} style={{ padding: "7px 10px", color: "#0F172A" }}>{formatarValor(c, item[c])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PainelDados({ dados }) {
  if (!dados || typeof dados !== "object") return null;
  const linhas = [];
  const listas = [];
  for (const [k, v] of Object.entries(dados)) {
    if (Array.isArray(v)) {
      if (v.length && typeof v[0] === "object") listas.push([k, v]);
    } else if (v && typeof v === "object") {
      Object.entries(v).forEach(([k2, v2]) => linhas.push([`${k} · ${k2}`, v2]));
    } else {
      linhas.push([k, v]);
    }
  }
  return (
    <>
      {linhas.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 16 }}>
          {linhas.map(([k, v]) => (
            <div key={k} style={{
              background: "linear-gradient(145deg, #F8FAFC 0%, #F1F5F9 100%)",
              border: "1px solid #ECEFF3", borderLeft: `3px solid ${COR}`, borderRadius: 12,
              padding: "10px 16px", minWidth: 128,
            }}>
              <div style={{ fontSize: 10, color: "#94A3B8", textTransform: "uppercase", fontWeight: 700, display: "flex", alignItems: "center", gap: 4 }}>
                <span>{iconePara(k)}</span>{k.replace(/_/g, " ")}
              </div>
              <div style={{ fontSize: 17, fontWeight: 800, color: "#0F172A", marginTop: 2 }}>{formatarValor(k, v)}</div>
            </div>
          ))}
        </div>
      )}
      {listas.map(([nome, itens]) => <TabelaLista key={nome} nome={nome} itens={itens} />)}
    </>
  );
}

// ── Orb — núcleo visual com anel de ondas ao redor, reagindo ao áudio em
// tempo real via CSS custom property (--nivel), atualizada fora do ciclo do
// React (requestAnimationFrame direto no DOM) pra não re-renderizar a
// árvore inteira 60x/s.
const CORES_MODO = {
  idle:     { a: COR, b: COR2 },
  ouvindo:  { a: "#06B6D4", b: "#0E7490" },
  pensando: { a: "#7C3AED", b: "#4C1D95" },
  falando:  { a: COR, b: "#B8403F" },
};
const N_BARRAS_ONDA = 16;

function Orb({ modo, orbRef, onClick }) {
  const cor = CORES_MODO[modo] || CORES_MODO.idle;
  const barras = Array.from({ length: N_BARRAS_ONDA });
  return (
    // "--nivel" é definido aqui (no wrapper, não no círculo em si) porque
    // CSS custom properties só cascateiam pra descendentes -- as barras da
    // onda são IRMÃS do círculo, não filhas dele, então precisavam de um
    // ancestral comum pra enxergar a mesma variável.
    <div ref={orbRef} style={{ "--nivel": 0, position: "relative", width: 230, height: 230, margin: "0 auto" }}>
      {barras.map((_, i) => {
        const ang = (i / N_BARRAS_ONDA) * 360;
        const atraso = (i % 4) * 0.07;
        return (
          // Rotação fica no wrapper estático (inline, nunca tocado pela
          // animação CSS); só o filho interno anima o scaleY -- se a
          // rotação estivesse no MESMO elemento que anima, a animação
          // substituiria o transform inteiro a cada frame e todas as
          // barras colapsariam pro mesmo ângulo (bug real, pego na revisão).
          <div key={i} style={{
            position: "absolute", left: "50%", top: "50%", width: 3, height: 14,
            transform: `rotate(${ang}deg) translate(0, -98px)`,
            transformOrigin: "center 98px",
          }}>
            <div className="jarvis-onda-barra" style={{
              width: "100%", height: "100%", background: cor.a, borderRadius: 3, opacity: 0.55,
              animationDelay: `${atraso}s`,
            }} />
          </div>
        );
      })}
      <div
        onClick={onClick}
        style={{
          width: 150, height: 150, borderRadius: "50%", cursor: "pointer",
          position: "absolute", left: "50%", top: "50%", transform: "translate(-50%,-50%)",
          background: `radial-gradient(circle at 35% 30%, ${cor.a}, ${cor.b} 70%)`,
          boxShadow: `0 0 calc(30px + var(--nivel) * 70px) calc(4px + var(--nivel) * 14px) ${cor.a}77, 0 10px 40px rgba(15,23,42,.25)`,
          transition: "background 0.4s ease, box-shadow 0.05s linear",
          animation: modo === "idle" ? "respirar 3.5s ease-in-out infinite" : modo === "pensando" ? "girar 1.4s linear infinite" : "none",
        }}
      >
        <div style={{
          position: "absolute", inset: 16, borderRadius: "50%",
          background: `radial-gradient(circle at 40% 35%, rgba(255,255,255,.55), rgba(255,255,255,0) 60%)`,
          pointerEvents: "none",
        }} />
        <div style={{
          position: "absolute", inset: -3, borderRadius: "50%", pointerEvents: "none",
          border: `2px solid ${cor.a}55`,
          transform: "scale(calc(1.15 + var(--nivel) * 0.35))",
          opacity: "calc(0.7 - var(--nivel) * 0.3)",
          transition: "transform 0.1s linear",
        }} />
      </div>
    </div>
  );
}

const SUGESTOES = [
  { grupo: "Produção", icone: "📈", texto: "qual a produção esse mês" },
  { grupo: "Faturamento", icone: "💰", texto: "como está o faturamento este ano" },
  { grupo: "Previsão", icone: "🔮", texto: "divida a previsão de produção do dia por setor" },
  { grupo: "Agenda", icone: "🩺", texto: "quais médicos têm agenda hoje" },
  { grupo: "Pacientes", icone: "🧑‍🤝‍🧑", texto: "lista de pacientes atendidos hoje na recepção ocupacional" },
  { grupo: "Bate-papo", icone: "💬", texto: "oi cia, tudo bem?" },
];

function Bolha({ papel, children }) {
  const souUsuario = papel === "user";
  return (
    <div style={{ display: "flex", justifyContent: souUsuario ? "flex-end" : "flex-start", marginBottom: 14 }}>
      <div style={{
        maxWidth: "88%",
        background: souUsuario ? `linear-gradient(135deg, ${COR} 0%, ${COR2} 100%)` : "#fff",
        color: souUsuario ? "#fff" : "#0F172A",
        borderRadius: souUsuario ? "16px 16px 4px 16px" : "16px 16px 16px 4px",
        padding: souUsuario ? "10px 16px" : "16px 18px",
        boxShadow: souUsuario ? "0 4px 14px rgba(37,99,235,.25)" : "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
        fontSize: souUsuario ? 13.5 : 14.5,
        fontWeight: souUsuario ? 600 : 400,
      }}>
        {children}
      </div>
    </div>
  );
}

// Efeito de texto "sendo digitado" -- só na resposta mais recente (pedido:
// "sentir que realmente está" interagindo com uma IA de verdade, não um
// texto estático que só aparece pronto).
function TextoDigitado({ texto, ativo }) {
  const [visivel, setVisivel] = useState(ativo ? "" : texto);
  useEffect(() => {
    if (!ativo) { setVisivel(texto); return; }
    setVisivel("");
    let i = 0;
    const passo = Math.max(1, Math.ceil(texto.length / 70));
    const id = setInterval(() => {
      i += passo;
      setVisivel(texto.slice(0, i));
      if (i >= texto.length) clearInterval(id);
    }, 16);
    return () => clearInterval(id);
  }, [texto, ativo]);
  return <>{visivel}</>;
}

export default function Jarvis() {
  const { user } = useAuth();
  const primeiroNome = (user?.nome || "").trim().split(" ")[0] || "";

  const [modo, setModo] = useState("idle"); // idle | ouvindo | pensando | falando
  const [iniciando, setIniciando] = useState(true); // sequência de "ligando" ao abrir a tela
  const [ativo, setAtivo] = useState(true); // escuta contínua ligada
  const [transcricao, setTranscricao] = useState("");
  const [historico, setHistorico] = useState([]); // mais recente primeiro
  const [textoManual, setTextoManual] = useState("");
  const [emailDestino, setEmailDestino] = useState("");
  const [enviandoPdf, setEnviandoPdf] = useState(false);
  const [statusPdf, setStatusPdf] = useState(null);
  const [baixandoPdf, setBaixandoPdf] = useState(false);
  const [permissaoNegada, setPermissaoNegada] = useState(false);

  // ── Modo reunião (Fase 2) -- grava/transcreve tudo que é dito, sem
  // identificar quem fala (decisão explícita do usuário de deixar pra
  // depois), e gera ata ao finalizar.
  const [modoReuniao, setModoReuniao] = useState(false);
  const [transcricaoReuniao, setTranscricaoReuniao] = useState("");
  const [duracaoReuniao, setDuracaoReuniao] = useState(0); // segundos, só pra mostrar o timer
  const [participantesReuniao, setParticipantesReuniao] = useState("");
  const [gerandoAta, setGerandoAta] = useState(false);
  const [ata, setAta] = useState(null);
  const [emailAtaDestino, setEmailAtaDestino] = useState("");
  const [enviandoAtaPdf, setEnviandoAtaPdf] = useState(false);
  const [statusAtaPdf, setStatusAtaPdf] = useState(null);
  const [baixandoAtaPdf, setBaixandoAtaPdf] = useState(false);
  const [mostrarHistorico, setMostrarHistorico] = useState(false);
  const [historicoReunioes, setHistoricoReunioes] = useState([]);
  const [carregandoHistorico, setCarregandoHistorico] = useState(false);

  const orbRef = useRef(null);
  const modoRef = useRef("idle");
  const ativoRef = useRef(true);
  const perguntarAoJarvisRef = useRef(null);
  const silencioTimeoutRef = useRef(null);
  const recognitionRef = useRef(null);
  const audioCtxRef = useRef(null);
  const rafRef = useRef(null);
  const timeoutComandoRef = useRef(null);
  const fimFeedRef = useRef(null);
  const modoReuniaoRef = useRef(false);
  const inicioReuniaoRef = useRef(null);
  const timerReuniaoRef = useRef(null);
  const fimTranscricaoRef = useRef(null);

  const setModoSync = (m) => { modoRef.current = m; setModo(m); };

  useEffect(() => {
    fimFeedRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [historico]);

  useEffect(() => {
    fimTranscricaoRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [transcricaoReuniao]);

  useEffect(() => () => clearInterval(timerReuniaoRef.current), []);

  // ── Análise de volume do microfone (orb reage enquanto ouve) ───────────
  const iniciarAnaliseAudio = useCallback(async () => {
    if (audioCtxRef.current) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      audioCtxRef.current = { ctx, stream, analyser };
      const data = new Uint8Array(analyser.frequencyBinCount);
      const loop = () => {
        analyser.getByteFrequencyData(data);
        const media = data.reduce((a, b) => a + b, 0) / data.length;
        const nivel = Math.min(1, media / 70);
        orbRef.current?.style.setProperty("--nivel", nivel.toFixed(3));
        rafRef.current = requestAnimationFrame(loop);
      };
      loop();
    } catch {
      setPermissaoNegada(true);
    }
  }, []);

  // ── Pseudo-amplitude enquanto fala (TTS não expõe o áudio real) ────────
  const animarFala = useCallback(() => {
    let t = 0;
    const loop = () => {
      t += 0.25;
      const nivel = (Math.sin(t) + 1) / 2 * 0.55 + 0.15;
      orbRef.current?.style.setProperty("--nivel", nivel.toFixed(3));
      if (window.speechSynthesis.speaking) rafRef.current = requestAnimationFrame(loop);
      else orbRef.current?.style.setProperty("--nivel", 0);
    };
    loop();
  }, []);

  const falar = useCallback((texto) => {
    if (!TEM_TTS || !texto) { setModoSync("idle"); return; }
    setModoSync("falando");
    recognitionRef.current?.stop(); // evita o Jarvis se ouvir falando
    const utt = new SpeechSynthesisUtterance(texto);
    utt.lang = "pt-BR";
    utt.rate = 1.03;  // levemente mais rapido que o padrao (1.0) soa menos robotico
    utt.pitch = 1.0;
    const voz = escolherMelhorVozPt();
    if (voz) utt.voice = voz;
    utt.onstart = () => animarFala();
    const retomarEscuta = () => {
      // Depois de responder, fica OUVINDO O COMANDO direto por mais alguns
      // segundos (sem precisar dizer "Jarvis" de novo) -- pedido explicito
      // do usuario: ele reclamou de ter que repetir a wake word toda vez,
      // mesmo logo depois de uma pergunta anterior. Só volta a exigir
      // "Jarvis" se esse intervalo passar sem pergunta nenhuma.
      setModoSync(ativoRef.current ? "ouvindo_comando" : "idle");
      setTranscricao("");
      clearTimeout(timeoutComandoRef.current);
      if (ativoRef.current) {
        timeoutComandoRef.current = setTimeout(() => {
          if (modoRef.current === "ouvindo_comando") setModoSync("ouvindo");
        }, JANELA_SEGUIMENTO_MS);
      }
      // O reconhecimento foi parado de proposito antes de falar (evita o
      // Jarvis se ouvir); como ele so reinicia sozinho dentro do proprio
      // onend (e naquele momento o modo ainda era "falando", entao pulava o
      // restart), precisa religar explicitamente aqui -- sem isso o
      // reconhecimento ficava morto pro resto da sessao apos a 1a resposta
      // (bug real: usuario relatou que a segunda pergunta nunca era ouvida).
      if (ativoRef.current) { try { recognitionRef.current?.start(); } catch { /* ja rodando */ } }
    };
    utt.onend = retomarEscuta;
    utt.onerror = retomarEscuta;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(utt);
  }, [animarFala]);

  // ── Sequência de "chegada" ao abrir a tela -- saudação falada e humanizada
  // (não um aviso de sistema tipo "online"/"inicializado"), pra dar a
  // sensação de estar falando com alguém de verdade, não só carregando uma
  // página. Só dispara 1x por sessão da tela.
  useEffect(() => {
    const saudacoes = primeiroNome
      ? [`Oi, ${primeiroNome}! Cheguei, tchê. Pode perguntar o que quiser.`,
         `E aí, ${primeiroNome}! Tô por aqui, bah. Manda a pergunta.`]
      : [`Oi, tchê! Cheguei. Pode perguntar o que quiser.`];
    const saudacao = saudacoes[Math.floor(Math.random() * saudacoes.length)];
    const t = setTimeout(() => {
      setIniciando(false);
      falar(saudacao);
    }, 1100);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const perguntarAoJarvis = useCallback((texto) => {
    const t = (texto || "").trim();
    if (!t) return;
    clearTimeout(timeoutComandoRef.current);
    setModoSync("pensando");
    setTranscricao(t);
    // Conversa estilo ChatGPT, com memoria do papo -- manda os ultimos
    // turnos (mais antigo primeiro) pro backend incluir no contexto do
    // modelo. historico[] guarda do mais recente pro mais antigo, por isso
    // o slice+reverse antes de montar os turnos.
    const historicoEnvio = [...historico].slice(0, 8).reverse().flatMap((h) => ([
      { papel: "user", texto: h.pergunta },
      { papel: "assistant", texto: h.resposta_texto },
    ]));
    fetch(`${API}/api/jarvis/perguntar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pergunta: t, historico: historicoEnvio, usuario_nome: primeiroNome }),
    })
      .then((r) => r.json())
      .then((resp) => {
        setHistorico((h) => [resp, ...h].slice(0, 20));
        falar(resp.resposta_texto);
      })
      .catch(() => {
        const erro = { pergunta: t, skill: null, dados: null, resposta_texto: "Erro ao falar com o servidor." };
        setHistorico((h) => [erro, ...h].slice(0, 20));
        falar(erro.resposta_texto);
      });
  }, [falar, historico, primeiroNome]);
  // O listener de reconhecimento contínuo é montado 1x (useEffect com deps
  // vazias, mais abaixo) e chamaria sempre a 1a versão desta função, sempre
  // com historico=[] (closure obsoleta) -- por isso ele chama via ref, que
  // é sempre mantido atualizado aqui.
  perguntarAoJarvisRef.current = perguntarAoJarvis;

  // ── Reconhecimento contínuo + detecção da wake word "Jarvis" ───────────
  useEffect(() => {
    if (!SpeechRecognitionAPI) return;

    const rec = new SpeechRecognitionAPI();
    rec.lang = "pt-BR";
    rec.continuous = true;
    rec.interimResults = true;

    rec.onresult = (ev) => {
      const ultimo = ev.results[ev.results.length - 1];
      const texto = ultimo[0].transcript.trim();

      // Modo reunião acumula TUDO que é dito (inclusive as perguntas feitas
      // pra CIA durante a reunião e as respostas dela) -- é paralelo ao
      // fluxo normal de pergunta/resposta abaixo, não substitui ele.
      if (modoReuniaoRef.current && ultimo.isFinal && texto) {
        setTranscricaoReuniao((t) => (t ? `${t} ${texto}` : texto));
      }

      if (modoRef.current === "pensando" || modoRef.current === "falando") return;

      if (modoRef.current === "ouvindo_comando") {
        setTranscricao(texto);
        clearTimeout(silencioTimeoutRef.current);
        if (ultimo.isFinal) {
          perguntarAoJarvisRef.current?.(texto);
        } else if (texto.length > 2) {
          // Navegador ainda não marcou como final -- se ficar
          // SILENCIO_FIM_FALA_MS sem nenhuma atualização nova (nenhuma
          // palavra a mais), assume que a pessoa parou de falar e manda
          // mesmo assim, em vez de ficar esperando o navegador decidir.
          silencioTimeoutRef.current = setTimeout(() => {
            if (modoRef.current === "ouvindo_comando") perguntarAoJarvisRef.current?.(texto);
          }, SILENCIO_FIM_FALA_MS);
        }
        return;
      }

      // idle / ouvindo (ambiente) -> procura a wake word
      const m = texto.match(WAKE_WORD);
      if (m) {
        const comando = (m[1] || "").trim();
        if (comando.length > 3 && ultimo.isFinal) {
          perguntarAoJarvisRef.current?.(comando);
        } else if (ultimo.isFinal) {
          // só disse "Jarvis" -> abre escuta ativa pro comando
          setModoSync("ouvindo_comando");
          setTranscricao("");
          clearTimeout(timeoutComandoRef.current);
          timeoutComandoRef.current = setTimeout(() => {
            if (modoRef.current === "ouvindo_comando") setModoSync(ativoRef.current ? "ouvindo" : "idle");
          }, JANELA_SEGUIMENTO_MS);
        }
      }
    };

    rec.onend = () => {
      if (ativoRef.current && modoRef.current !== "falando" && modoRef.current !== "pensando") {
        try { rec.start(); } catch { /* já rodando */ }
      }
    };
    rec.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        setPermissaoNegada(true);
        setAtivo(false);
        ativoRef.current = false;
      }
    };

    recognitionRef.current = rec;
    if (ativoRef.current) {
      iniciarAnaliseAudio();
      setModoSync("ouvindo");
      try { rec.start(); } catch { /* noop */ }
    }

    return () => {
      ativoRef.current = false;
      rec.onend = null;
      rec.stop();
      clearTimeout(silencioTimeoutRef.current);
      cancelAnimationFrame(rafRef.current);
      if (audioCtxRef.current) {
        audioCtxRef.current.stream.getTracks().forEach((t) => t.stop());
        audioCtxRef.current.ctx.close();
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const alternarAtivo = () => {
    const novo = !ativo;
    setAtivo(novo);
    ativoRef.current = novo;
    if (novo) {
      iniciarAnaliseAudio();
      setModoSync("ouvindo");
      try { recognitionRef.current?.start(); } catch { /* noop */ }
    } else {
      setModoSync("idle");
      recognitionRef.current?.stop();
      window.speechSynthesis?.cancel();
    }
  };

  const cliqueNoOrb = () => {
    if (modoRef.current === "pensando" || modoRef.current === "falando") return;
    if (!ativo) alternarAtivo();
    else { try { recognitionRef.current?.start(); } catch { /* ja rodando */ } }
    setModoSync("ouvindo_comando");
    setTranscricao("");
    clearTimeout(timeoutComandoRef.current);
    timeoutComandoRef.current = setTimeout(() => {
      if (modoRef.current === "ouvindo_comando") setModoSync(ativoRef.current ? "ouvindo" : "idle");
    }, JANELA_SEGUIMENTO_MS);
  };

  const iniciarReuniao = () => {
    if (!ativo) alternarAtivo();
    else { try { recognitionRef.current?.start(); } catch { /* ja rodando */ } }
    setAta(null);
    setTranscricaoReuniao("");
    setDuracaoReuniao(0);
    inicioReuniaoRef.current = new Date();
    modoReuniaoRef.current = true;
    setModoReuniao(true);
    clearInterval(timerReuniaoRef.current);
    timerReuniaoRef.current = setInterval(() => {
      setDuracaoReuniao(Math.round((Date.now() - inicioReuniaoRef.current.getTime()) / 1000));
    }, 1000);
  };

  const finalizarReuniao = () => {
    clearInterval(timerReuniaoRef.current);
    modoReuniaoRef.current = false;
    setModoReuniao(false);
    const duracaoMin = (Date.now() - inicioReuniaoRef.current.getTime()) / 60000;
    setGerandoAta(true);
    fetch(`${API}/api/jarvis/reuniao/finalizar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        transcricao: transcricaoReuniao,
        duracao_min: duracaoMin,
        participantes: participantesReuniao,
        data_inicio: inicioReuniaoRef.current.toLocaleString("pt-BR"),
      }),
    })
      .then((r) => r.json())
      .then(setAta)
      .catch(() => setAta({ resumo: "Erro ao gerar a ata.", decisoes: [], acoes: [], insights: [], alertas: [], transcricao: transcricaoReuniao }))
      .finally(() => setGerandoAta(false));
  };

  const _baixarArquivo = (blob, nomeArquivo) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nomeArquivo;
    a.click();
    URL.revokeObjectURL(url);
  };

  const baixarAtaPdf = () => {
    if (!ata) return;
    setBaixandoAtaPdf(true);
    fetch(`${API}/api/jarvis/reuniao/pdf/baixar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ata }),
    })
      .then((r) => r.blob())
      .then((blob) => _baixarArquivo(blob, "CIA_ata_reuniao.pdf"))
      .catch(() => setStatusAtaPdf({ ok: false, erro: "Erro ao baixar o PDF" }))
      .finally(() => setBaixandoAtaPdf(false));
  };

  const enviarAtaPdf = () => {
    const destino = (emailAtaDestino || "").trim();
    if (!destino || !ata) return;
    setEnviandoAtaPdf(true);
    setStatusAtaPdf(null);
    fetch(`${API}/api/jarvis/reuniao/pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ata, destinatario: destino }),
    })
      .then((r) => r.json())
      .then(setStatusAtaPdf)
      .catch(() => setStatusAtaPdf({ ok: false, erro: "Erro de rede" }))
      .finally(() => setEnviandoAtaPdf(false));
  };

  const abrirHistorico = () => {
    setMostrarHistorico(true);
    setAta(null);
    setCarregandoHistorico(true);
    fetch(`${API}/api/jarvis/reuniao/historico`)
      .then((r) => r.json())
      .then((d) => setHistoricoReunioes(d.atas || []))
      .catch(() => setHistoricoReunioes([]))
      .finally(() => setCarregandoHistorico(false));
  };

  const abrirAtaDoHistorico = (id) => {
    fetch(`${API}/api/jarvis/reuniao/${id}`)
      .then((r) => r.json())
      .then((d) => { setAta(d); setMostrarHistorico(false); })
      .catch(() => {});
  };

  const baixarPdf = (item) => {
    setBaixandoPdf(true);
    fetch(`${API}/api/jarvis/pdf/baixar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pergunta: item.pergunta, resposta_texto: item.resposta_texto, dados: item.dados }),
    })
      .then((r) => r.blob())
      .then((blob) => _baixarArquivo(blob, "CIA_consulta.pdf"))
      .catch(() => setStatusPdf({ ok: false, erro: "Erro ao baixar o PDF" }))
      .finally(() => setBaixandoPdf(false));
  };

  const enviarPdf = (item, idx) => {
    const destino = (emailDestino || "").trim();
    if (!destino) return;
    setEnviandoPdf(true);
    setStatusPdf(null);
    fetch(`${API}/api/jarvis/pdf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pergunta: item.pergunta, resposta_texto: item.resposta_texto, dados: item.dados, destinatario: destino }),
    })
      .then((r) => r.json())
      .then((resp) => setStatusPdf({ idx, ...resp }))
      .catch(() => setStatusPdf({ idx, ok: false, erro: "Erro de rede" }))
      .finally(() => setEnviandoPdf(false));
  };

  const enviarTexto = () => {
    if (!textoManual.trim()) return;
    perguntarAoJarvis(textoManual);
    setTextoManual("");
  };

  const LEGENDA_MODO = {
    idle: "Em espera — clique na esfera ou ative a escuta",
    ouvindo: 'Ouvindo o ambiente — diga "CIA" pra ativar',
    ouvindo_comando: "Pode perguntar...",
    pensando: "Consultando o Dashboard...",
    falando: "Respondendo...",
  };
  const PONTO_STATUS = {
    idle: "#94A3B8", ouvindo: "#06B6D4", ouvindo_comando: "#06B6D4", pensando: "#7C3AED", falando: COR,
  };

  const conversaOrdenada = [...historico].reverse();

  return (
    <div style={{ maxWidth: 860, margin: "0 auto" }}>
      {/* Header */}
      <div style={{
        background: `linear-gradient(135deg, ${COR} 0%, ${COR2} 100%)`,
        borderRadius: 20, padding: "22px 28px", marginBottom: 18, color: "#fff",
        display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10,
      }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 900, display: "flex", alignItems: "center", gap: 8 }}>
            <span>🤖 CIA</span>
            <span style={{
              fontSize: 9, fontWeight: 800, background: "rgba(255,255,255,.18)", padding: "3px 9px",
              borderRadius: 99, textTransform: "uppercase", letterSpacing: .5,
            }}>beta</span>
          </div>
          <div style={{ fontSize: 12.5, opacity: .85, marginTop: 2 }}>
            {primeiroNome ? `E aí, ${primeiroNome}! ` : ""}Converse sobre qualquer assunto — ou pergunte sobre os dados do Dashboard
          </div>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {SpeechRecognitionAPI && !modoReuniao && (
            <button onClick={iniciarReuniao} style={{
              padding: "8px 16px", borderRadius: 20, border: "1.5px solid rgba(255,255,255,.35)", cursor: "pointer",
              background: "rgba(255,255,255,.12)", color: "#fff", fontWeight: 700, fontSize: 12,
              display: "flex", alignItems: "center", gap: 6,
            }}>🎙️ Nova Reunião</button>
          )}
          {!modoReuniao && (
            <button onClick={abrirHistorico} style={{
              padding: "8px 16px", borderRadius: 20, border: "1.5px solid rgba(255,255,255,.35)", cursor: "pointer",
              background: "rgba(255,255,255,.12)", color: "#fff", fontWeight: 700, fontSize: 12,
            }}>📋 Histórico</button>
          )}
          {SpeechRecognitionAPI && (
            <button onClick={alternarAtivo} style={{
              padding: "8px 16px", borderRadius: 20, border: "1.5px solid rgba(255,255,255,.35)", cursor: "pointer",
              background: ativo ? "rgba(16,185,129,.2)" : "rgba(255,255,255,.1)", color: "#fff",
              fontWeight: 700, fontSize: 12, display: "flex", alignItems: "center", gap: 6,
            }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: ativo ? "#34D399" : "#94A3B8", display: "inline-block" }} />
              {ativo ? "Escuta ativa" : "Escuta desligada"}
            </button>
          )}
        </div>
      </div>

      {!SpeechRecognitionAPI && (
        <div style={{ fontSize: 11.5, color: "#DC2626", marginBottom: 10, fontWeight: 600 }}>
          Reconhecimento de voz não disponível neste navegador — use Chrome ou Edge. Digite abaixo.
        </div>
      )}
      {permissaoNegada && (
        <div style={{ fontSize: 11.5, color: "#DC2626", marginBottom: 10, fontWeight: 600 }}>
          Permissão de microfone negada — libere o acesso ao microfone pro site e recarregue a página.
        </div>
      )}

      {/* Orb hero */}
      <div style={{
        display: "flex", flexDirection: "column", alignItems: "center", padding: "30px 0 56px",
        background: "radial-gradient(ellipse at center, #FFF9F5 0%, transparent 70%)",
      }}>
        <div style={{
          animation: iniciando ? "materializar 1.1s cubic-bezier(.2,.9,.3,1.2)" : "none",
        }}>
          <Orb modo={iniciando ? "idle" : (modo === "ouvindo_comando" ? "ouvindo" : modo)} orbRef={orbRef} onClick={cliqueNoOrb} />
        </div>
        <div style={{ marginTop: 14, fontSize: 13, fontWeight: 700, color: "#334155", minHeight: 20, textAlign: "center", display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: iniciando ? DOURADO : PONTO_STATUS[modo], flexShrink: 0 }} />
          {iniciando ? "chegando..." : LEGENDA_MODO[modo]}
        </div>
        {transcricao && (modo === "ouvindo_comando" || modo === "pensando") && (
          <div style={{ marginTop: 4, fontSize: 13, color: "#64748B", fontStyle: "italic", textAlign: "center", maxWidth: 500 }}>"{transcricao}"</div>
        )}
        {SpeechRecognitionAPI && !iniciando && (
          // Botão bem explícito pra silenciar o microfone -- o pill do
          // cabeçalho já fazia isso, mas pouco óbvio que era clicável
          // (parecia só indicador de status). Esse fica colado no "palco"
          // principal (embaixo do orb), onde a atenção já está.
          <button onClick={alternarAtivo} style={{
            marginTop: 16, padding: "9px 18px", borderRadius: 999, cursor: "pointer",
            border: `1.5px solid ${ativo ? "#FCA5A5" : "#A7F3D0"}`,
            background: ativo ? "#FEF2F2" : "#ECFDF5", color: ativo ? "#B91C1C" : "#047857",
            fontWeight: 700, fontSize: 12.5, display: "flex", alignItems: "center", gap: 7,
          }}>
            <span>{ativo ? "🔇" : "🎤"}</span>
            {ativo ? "Clique pra não escutar" : "Clique pra voltar a escutar"}
          </button>
        )}
      </div>

      {/* Modo reunião -- gravação em andamento */}
      {modoReuniao && (
        <div style={{
          background: "#fff", borderRadius: 18, padding: 20, marginBottom: 16,
          boxShadow: "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#DC2626", animation: "piscar 1.2s ease-in-out infinite" }} />
              <span style={{ fontWeight: 800, fontSize: 13.5, color: "#0F172A" }}>Gravando reunião</span>
              <span style={{ fontSize: 12.5, color: "#94A3B8", fontVariantNumeric: "tabular-nums" }}>
                {String(Math.floor(duracaoReuniao / 60)).padStart(2, "0")}:{String(duracaoReuniao % 60).padStart(2, "0")}
              </span>
            </div>
            <button onClick={finalizarReuniao} style={{
              padding: "8px 18px", borderRadius: 10, border: "none", cursor: "pointer",
              background: "#0F172A", color: "#fff", fontWeight: 700, fontSize: 12.5,
            }}>Finalizar reunião</button>
          </div>
          <input
            value={participantesReuniao}
            onChange={(e) => setParticipantesReuniao(e.target.value)}
            placeholder="Participantes (opcional, ex: Pedro, Ana, Carlos)"
            style={{ width: "100%", padding: "8px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 12.5, marginBottom: 12, boxSizing: "border-box" }}
          />
          <div style={{
            maxHeight: 220, overflowY: "auto", background: "#FAFBFC", border: "1px solid #F1F5F9",
            borderRadius: 10, padding: 14, fontSize: 13, color: "#334155", lineHeight: 1.6,
          }}>
            {transcricaoReuniao || <span style={{ color: "#94A3B8", fontStyle: "italic" }}>Ouvindo... fale normalmente, a transcrição vai aparecer aqui.</span>}
            <div ref={fimTranscricaoRef} />
          </div>
        </div>
      )}

      {/* Histórico de reuniões */}
      {mostrarHistorico && (
        <div style={{
          background: "#fff", borderRadius: 18, padding: 20, marginBottom: 16,
          boxShadow: "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div style={{ fontSize: 15, fontWeight: 900, color: "#8B1A1A" }}>Histórico de Reuniões</div>
            <button onClick={() => setMostrarHistorico(false)} style={{
              padding: "6px 14px", borderRadius: 8, border: "1.5px solid #E2E8F0", cursor: "pointer",
              background: "#fff", color: "#64748B", fontWeight: 700, fontSize: 12,
            }}>Fechar</button>
          </div>
          {carregandoHistorico ? (
            <div style={{ textAlign: "center", color: "#94A3B8", fontSize: 12.5, padding: 20 }}>Carregando...</div>
          ) : historicoReunioes.length === 0 ? (
            <div style={{ textAlign: "center", color: "#94A3B8", fontSize: 12.5, padding: 20 }}>Nenhuma reunião registrada ainda.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {historicoReunioes.map((h) => (
                <button key={h.id} onClick={() => abrirAtaDoHistorico(h.id)} style={{
                  textAlign: "left", background: "#F8FAFC", border: "1px solid #F1F5F9", borderRadius: 12,
                  padding: "12px 16px", cursor: "pointer",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11.5, color: "#94A3B8", marginBottom: 4 }}>
                    <span>{h.data_inicio}</span>
                    <span>{Math.round(h.duracao_min)} min{h.participantes ? ` · ${h.participantes}` : ""}</span>
                  </div>
                  <div style={{ fontSize: 13, color: "#0F172A" }}>{h.resumo}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Ata gerada */}
      {gerandoAta && (
        <div style={{ background: "#fff", borderRadius: 18, padding: 24, marginBottom: 16, textAlign: "center", color: "#94A3B8", fontSize: 13 }}>
          Gerando a ata da reunião...
        </div>
      )}
      {ata && !gerandoAta && (
        <div style={{
          background: "#fff", borderRadius: 18, padding: 20, marginBottom: 16,
          boxShadow: "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
        }}>
          <div style={{ fontSize: 15, fontWeight: 900, color: "#8B1A1A", marginBottom: 2 }}>Ata da Reunião</div>
          <div style={{ fontSize: 11, color: "#94A3B8", marginBottom: 14 }}>
            {ata.data_inicio} · {Math.round(ata.duracao_min)} min{ata.participantes ? ` · ${ata.participantes}` : ""}
          </div>
          <div style={{ fontSize: 13.5, color: "#0F172A", background: "#FDF2F2", padding: "12px 16px", borderRadius: 10, lineHeight: 1.55, marginBottom: 16 }}>
            {ata.resumo}
          </div>

          {!ata.decisoes?.length ? (
            <div style={{ fontSize: 11.5, fontWeight: 800, color: "#64748B", textTransform: "uppercase", marginBottom: 4 }}>
              Decisões <span style={{ fontWeight: 400, textTransform: "none", color: "#94A3B8", fontStyle: "italic" }}>— nenhuma registrada</span>
            </div>
          ) : (
            <TabelaLista nome="decisoes" itens={ata.decisoes} />
          )}

          {!ata.acoes?.length ? (
            <div style={{ fontSize: 11.5, fontWeight: 800, color: "#64748B", textTransform: "uppercase", margin: "14px 0 4px" }}>
              Ações <span style={{ fontWeight: 400, textTransform: "none", color: "#94A3B8", fontStyle: "italic" }}>— nenhuma registrada</span>
            </div>
          ) : (
            <TabelaLista nome="acoes" itens={ata.acoes} />
          )}

          {ata.acoes_resolvidas_nesta_reuniao?.length > 0 && (
            <>
              <div style={{ fontSize: 11.5, fontWeight: 800, color: "#059669", textTransform: "uppercase", margin: "16px 0 6px" }}>✓ Pendências resolvidas nesta reunião</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "#047857" }}>
                {ata.acoes_resolvidas_nesta_reuniao.map((p, idx) => <li key={idx}>{p.acao}</li>)}
              </ul>
            </>
          )}
          {ata.acoes_pendentes_anteriores?.length > 0 && (
            <>
              <div style={{ fontSize: 11.5, fontWeight: 800, color: "#B45309", textTransform: "uppercase", margin: "16px 0 6px" }}>⏳ Pendências em aberto (reuniões anteriores)</div>
              <TabelaLista nome="acoes_pendentes" itens={ata.acoes_pendentes_anteriores.map(({ acao, responsavel, prazo }) => ({ acao, responsavel, prazo }))} />
            </>
          )}

          {ata.insights?.length > 0 && (
            <>
              <div style={{ fontSize: 11.5, fontWeight: 800, color: "#64748B", textTransform: "uppercase", margin: "16px 0 6px" }}>Insights</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "#334155" }}>
                {ata.insights.map((i, idx) => <li key={idx}>{i}</li>)}
              </ul>
            </>
          )}
          {ata.alertas?.length > 0 && (
            <>
              <div style={{ fontSize: 11.5, fontWeight: 800, color: "#B91C1C", textTransform: "uppercase", margin: "16px 0 6px" }}>Alertas</div>
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12.5, color: "#B91C1C" }}>
                {ata.alertas.map((a, idx) => <li key={idx}>{a}</li>)}
              </ul>
            </>
          )}

          <div style={{ display: "flex", gap: 8, marginTop: 18, alignItems: "center", flexWrap: "wrap" }}>
            <input
              value={emailAtaDestino}
              onChange={(e) => setEmailAtaDestino(e.target.value)}
              placeholder="e-mail de destino"
              style={{ flex: 1, minWidth: 180, padding: "8px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 12.5 }}
            />
            <button
              onClick={enviarAtaPdf}
              disabled={enviandoAtaPdf || !emailAtaDestino.trim()}
              style={{
                padding: "8px 16px", borderRadius: 8, border: "none", cursor: "pointer",
                background: "#0F172A", color: "#fff", fontWeight: 700, fontSize: 12,
                opacity: enviandoAtaPdf || !emailAtaDestino.trim() ? 0.5 : 1,
              }}
            >{enviandoAtaPdf ? "Enviando..." : "Gerar PDF e enviar"}</button>
            <button
              onClick={baixarAtaPdf}
              disabled={baixandoAtaPdf}
              style={{
                padding: "8px 16px", borderRadius: 8, border: "1.5px solid #0F172A", cursor: "pointer",
                background: "#fff", color: "#0F172A", fontWeight: 700, fontSize: 12,
                opacity: baixandoAtaPdf ? 0.5 : 1,
              }}
            >{baixandoAtaPdf ? "Gerando..." : "Baixar PDF"}</button>
            <button onClick={() => setAta(null)} style={{
              padding: "8px 16px", borderRadius: 8, border: "1.5px solid #E2E8F0", cursor: "pointer",
              background: "#fff", color: "#64748B", fontWeight: 700, fontSize: 12,
            }}>Fechar</button>
          </div>
          {statusAtaPdf && (
            <div style={{ fontSize: 12, marginTop: 8, fontWeight: 700, color: statusAtaPdf.ok ? "#059669" : "#DC2626" }}>
              {statusAtaPdf.ok ? "Ata enviada por e-mail." : `Erro ao enviar: ${statusAtaPdf.erro}`}
            </div>
          )}
        </div>
      )}

      {/* Conversa */}
      <div style={{ minHeight: 120, marginBottom: 14 }}>
        {conversaOrdenada.length === 0 ? (
          <div style={{
            background: "#fff", borderRadius: 18, padding: 24,
            boxShadow: "0 1px 4px rgba(0,0,0,.06), 0 0 0 1px rgba(0,0,0,.03)",
          }}>
            <div style={{ fontSize: 12.5, fontWeight: 800, color: "#94A3B8", textTransform: "uppercase", marginBottom: 12, textAlign: "center" }}>
              Experimente perguntar
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(230px, 1fr))", gap: 10 }}>
              {SUGESTOES.map((s) => (
                <button key={s.texto} onClick={() => perguntarAoJarvis(s.texto)} style={{
                  background: "#F8FAFC", border: "1px solid #EEF1F5", borderRadius: 14,
                  padding: "12px 14px", cursor: "pointer", textAlign: "left", display: "flex", gap: 10, alignItems: "flex-start",
                  transition: "background .15s",
                }}
                  onMouseEnter={(e) => e.currentTarget.style.background = "#EFF6FF"}
                  onMouseLeave={(e) => e.currentTarget.style.background = "#F8FAFC"}
                >
                  <span style={{ fontSize: 18, lineHeight: 1 }}>{s.icone}</span>
                  <span>
                    <div style={{ fontSize: 10, fontWeight: 800, color: "#94A3B8", textTransform: "uppercase" }}>{s.grupo}</div>
                    <div style={{ fontSize: 12.5, color: "#334155", fontWeight: 600, marginTop: 2 }}>"{s.texto}"</div>
                  </span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div>
            {conversaOrdenada.map((item, idx) => (
              <div key={idx}>
                <Bolha papel="user">{item.pergunta}</Bolha>
                <Bolha papel="assistant">
                  <div style={{ lineHeight: 1.55 }}>
                    <TextoDigitado texto={item.resposta_texto} ativo={idx === conversaOrdenada.length - 1} />
                  </div>
                  <PainelDados dados={item.dados} />
                  {item.dados && (
                    <div style={{ display: "flex", gap: 8, marginTop: 16, alignItems: "center", flexWrap: "wrap" }}>
                      <input
                        value={emailDestino}
                        onChange={(e) => setEmailDestino(e.target.value)}
                        placeholder="e-mail de destino"
                        style={{ flex: 1, minWidth: 180, padding: "8px 12px", borderRadius: 8, border: "1.5px solid #E2E8F0", fontSize: 12.5 }}
                      />
                      <button
                        onClick={() => enviarPdf(item, idx)}
                        disabled={enviandoPdf || !emailDestino.trim()}
                        style={{
                          padding: "8px 16px", borderRadius: 8, border: "none", cursor: "pointer",
                          background: "#0F172A", color: "#fff", fontWeight: 700, fontSize: 12,
                          opacity: enviandoPdf || !emailDestino.trim() ? 0.5 : 1,
                        }}
                      >{enviandoPdf ? "Enviando..." : "Gerar PDF e enviar"}</button>
                      <button
                        onClick={() => baixarPdf(item)}
                        disabled={baixandoPdf}
                        style={{
                          padding: "8px 16px", borderRadius: 8, border: "1.5px solid #0F172A", cursor: "pointer",
                          background: "#fff", color: "#0F172A", fontWeight: 700, fontSize: 12,
                          opacity: baixandoPdf ? 0.5 : 1,
                        }}
                      >{baixandoPdf ? "Gerando..." : "Baixar PDF"}</button>
                    </div>
                  )}
                  {statusPdf && statusPdf.idx === idx && (
                    <div style={{ fontSize: 12, marginTop: 8, fontWeight: 700, color: statusPdf.ok ? "#059669" : "#DC2626" }}>
                      {statusPdf.ok ? "PDF enviado por e-mail." : `Erro ao enviar: ${statusPdf.erro}`}
                    </div>
                  )}
                </Bolha>
              </div>
            ))}
            <div ref={fimFeedRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <div style={{
        position: "sticky", bottom: 14, display: "flex", gap: 8, alignItems: "center",
        background: "#fff", borderRadius: 999, padding: "6px 6px 6px 18px",
        boxShadow: "0 8px 28px rgba(15,23,42,.12), 0 0 0 1px rgba(0,0,0,.04)", marginBottom: 20,
      }}>
        <input
          value={textoManual}
          onChange={(e) => setTextoManual(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") enviarTexto(); }}
          placeholder='Converse com a CIA...'
          style={{ flex: 1, border: "none", outline: "none", fontSize: 13.5, padding: "10px 0", background: "transparent" }}
        />
        <button
          onClick={enviarTexto}
          disabled={!textoManual.trim()}
          style={{
            width: 40, height: 40, borderRadius: "50%", border: "none", cursor: "pointer", flexShrink: 0,
            background: textoManual.trim() ? COR : "#E2E8F0", color: "#fff", fontSize: 16,
            display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >➤</button>
      </div>

      <style>{`
        @keyframes materializar { 0%{opacity:0; transform:scale(.4); filter:blur(6px)} 60%{opacity:1} 100%{opacity:1; transform:scale(1); filter:blur(0)} }
        @keyframes piscar { 0%,100%{opacity:1} 50%{opacity:.25} }
        @keyframes respirar { 0%,100%{filter:brightness(1)} 50%{filter:brightness(1.12)} }
        @keyframes girar { 0%{transform:translate(-50%,-50%) scale(calc(1 + var(--nivel) * 0.18)) rotate(0deg)} 100%{transform:translate(-50%,-50%) scale(calc(1 + var(--nivel) * 0.18)) rotate(360deg)} }
        .jarvis-onda-barra { animation: onda 1.1s ease-in-out infinite; }
        .jarvis-onda-barra { transform-origin: center bottom; }
        @keyframes onda { 0%,100% { transform: scaleY(calc(0.5 + var(--nivel) * 1.4)); } 50% { transform: scaleY(calc(1 + var(--nivel) * 1.8)); } }
      `}</style>
    </div>
  );
}
