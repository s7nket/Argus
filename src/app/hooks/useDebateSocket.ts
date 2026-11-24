import { useState, useRef, useCallback, useEffect } from 'react';
import { wsUrl } from '../lib/api';
import type { AgentPipelineEntry, DebateMessage, HumanSide, HumanTurn, JudgeStatus } from '../types/debate';

interface UseDebateSocketParams {
  prompt: string;
  rounds: number;
  humanSide: HumanSide;
  judgeStatus: JudgeStatus;
  /** Callback to clear the PDF-exported flag when a new debate starts. */
  onDebateStart?: () => void;
}

interface UseDebateSocketReturn {
  isDebating: boolean;
  messages: DebateMessage[];
  typingAgent: string | null;
  debateComplete: boolean;
  error: string | null;
  notice: string | null;
  debateId: string | null;
  agentPipeline: AgentPipelineEntry[];
  humanTurn: HumanTurn | null;
  humanInput: string;
  setHumanInput: (v: string) => void;
  handleStartDebate: (e?: React.FormEvent) => void;
  sendHumanArgument: () => void;
}

export function useDebateSocket({
  prompt,
  rounds,
  humanSide,
  judgeStatus,
  onDebateStart,
}: UseDebateSocketParams): UseDebateSocketReturn {
  const [isDebating, setIsDebating] = useState(false);
  const [messages, setMessages] = useState<DebateMessage[]>([]);
  const [typingAgent, setTypingAgent] = useState<string | null>(null);
  const [debateComplete, setDebateComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [debateId, setDebateId] = useState<string | null>(null);
  const [agentPipeline, setAgentPipeline] = useState<AgentPipelineEntry[]>([]);
  const [humanTurn, setHumanTurn] = useState<HumanTurn | null>(null);
  const [humanInput, setHumanInput] = useState('');

  const wsRef = useRef<WebSocket | null>(null);
  const heartbeatRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const typingStartRef = useRef<number>(0);
  const debateCompleteRef = useRef(false);
  const errorOccurredRef = useRef(false);

  // Clean up the WebSocket when the component that owns this hook unmounts.
  useEffect(() => {
    return () => { wsRef.current?.close(); };
  }, []);

  const sendHumanArgument = useCallback(() => {
    if (!wsRef.current || !humanInput.trim()) return;
    wsRef.current.send(JSON.stringify({ type: 'human_argument', text: humanInput.trim() }));
    // We do NOT append locally to `messages` here.
    // The backend orchestrator will immediately broadcast the argument back
    // over the WebSocket (as `pro_argument` / `con_argument`), which will append it.
    setHumanInput('');
    setHumanTurn(null);
  }, [humanInput]);

  const handleStartDebate = useCallback((e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (isDebating || typingAgent) return;

    // Used to return here silently on an empty topic — a click or an Enter
    // press produced literally nothing, which is indistinguishable from the
    // button being broken. The button below is now disabled for the same
    // condition, but Enter-to-submit bypasses a disabled button in some
    // browsers, so this path needs its own feedback too.
    if (!prompt.trim()) {
      setError('Enter a debate topic first.');
      return;
    }

    if (judgeStatus === 'offline') {
      setError('Judge is offline. Check that the backend is running and GROQ_API_KEY is set in backend/.env.');
      return;
    }

    setIsDebating(true);
    setMessages([]);
    setTypingAgent(null);
    setDebateComplete(false);
    setNotice(null);
    setDebateId(null);
    debateCompleteRef.current = false;
    errorOccurredRef.current = false;
    setError(null);
    onDebateStart?.();

    const ws = new WebSocket(wsUrl('/ws/debate'));
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ topic: prompt, rounds, human_side: humanSide }));
      // Browsers cannot emit WS ping frames; agent generation can leave the
      // socket silent for 30-60s, long enough for a middlebox to drop the idle
      // connection (close 1006). A periodic outbound frame keeps it warm.
      heartbeatRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }));
      }, 15000);
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      switch (msg.type) {
        case 'agent_typing':
          setNotice(null);
          setTypingAgent(msg.agent);
          typingStartRef.current = Date.now();
          break;
        case 'sub_round_start':
          setMessages(prev => [...prev, { type: 'sub_round_divider', round: msg.round, sub_round: msg.sub_round, label: msg.label }]);
          break;
        case 'pro_argument': {
          const latency = Date.now() - typingStartRef.current;
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'pro', round: msg.round, sub_round: msg.sub_round, text: msg.text, latency, model: msg.model || 'unknown' }]);
          break;
        }
        case 'con_argument': {
          const latency = Date.now() - typingStartRef.current;
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'con', round: msg.round, sub_round: msg.sub_round, text: msg.text, latency, model: msg.model || 'unknown' }]);
          break;
        }
        case 'syn_argument': {
          const latency = Date.now() - typingStartRef.current;
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'syn', round: msg.round, sub_round: msg.sub_round, text: msg.text, latency, model: msg.model || 'unknown' }]);
          break;
        }
        case 'round_verdict':
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'verdict', round: msg.round, data: msg.data }]);
          break;
        case 'final_verdict':
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'final_verdict', data: msg.data }]);
          break;
        case 'debate_end':
          setNotice(null);
          debateCompleteRef.current = true;
          setDebateComplete(true);
          setTypingAgent(null);
          break;
        // The server confirms it picked the debate up before making any upstream
        // call. Without this the topic parse — which can stall on a rate limit —
        // leaves the UI blank and looks like the button did nothing.
        case 'accepted':
          setNotice('Starting debate…');
          break;
        case 'debate_start':
          if (msg.debate_id) setDebateId(msg.debate_id);
          break;
        case 'human_turn':
          setTypingAgent(null);
          setHumanTurn({ role: msg.role, round: msg.round, sub_round: msg.sub_round });
          break;
        // A call is waiting out a rate limit or a transient error. These waits
        // run to minutes, so they have to be visible.
        case 'notice':
          setNotice(msg.message);
          break;
        case 'fact_check':
          setTypingAgent(null);
          setMessages(prev => [...prev, { type: 'fact_check', round: msg.round, sub_round: msg.sub_round, data: msg.data }]);
          break;
        case 'agent_status':
          setAgentPipeline(msg.agents ?? []);
          break;
        case 'error':
          errorOccurredRef.current = true;
          setError(msg.message);
          setNotice(null);
          setTypingAgent(null);
          break;
      }
    };

    ws.onerror = () => {
      errorOccurredRef.current = true;
      setError('WebSocket connection failed. Is the backend running?');
      setTypingAgent(null);
      setIsDebating(false);
    };

    ws.onclose = () => {
      if (heartbeatRef.current) { clearInterval(heartbeatRef.current); heartbeatRef.current = null; }
      wsRef.current = null;
      setTypingAgent(null);
      setIsDebating(false);
      if (!debateCompleteRef.current && !errorOccurredRef.current) {
        setError('Connection lost. The debate was interrupted.');
      }
    };
  }, [prompt, rounds, isDebating, typingAgent, judgeStatus, humanSide, onDebateStart]);

  return {
    isDebating,
    messages,
    typingAgent,
    debateComplete,
    error,
    notice,
    debateId,
    agentPipeline,
    humanTurn,
    humanInput,
    setHumanInput,
    handleStartDebate,
    sendHumanArgument,
  };
}
