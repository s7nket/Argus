import { jsPDF } from 'jspdf';

export interface DebateExportData {
  topic: string;
  debateId?: string | null;
  messages: any[];
  finalVerdict?: any;
  stack?: {
    model?: string;
    scorer?: string;
    ftOnline?: boolean;
    docs?: number;
  };
  createdAt?: string;
}

function asText(value: unknown): string {
  if (value == null) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return value.map(asText).filter(Boolean).join(' ');
  if (typeof value === 'object') {
    return Object.values(value as Record<string, unknown>).map(asText).filter(Boolean).join(' ');
  }
  return String(value);
}

function cleanPdfText(str: unknown): string {
  const s = asText(str);
  if (!s) return '';
  return s
    .replace(/[\u2018\u2019\u0060\u00B4]/g, "'")
    .replace(/[\u201C\u201D\u00AB\u00BB]/g, '"')
    .replace(/[\u2013\u2014\u2015\u2010\u2011\u2012]/g, '-')
    .replace(/\u2026/g, '...')
    .replace(/[\u2022\u2023\u25E6\u2043\u2219\u00B7]/g, '|')
    .replace(/[\u2190-\u21FF]/g, '->')
    .replace(/[^\x20-\x7E\n\r\t]/g, (char) => {
      const code = char.charCodeAt(0);
      if (code >= 160 && code <= 255) return char;
      return ' ';
    });
}

export async function exportAndShareDebatePdf(data: DebateExportData): Promise<{ downloaded: boolean }> {
  const doc = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: 'a4',
  });

  let primaryFont = 'helvetica';
  let monoFont = 'courier';

  const pageWidth = 210;
  const pageHeight = 297;
  const marginX = 14;
  const contentWidth = pageWidth - marginX * 2;
  const bottomMargin = 16;

  let y = 14;

  // Light Mode Theme Palette (RGB tuples)
  const bgMain: [number, number, number] = [248, 250, 252];
  const cardBg: [number, number, number] = [255, 255, 255];
  const borderLine: [number, number, number] = [226, 232, 240];
  const textWhite: [number, number, number] = [15, 23, 42]; // Main dark text
  const textBody: [number, number, number] = [51, 65, 85];
  const textMuted: [number, number, number] = [100, 116, 139];
  const scoreCardBg: [number, number, number] = [241, 245, 249];
  
  // Accents
  const proEmerald: [number, number, number] = [5, 150, 105];
  const proCardBg: [number, number, number] = [236, 253, 245];
  const proCardBorder: [number, number, number] = [167, 243, 208];
  
  const conRose: [number, number, number] = [225, 29, 72];
  const conCardBg: [number, number, number] = [255, 241, 242];
  const conCardBorder: [number, number, number] = [254, 205, 211];

  const synAmber: [number, number, number] = [217, 119, 6];
  const synCardBg: [number, number, number] = [254, 243, 199];
  const synCardBorder: [number, number, number] = [253, 230, 138];

  const judgeIndigo: [number, number, number] = [79, 70, 229];
  const judgeCardBg: [number, number, number] = [238, 242, 255];
  const judgeCardBorder: [number, number, number] = [199, 210, 254];

  const drawPageBg = () => {
    doc.setFillColor(bgMain[0], bgMain[1], bgMain[2]);
    doc.rect(0, 0, pageWidth, pageHeight, 'F');
  };

  const drawHeaderSmall = () => {
    doc.setFont(monoFont, 'bold');
    doc.setFontSize(8);
    doc.setTextColor(textWhite[0], textWhite[1], textWhite[2]);
    doc.text('ARGUS', marginX, 10);

    doc.setFont(primaryFont, 'bold');
    doc.setFontSize(7.5);
    doc.setTextColor(proEmerald[0], proEmerald[1], proEmerald[2]);
    doc.text('// VERDICT PROTOCOL', marginX + 16, 10);
    
    doc.setFont(primaryFont, 'normal');
    doc.setTextColor(textMuted[0], textMuted[1], textMuted[2]);
    const topicTrunc = cleanPdfText(data.topic || 'Debate Verdict Report').slice(0, 55);
    doc.text(topicTrunc, pageWidth - marginX, 10, { align: 'right' });

    doc.setDrawColor(borderLine[0], borderLine[1], borderLine[2]);
    doc.setLineWidth(0.3);
    doc.line(marginX, 12, pageWidth - marginX, 12);
  };

  const ensureSpace = (neededHeight: number) => {
    if (y + neededHeight > pageHeight - bottomMargin) {
      doc.addPage();
      drawPageBg();
      drawHeaderSmall();
      y = 17;
    }
  };

  // 1. Initial Page Background & Header Card
  drawPageBg();

  doc.setFillColor(cardBg[0], cardBg[1], cardBg[2]);
  doc.setDrawColor(borderLine[0], borderLine[1], borderLine[2]);
  doc.setLineWidth(0.4);
  doc.roundedRect(marginX, y, contentWidth, 32, 2, 2, 'FD');

  doc.setFont(monoFont, 'bold');
  doc.setFontSize(14);
  doc.setTextColor(textWhite[0], textWhite[1], textWhite[2]);
  doc.text('ARGUS', marginX + 5, y + 7.5);

  doc.setFont(primaryFont, 'bold');
  doc.setFontSize(8);
  doc.setTextColor(proEmerald[0], proEmerald[1], proEmerald[2]);
  doc.text('AI MULTI-AGENT ARENA   |   OFFICIAL VERDICT REPORT', marginX + 31, y + 7.5);

  doc.setFont(monoFont, 'normal');
  doc.setFontSize(7.5);
  doc.setTextColor(textMuted[0], textMuted[1], textMuted[2]);
  const dateStr = data.createdAt ? new Date(data.createdAt).toLocaleString() : new Date().toLocaleString();
  const idStr = data.debateId ? `ID: ${data.debateId}` : `ID: SESSION-${Date.now().toString().slice(-6)}`;
  doc.text(cleanPdfText(`${idStr}   |   ${dateStr}`), marginX + 5, y + 13);

  const isFt = data.stack?.ftOnline || String(data.stack?.scorer || '').includes('kaggle-ft');
  doc.setFillColor(isFt ? proCardBg[0] : judgeCardBg[0], isFt ? proCardBg[1] : judgeCardBg[1], isFt ? proCardBg[2] : judgeCardBg[2]);
  doc.setDrawColor(isFt ? proCardBorder[0] : judgeCardBorder[0], isFt ? proCardBorder[1] : judgeCardBorder[1], isFt ? proCardBorder[2] : judgeCardBorder[2]);
  doc.roundedRect(marginX + 5, y + 15.5, 75, 5.5, 1, 1, 'FD');

  doc.setFont(monoFont, 'bold');
  doc.setFontSize(6.8);
  doc.setTextColor(judgeIndigo[0], judgeIndigo[1], judgeIndigo[2]);
  doc.text('JUDGE: ARGUSCORE', marginX + 7, y + 19.3);

  doc.setFont(primaryFont, 'bold');
  doc.setFontSize(9);
  doc.setTextColor(textWhite[0], textWhite[1], textWhite[2]);
  const topicLines = doc.splitTextToSize(cleanPdfText(`DEBATE TOPIC: "${data.topic || 'Untitled Debate'}"`), contentWidth - 10);
  doc.text(topicLines, marginX + 5, y + 26);

  y += 37;

  // 2. Final Verdict Hero Card
  const finalMsg = data.messages.find(m => m.type === 'final_verdict')?.data || data.finalVerdict;

  if (finalMsg && typeof finalMsg === 'object') {
    ensureSpace(55);

    const rawWinner = finalMsg.overall_winner || (typeof finalMsg.winner === 'string' ? finalMsg.winner : finalMsg.winner?.name) || 'tie';
    const winner = String(rawWinner).toLowerCase();
    const isTie = winner === 'tie' || finalMsg.is_tie;
    const proTotal = Number(finalMsg.pro_total ?? 0);
    const conTotal = Number(finalMsg.con_total ?? 0);
    const synTotal = Number(finalMsg.syn_total ?? 0);

    let winnerBorder: [number, number, number] = proEmerald;
    let winnerBg: [number, number, number] = proCardBg;
    let winnerText: [number, number, number] = proEmerald;
    let winnerTitle = 'AGENT-01 // PRO WINS';

    if (winner === 'con') {
      winnerBorder = conRose;
      winnerBg = conCardBg;
      winnerText = conRose;
      winnerTitle = 'AGENT-02 // CON WINS';
    } else if (winner === 'syn') {
      winnerBorder = synAmber;
      winnerBg = synCardBg;
      winnerText = synAmber;
      winnerTitle = 'AGENT-03 // SYN WINS';
    } else if (isTie) {
      winnerBorder = [234, 179, 8];
      winnerBg = [254, 252, 232];
      winnerText = [202, 138, 4];
      winnerTitle = 'ARENA DRAW // TIE';
    }

    doc.setFillColor(winnerBg[0], winnerBg[1], winnerBg[2]);
    doc.setDrawColor(winnerBorder[0], winnerBorder[1], winnerBorder[2]);
    doc.setLineWidth(0.6);
    doc.roundedRect(marginX, y, contentWidth, 18, 2, 2, 'FD');

    doc.setFont(monoFont, 'bold');
    doc.setFontSize(11);
    doc.setTextColor(winnerText[0], winnerText[1], winnerText[2]);
    doc.text(winnerTitle, marginX + 5, y + 7.5);

    doc.setFont(primaryFont, 'bold');
    doc.setFontSize(synTotal > 0 ? 8.5 : 10);
    doc.setTextColor(textWhite[0], textWhite[1], textWhite[2]);
    const scoreStr = synTotal > 0
      ? `PRO ${proTotal.toFixed(1)}  |  CON ${conTotal.toFixed(1)}  |  SYN ${synTotal.toFixed(1)}`
      : `PRO ${proTotal.toFixed(1)}  vs  CON ${conTotal.toFixed(1)}`;
    doc.text(scoreStr, pageWidth - marginX - 5, y + 7.5, { align: 'right' });

    doc.setFont(monoFont, 'normal');
    doc.setFontSize(7.5);
    doc.setTextColor(textMuted[0], textMuted[1], textMuted[2]);
    const numRounds = (data.messages.filter(m => m.type === 'verdict').length) || 2;
    doc.text(cleanPdfText(`Debaters: 3 Agents (PRO, CON, SYN)  |  Rounds Evaluated: ${numRounds}`), marginX + 5, y + 13.5);

    y += 22;

    const verdictNarrative = cleanPdfText(finalMsg.verdict || finalMsg.final_reasoning || '');
    if (verdictNarrative) {
      const vLines = doc.splitTextToSize(verdictNarrative, contentWidth - 10);
      const vHeight = Math.max(18, vLines.length * 4.2 + 10);
      ensureSpace(vHeight);

      doc.setFillColor(cardBg[0], cardBg[1], cardBg[2]);
      doc.setDrawColor(judgeCardBorder[0], judgeCardBorder[1], judgeCardBorder[2]);
      doc.setLineWidth(0.35);
      doc.roundedRect(marginX, y, contentWidth, vHeight, 2, 2, 'FD');

      doc.setFont(monoFont, 'bold');
      doc.setFontSize(8);
      doc.setTextColor(judgeIndigo[0], judgeIndigo[1], judgeIndigo[2]);
      doc.text('FINAL JUDGE VERDICT NARRATIVE', marginX + 5, y + 5.5);

      doc.setFont(primaryFont, 'normal');
      doc.setFontSize(8);
      doc.setTextColor(textBody[0], textBody[1], textBody[2]);
      doc.text(vLines, marginX + 5, y + 10);

      y += vHeight + 4.5;
    }

    const wAnalysis = typeof finalMsg.winner === 'object' ? finalMsg.winner : {};
    const lAnalysis = typeof finalMsg.loser === 'object' ? finalMsg.loser : {};
    const decisiveArg = cleanPdfText(wAnalysis?.decisive_argument || finalMsg.decisive_argument || '');
    const fatalWeakness = cleanPdfText(lAnalysis?.fatal_weakness || finalMsg.fatal_weakness || '');

    if (decisiveArg || fatalWeakness) {
      ensureSpace(26);
      const colW = (contentWidth - 4) / 2;

      doc.setFillColor(proCardBg[0], proCardBg[1], proCardBg[2]);
      doc.setDrawColor(proCardBorder[0], proCardBorder[1], proCardBorder[2]);
      doc.setLineWidth(0.3);
      doc.roundedRect(marginX, y, colW, 22, 1.5, 1.5, 'FD');

      doc.setFont(monoFont, 'bold');
      doc.setFontSize(7);
      doc.setTextColor(proEmerald[0], proEmerald[1], proEmerald[2]);
      doc.text('WINNING FACTOR / DECISIVE MOMENT', marginX + 4, y + 4.8);

      doc.setFont(primaryFont, 'normal');
      doc.setFontSize(7.5);
      doc.setTextColor(textBody[0], textBody[1], textBody[2]);
      const wLines = doc.splitTextToSize(decisiveArg || 'Consistent argument grounding and verified factual evidence.', colW - 8);
      doc.text(wLines.slice(0, 3), marginX + 4, y + 9.5);

      doc.setFillColor(conCardBg[0], conCardBg[1], conCardBg[2]);
      doc.setDrawColor(conCardBorder[0], conCardBorder[1], conCardBorder[2]);
      doc.roundedRect(marginX + colW + 4, y, colW, 22, 1.5, 1.5, 'FD');

      doc.setFont(monoFont, 'bold');
      doc.setFontSize(7);
      doc.setTextColor(conRose[0], conRose[1], conRose[2]);
      doc.text('OPPONENT FATAL WEAKNESS', marginX + colW + 8, y + 4.8);

      doc.setFont(primaryFont, 'normal');
      doc.setFontSize(7.5);
      doc.setTextColor(textBody[0], textBody[1], textBody[2]);
      const lLines = doc.splitTextToSize(fatalWeakness || 'Unverified assertions or lack of counterargument specificity.', colW - 8);
      doc.text(lLines.slice(0, 3), marginX + colW + 8, y + 9.5);

      y += 26;
    }
  }

  // 3. Round-by-Round Verdicts & Audit Info
  const roundVerdicts = data.messages.filter(m => m.type === 'verdict');

  if (roundVerdicts.length > 0) {
    ensureSpace(14);
    doc.setFont(monoFont, 'bold');
    doc.setFontSize(9);
    doc.setTextColor(textWhite[0], textWhite[1], textWhite[2]);
    doc.text('ROUND-BY-ROUND VERDICT & AUDIT', marginX, y);

    doc.setDrawColor(borderLine[0], borderLine[1], borderLine[2]);
    doc.setLineWidth(0.4);
    doc.line(marginX, y + 2, pageWidth - marginX, y + 2);
    y += 7;

    for (let i = 0; i < roundVerdicts.length; i++) {
      const msg = roundVerdicts[i];
      const v = msg.data || {};
      const proS = typeof v.pro_scores === 'number' ? v.pro_scores : (v.pro_scores?.total ?? 0);
      const conS = typeof v.con_scores === 'number' ? v.con_scores : (v.con_scores?.total ?? 0);
      const synS = v.syn_scores != null ? (typeof v.syn_scores === 'number' ? v.syn_scores : (v.syn_scores?.total ?? 0)) : null;
      const rWinner = String(v.round_winner || 'tie').toUpperCase();
      const reasoning = cleanPdfText(v.reasoning || '');

      const rLines = doc.splitTextToSize(reasoning, contentWidth - 10);
      const rHeight = rLines.length * 4.2 + 19;

      ensureSpace(rHeight + 5);

      doc.setFillColor(judgeCardBg[0], judgeCardBg[1], judgeCardBg[2]);
      doc.setDrawColor(judgeCardBorder[0], judgeCardBorder[1], judgeCardBorder[2]);
      doc.setLineWidth(0.4);
      doc.roundedRect(marginX, y, contentWidth, rHeight, 2, 2, 'FD');

      doc.setFont(monoFont, 'bold');
      doc.setFontSize(8);
      doc.setTextColor(judgeIndigo[0], judgeIndigo[1], judgeIndigo[2]);
      doc.text(`ROUND ${msg.round} VERDICT`, marginX + 5, y + 5.5);

      const scoreBoxW = synS != null ? 27 : 34;
      const scoreBoxH = 7;
      
      doc.setFillColor(scoreCardBg[0], scoreCardBg[1], scoreCardBg[2]);
      doc.roundedRect(marginX + 5, y + 8, scoreBoxW, scoreBoxH, 1, 1, 'F');
      doc.setFont(monoFont, 'normal');
      doc.setFontSize(6.5);
      doc.setTextColor(textMuted[0], textMuted[1], textMuted[2]);
      doc.text('PRO:', marginX + 7, y + 12.8);
      doc.setFont(primaryFont, 'bold');
      doc.setFontSize(7.5);
      doc.setTextColor(textWhite[0], textWhite[1], textWhite[2]);
      doc.text(`${Number(proS).toFixed(1)}/10`, marginX + 16, y + 13);

      doc.setFillColor(scoreCardBg[0], scoreCardBg[1], scoreCardBg[2]);
      doc.roundedRect(marginX + 5 + scoreBoxW + 3, y + 8, scoreBoxW, scoreBoxH, 1, 1, 'F');
      doc.setFont(monoFont, 'normal');
      doc.setFontSize(6.5);
      doc.setTextColor(textMuted[0], textMuted[1], textMuted[2]);
      doc.text('CON:', marginX + 5 + scoreBoxW + 5, y + 12.8);
      doc.setFont(primaryFont, 'bold');
      doc.setFontSize(7.5);
      doc.setTextColor(textWhite[0], textWhite[1], textWhite[2]);
      doc.text(`${Number(conS).toFixed(1)}/10`, marginX + 5 + scoreBoxW + 14, y + 13);

      if (synS != null) {
        doc.setFillColor(scoreCardBg[0], scoreCardBg[1], scoreCardBg[2]);
        doc.roundedRect(marginX + 5 + (scoreBoxW + 3) * 2, y + 8, scoreBoxW, scoreBoxH, 1, 1, 'F');
        doc.setFont(monoFont, 'normal');
        doc.setFontSize(6.5);
        doc.setTextColor(textMuted[0], textMuted[1], textMuted[2]);
        doc.text('SYN:', marginX + 5 + (scoreBoxW + 3) * 2 + 2, y + 12.8);
        doc.setFont(primaryFont, 'bold');
        doc.setFontSize(7.5);
        doc.setTextColor(textWhite[0], textWhite[1], textWhite[2]);
        doc.text(`${Number(synS).toFixed(1)}/10`, marginX + 5 + (scoreBoxW + 3) * 2 + 11, y + 13);
      }

      doc.setFont(monoFont, 'bold');
      doc.setFontSize(7.5);
      const winColor: [number, number, number] = rWinner === 'PRO' ? proEmerald : rWinner === 'CON' ? conRose : rWinner === 'SYN' ? synAmber : [202, 138, 4];
      doc.setTextColor(winColor[0], winColor[1], winColor[2]);
      doc.text(`WINNER: ${rWinner}`, pageWidth - marginX - 5, y + 12.8, { align: 'right' });

      doc.setFont(primaryFont, 'normal');
      doc.setFontSize(7.5);
      doc.setTextColor(textBody[0], textBody[1], textBody[2]);
      doc.text(rLines, marginX + 5, y + 18.5);

      y += rHeight + 4;

      // Render Detailed Audit Data
      const audit = v.audit || {};
      const proEvidence = audit.pro_evidence_cited || [];
      const conEvidence = audit.con_evidence_cited || [];
      const proUnsupported = audit.pro_unsupported_claims || [];
      const conUnsupported = audit.con_unsupported_claims || [];
      const fallacies = audit.fallacy_claims || [];

      const renderSection = (title: string, items: any[], color: [number, number, number]) => {
        if (!items || items.length === 0) return;
        ensureSpace(12);
        doc.setFont(primaryFont, 'bold');
        doc.setFontSize(8);
        doc.setTextColor(color[0], color[1], color[2]);
        doc.text(title, marginX + 2, y + 4);
        y += 8;
        doc.setFont(primaryFont, 'normal');
        doc.setFontSize(7.5);
        doc.setTextColor(textBody[0], textBody[1], textBody[2]);
        for (const item of items) {
          let textObj = typeof item === 'string' ? item : JSON.stringify(item);
          if (item && item.named && item.quote) {
             textObj = `Fallacy '${item.named}' by ${String(item.by).toUpperCase()}: "${item.quote}" -> Valid: ${item.valid}`;
          }
          const lines = doc.splitTextToSize(`• ${cleanPdfText(textObj)}`, contentWidth - 8);
          ensureSpace(lines.length * 4 + 2);
          doc.text(lines, marginX + 4, y);
          y += lines.length * 4;
        }
        y += 3;
      };

      renderSection(`PRO Evidence Cited:`, proEvidence, proEmerald);
      renderSection(`CON Evidence Cited:`, conEvidence, conRose);
      if (audit.syn_evidence_cited?.length > 0) {
        renderSection(`SYN Evidence Cited:`, audit.syn_evidence_cited, synAmber);
      }
      renderSection(`PRO Unsupported Claims:`, proUnsupported, proEmerald);
      renderSection(`CON Unsupported Claims:`, conUnsupported, conRose);
      renderSection(`Fallacy Accusations:`, fallacies, judgeIndigo);
      
      y += 6;
    }
  }

  // 4. Full Debate Transcript
  const transcriptMessages = data.messages.filter(m =>
    m.type === 'pro_argument' || m.type === 'con_argument' || m.type === 'syn_argument' ||
    m.type === 'pro' || m.type === 'con' || m.type === 'syn'
  );

  if (transcriptMessages.length > 0) {
    ensureSpace(20);
    doc.setFont(monoFont, 'bold');
    doc.setFontSize(10);
    doc.setTextColor(textWhite[0], textWhite[1], textWhite[2]);
    doc.text('FULL DEBATE TRANSCRIPT', marginX, y);

    doc.setDrawColor(borderLine[0], borderLine[1], borderLine[2]);
    doc.setLineWidth(0.4);
    doc.line(marginX, y + 2, pageWidth - marginX, y + 2);
    y += 8;

    for (let i = 0; i < transcriptMessages.length; i++) {
      const msg = transcriptMessages[i];
      const isPro = msg.type === 'pro_argument' || msg.type === 'pro';
      const isCon = msg.type === 'con_argument' || msg.type === 'con';
      const speaker = isPro ? 'AGENT-01 (PRO)' : isCon ? 'AGENT-02 (CON)' : 'AGENT-03 (SYN)';
      const roundStr = `ROUND ${msg.round}.${msg.sub_round || 1}`;
      const header = `${speaker} - ${roundStr}`;
      const color = isPro ? proEmerald : isCon ? conRose : synAmber;

      const text = cleanPdfText(msg.text || '');
      const lines = doc.splitTextToSize(text, contentWidth - 4);
      const textHeight = lines.length * 4;

      ensureSpace(textHeight + 15);
      
      doc.setFont(monoFont, 'bold');
      doc.setFontSize(8);
      doc.setTextColor(color[0], color[1], color[2]);
      doc.text(header, marginX, y);
      y += 5;

      doc.setFont(primaryFont, 'normal');
      doc.setFontSize(8);
      doc.setTextColor(textBody[0], textBody[1], textBody[2]);
      doc.text(lines, marginX + 2, y);
      y += textHeight + 6;
    }
  }

  // 5. Page Numbering & Footers
  const totalPages = doc.getNumberOfPages();
  for (let p = 1; p <= totalPages; p++) {
    doc.setPage(p);
    doc.setFont(monoFont, 'normal');
    doc.setFontSize(6.8);
    doc.setTextColor(textMuted[0], textMuted[1], textMuted[2]);

    doc.setDrawColor(borderLine[0], borderLine[1], borderLine[2]);
    doc.setLineWidth(0.3);
    doc.line(marginX, pageHeight - 10, pageWidth - marginX, pageHeight - 10);

    doc.text('ARGUS AI ARENA   |   VERIFIABLE MULTI-AGENT PROTOCOL', marginX, pageHeight - 6.5);
    doc.text(`PAGE ${p} OF ${totalPages}`, pageWidth - marginX, pageHeight - 6.5, { align: 'right' });
  }

  // 6. Direct Instant Download
  const cleanTitle = (data.topic || 'debate')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .slice(0, 30);
  const filename = `argus-verdict-${cleanTitle || 'session'}-${Date.now().toString().slice(-4)}.pdf`;

  try {
    doc.save(filename);
  } catch {
    const blob = doc.output('blob');
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => {
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    }, 200);
  }

  return { downloaded: true };
}
