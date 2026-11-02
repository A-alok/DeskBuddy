import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { IconBook, IconMic, IconPause, IconSend, IconTrash } from '@/components/icons';
import { Badge, Button, Card, EmptyState, PageHeader, Spinner, Toggle, cx } from '@/components/ui';
import { api } from '@/lib/api';
import { intentLabel } from '@/lib/device';
import { formatTimeOfDay } from '@/lib/format';
import { tap } from '@/lib/native';
import type { ChatMessage, Note } from '@/lib/types';
import { useDeskmate } from '@/store/useDeskmate';

// Grouped suggestions
const SUGGESTIONS: { group: string; items: string[] }[] = [
  {
    group: 'Study Notes & Quizzing',
    items: [
      'Ask me a question from my notes',
      'Quiz me from my notes',
      'Next question',
      'Explain this topic in detail',
    ],
  },
  {
    group: 'English Commands',
    items: [
      'Turn on the LED',
      'Lights off',
      'Set a timer for 10 minutes',
      'Start pomodoro',
      'Remind me to stretch in 20 minutes',
      'Set an alarm for 6:45 am',
    ],
  },
  {
    group: 'Hindi / Hinglish',
    items: [
      'notes se sawal pucho',
      'light chalu karo',
      'light band karo',
      '5 minute ka timer lagao',
      'timer band karo',
      'subah 7 baje ka alarm lagao',
      'mausam kaisa hai',
    ],
  },
];

// Browser speech recognition support
const SpeechRecognitionClass =
  typeof window !== 'undefined'
    ? (window as unknown as { SpeechRecognition?: any }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: any }).webkitSpeechRecognition
    : null;

function cleanQuestionText(content: string): string {
  let cleaned = content.replace(/^📝\s*(?:Next\s+)?Question(?:\s+from\s+[^\n:]+)?[:\n]*/i, '');
  cleaned = cleaned.replace(/💡\s*(?:Speak|Say|Answer).*$/is, '');
  return cleaned.trim();
}

function extractOptions(content: string): string[] {
  const lines = content.split('\n');
  const options: string[] = [];
  for (const line of lines) {
    const m = line.match(/^[A-D]\)\s+(.*)/i) || line.match(/^-\s+(.*)/);
    if (m && !line.includes('Question') && !line.includes('Answer') && !line.includes('Score')) {
      options.push(m[1].trim());
    }
  }
  return options;
}

interface EvaluationResult {
  tone: 'good' | 'warn' | 'bad';
  label: string;
  feedback: string;
  suggestion: string;
}

interface NextQuestionResult {
  noteTitle: string;
  question: string;
  options: string[];
  prompt: string;
}

interface QuizSummaryResult {
  noteTitle: string;
  scoreText: string;
  totalAnswered: number;
  pct: number;
  feedbackNote: string;
}

function parseQuizSummary(content: string): QuizSummaryResult | null {
  if (!content.includes('Quiz Summary') && !content.includes('Final Score')) {
    return null;
  }
  const titleMatch = content.match(/Quiz Summary for ([^\n:]+)/i);
  const noteTitle = titleMatch ? titleMatch[1].trim() : 'Study Notes';

  const scoreMatch = content.match(/(?:Score|Final Score):\s*(\d+)\/(\d+)\s*\(([\d.]+)%\)/i);
  const scoreText = scoreMatch ? `${scoreMatch[1]}/${scoreMatch[2]}` : '';
  const pct = scoreMatch ? parseInt(scoreMatch[3], 10) : 0;
  const totalAnswered = scoreMatch ? parseInt(scoreMatch[2], 10) : 0;

  let feedbackNote = '';
  if (content.includes('🌟')) {
    feedbackNote = '🌟 Excellent revision! You have mastered these concepts.';
  } else if (content.includes('👍')) {
    feedbackNote = '👍 Good practice session! A little more review and you will ace it.';
  } else if (content.includes('completed all questions')) {
    feedbackNote = '🎉 You completed all questions from this note!';
  } else {
    feedbackNote = 'Keep studying these notes and practice again to improve!';
  }

  return { noteTitle, scoreText, totalAnswered, pct, feedbackNote };
}

function parseEvaluationAndQuestion(content: string): {
  evaluation: EvaluationResult | null;
  nextQuestion: NextQuestionResult | null;
} {
  let evalPart = '';
  let questionPart = '';

  const qIndex = content.search(/📝\s*(?:Next\s+)?Question/i);
  if (qIndex !== -1) {
    if (qIndex > 0) {
      evalPart = content.slice(0, qIndex).trim();
    }
    questionPart = content.slice(qIndex).trim();
  } else if (
    content.includes('🎯 Evaluation:') ||
    content.includes('Evaluation:') ||
    content.includes('💡 Suggestion:')
  ) {
    evalPart = content.trim();
  } else if (content.includes('📝 Question from') || content.includes('Here is a question from')) {
    questionPart = content.trim();
  }

  let evaluation: EvaluationResult | null = null;
  if (evalPart && (evalPart.includes('🎯') || evalPart.includes('Evaluation:') || evalPart.includes('💡 Suggestion:'))) {
    let tone: 'good' | 'warn' | 'bad' = 'good';
    let label = 'Correct';
    const low = evalPart.toLowerCase();
    if (low.includes('partially correct')) {
      tone = 'warn';
      label = 'Partially Correct';
    } else if (
      low.includes('needs review') ||
      low.includes('incorrect') ||
      low.includes('wrong') ||
      low.includes('not quite')
    ) {
      tone = 'bad';
      label = 'Needs Review';
    }

    let feedback = evalPart;
    let suggestion = '';
    const sugIndex = evalPart.indexOf('💡 Suggestion:');
    if (sugIndex !== -1) {
      suggestion = evalPart.slice(sugIndex + 14).trim();
      feedback = evalPart.slice(0, sugIndex).trim();
    }
    feedback = feedback.replace(/^🎯\s*Evaluation:\s*[^\n]+\n*/i, '').trim();
    feedback = feedback.replace(/^Evaluation:\s*[^\n]+\n*/i, '').trim();

    evaluation = { tone, label, feedback, suggestion };
  }

  let nextQuestion: NextQuestionResult | null = null;
  if (questionPart) {
    const titleMatch = questionPart.match(/(?:Next\s+)?Question\s+from\s+([^\n:]+)/i);
    const noteTitle = titleMatch ? titleMatch[1].trim() : 'Notes';
    const options = extractOptions(questionPart);
    const cleanedQ = cleanQuestionText(questionPart);

    let prompt = '💡 Speak your answer, or say "no" to finish.';
    if (questionPart.includes('💡 Speak') || questionPart.includes('💡 Say') || questionPart.includes('💡 Answer')) {
      const pMatch = questionPart.match(/💡\s*([^\n]+)/);
      if (pMatch) prompt = pMatch[1].trim();
    }

    nextQuestion = {
      noteTitle,
      question: cleanedQ,
      options,
      prompt,
    };
  }

  return { evaluation, nextQuestion };
}

export function ChatPage() {
  const chat = useDeskmate((state) => state.chat);
  const sending = useDeskmate((state) => state.chatSending);
  const provider = useDeskmate((state) => state.aiProvider);
  const commands = useDeskmate((state) => state.commands);
  const sendChat = useDeskmate((state) => state.sendChat);
  const loadChat = useDeskmate((state) => state.loadChat);
  const run = useDeskmate((state) => state.run);

  const [searchParams, setSearchParams] = useSearchParams();
  const [notes, setNotes] = useState<Note[]>([]);
  const [draft, setDraft] = useState('');
  const [speak, setSpeak] = useState(false);
  const [handsFree, setHandsFree] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [speechInterim, setSpeechInterim] = useState('');
  const listRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);
  const lastSpokenMsgId = useRef<string | null>(null);
  const handsFreeRef = useRef(handsFree);
  handsFreeRef.current = handsFree;
  const sendingRef = useRef(sending);
  sendingRef.current = sending;
  const isSpeakingRef = useRef(false);
  const utteranceRef = useRef<any>(null);

  useEffect(() => {
    void api.study.notes().then(setNotes).catch(() => {});
  }, []);

  useEffect(() => {
    const prompt = searchParams.get('prompt');
    if (prompt) {
      setDraft(prompt);
      setSearchParams({}, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Stick to the bottom as messages arrive.
  useEffect(() => {
    const node = listRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [chat.length, sending, speechInterim]);

  const stopListening = useCallback(() => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.abort();
      } catch {}
      recognitionRef.current = null;
    }
    setIsListening(false);
    setSpeechInterim('');
  }, []);

  const startListening = useCallback(() => {
    if (!SpeechRecognitionClass || sendingRef.current || isSpeakingRef.current) return;
    stopListening();

    try {
      const recognition = new SpeechRecognitionClass();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event: any) => {
        let interim = '';
        let final = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const item = event.results[i];
          if (item.isFinal) {
            final += item[0].transcript;
          } else {
            interim += item[0].transcript;
          }
        }

        if (interim) {
          setSpeechInterim(interim);
        }

        if (final.trim()) {
          setSpeechInterim('');
          stopListening();
          tap();
          void sendChat(final.trim(), speak);
        }
      };

      recognition.onerror = (e: any) => {
        if (e.error !== 'no-speech') {
          setIsListening(false);
        }
      };

      recognition.onend = () => {
        setIsListening(false);
        // If in hands-free mode and not speaking or sending, keep listening for answer!
        if (handsFreeRef.current && !isSpeakingRef.current && !sendingRef.current) {
          setTimeout(() => {
            if (handsFreeRef.current && !isSpeakingRef.current && !sendingRef.current) {
              startListening();
            }
          }, 350);
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch {
      setIsListening(false);
    }
  }, [speak, sendChat, stopListening]);

  // Voice playback + continuous listening loop
  useEffect(() => {
    if (chat.length === 0) return;
    const last = chat[chat.length - 1];
    if (last.id === lastSpokenMsgId.current) return;
    lastSpokenMsgId.current = last.id;

    // Only engage browser speech/listening if the user explicitly enabled laptop hands-free mode.
    // By default, the ESP32 hardware mic and speaker handle recording and speaking.
    if (last.role === 'assistant' && handsFree) {
      const isQuizEnd =
        last.content.toLowerCase().includes('quiz ended') ||
        last.content.includes('Quiz Summary') ||
        last.content.includes('completed all questions');

      if (isQuizEnd) {
        setHandsFree(false);
      }

      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();

        const cleanSpeech = last.content
          .replace(/[🎯📝💡➡️🔁📖🛑📊•]/g, '')
          .replace(/\*\*/g, '')
          .replace(/Evaluation:\s*/i, 'Evaluation: ')
          .replace(/Suggestion:\s*/i, 'Suggestion: ');

        const utterance = new SpeechSynthesisUtterance(cleanSpeech);
        utterance.rate = 1.05;
        utteranceRef.current = utterance;
        isSpeakingRef.current = true;

        let handled = false;
        const proceedToListen = () => {
          if (handled) return;
          handled = true;
          isSpeakingRef.current = false;
          utteranceRef.current = null;
          if (!isQuizEnd) {
            setTimeout(() => {
              startListening();
            }, 350);
          }
        };

        utterance.onend = proceedToListen;
        utterance.onerror = proceedToListen;

        // Safety fallback timer in case browser drops onend
        const words = cleanSpeech.split(/\s+/).filter(Boolean).length;
        const fallbackMs = Math.max(3000, (words / 2.2) * 1000 + 1200);
        setTimeout(proceedToListen, fallbackMs);

        window.speechSynthesis.speak(utterance);
      } else if (!isQuizEnd) {
        setTimeout(() => {
          startListening();
        }, 600);
      }
    }
  }, [chat, handsFree, startListening]);

  // Hands-free toggle effect
  useEffect(() => {
    if (handsFree) {
      startListening();
    } else {
      stopListening();
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    }
    return () => {
      stopListening();
      if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, [handsFree, startListening, stopListening]);

  const submit = () => {
    const message = draft.trim();
    if (!message || sending) return;
    tap();
    setDraft('');
    void sendChat(message, speak);
  };

  const isOffline = provider === 'offline-mock' || provider === 'mock';
  const displayModel =
    provider && provider.startsWith('groq')
      ? provider.replace(/^groq:/, 'groq · ')
      : provider && provider !== 'local' && provider !== 'offline-mock'
      ? provider
      : 'groq · openai/gpt-oss-20b';

  return (
    <>
      <PageHeader
        title="AI Chat"
        subtitle="Commands work in English or Hindi and run locally. Study notes quizzing continuous listening supported."
        actions={
          <div className="flex items-center gap-2">
            <Badge tone={isOffline ? 'warn' : 'good'}>
              {isOffline ? 'offline rules' : displayModel}
            </Badge>
            <Button
              size="sm"
              variant="ghost"
              aria-label="Clear conversation"
              onClick={() =>
                void run('Clear chat', async () => {
                  const result = await api.chat.clear();
                  await loadChat();
                  return result;
                })
              }
            >
              <IconTrash className="size-4" />
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <Card className="flex min-h-[60vh] flex-col lg:min-h-[70vh]">
          {/* Study Notes quick bar */}
          {notes.length > 0 && (
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-accent/20 bg-accent/5 px-3 py-2 text-xs text-ink-300">
              <div className="flex items-center gap-2">
                <IconBook className="size-4 shrink-0 text-accent" />
                <span>
                  <strong className="text-ink-100">{notes.length} Study Note{notes.length > 1 ? 's' : ''}</strong> available
                  <span className="text-ink-400"> ({notes[0].title})</span>
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    tap();
                    void sendChat('Ask me a question from my notes', speak);
                  }}
                  disabled={sending}
                  className="cursor-pointer rounded-lg bg-accent/20 px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent/30 disabled:opacity-40"
                >
                  Quiz me on notes
                </button>
                <Link to="/study" className="text-xs text-ink-400 hover:text-ink-200">
                  Manage notes →
                </Link>
              </div>
            </div>
          )}

          {/* Continuous voice listening bar */}
          {handsFree && (
            <div className="mb-3 flex items-center justify-between gap-2 rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-2 text-xs text-emerald-200">
              <div className="flex items-center gap-2">
                <span className="relative flex size-2.5">
                  <span className={cx('absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75', isListening && 'animate-ping')} />
                  <span className="relative inline-flex size-2.5 rounded-full bg-emerald-500" />
                </span>
                <span className="font-medium">
                  {isListening ? (speechInterim ? `Heard: “${speechInterim}”` : 'Listening for your answer… speak naturally') : 'Speaking response…'}
                </span>
              </div>
              <button
                type="button"
                onClick={() => setHandsFree(false)}
                className="flex items-center gap-1 rounded bg-ink-800/80 px-2 py-0.5 text-[11px] text-ink-300 hover:bg-ink-700 hover:text-ink-100"
              >
                <IconPause className="size-3" /> Stop Hands-Free
              </button>
            </div>
          )}

          {/* Messages list */}
          <div ref={listRef} className="flex-1 overflow-y-auto pr-1">
            {chat.length === 0 ? (
              <div className="grid h-full place-items-center">
                <EmptyState
                  title="Say something or start a quiz"
                  body={
                    notes.length > 0
                      ? 'Say "Quiz me on my notes" or enable Hands-Free mode to practice continuously.'
                      : 'Commands are executed for real: a timer started here starts on the device.'
                  }
                />
              </div>
            ) : (
              <ul className="flex flex-col gap-3">
                {chat.map((message, idx) => {
                  const mine = message.role === 'user';
                  const isAssistant = message.role === 'assistant';
                  const quizSummary = isAssistant ? parseQuizSummary(message.content) : null;
                  const { evaluation, nextQuestion } =
                    isAssistant && !quizSummary
                      ? parseEvaluationAndQuestion(message.content)
                      : { evaluation: null, nextQuestion: null };

                  // Look back to find previous user answer for evaluation cards
                  let userAnswer: ChatMessage | null = null;
                  if (evaluation) {
                    if (idx > 0 && chat[idx - 1]?.role === 'user') {
                      userAnswer = chat[idx - 1];
                    }
                  }

                  return (
                    <li key={message.id} className={cx('flex', mine ? 'justify-end' : 'justify-start')}>
                      <div
                        className={cx(
                          'max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm sm:max-w-[75%]',
                          mine
                            ? 'rounded-br-md bg-accent/15 text-ink-100'
                            : 'rounded-bl-md bg-ink-850 text-ink-200',
                        )}
                      >
                        {/* 1. Rich Quiz Session Summary Card */}
                        {quizSummary ? (
                          <div className="flex flex-col gap-2.5 min-w-[260px] sm:min-w-[320px]">
                            <div className="flex items-center justify-between border-b border-ink-800 pb-2">
                              <div className="flex items-center gap-1.5">
                                <span className="text-base">📊</span>
                                <span className="text-xs font-semibold text-ink-100">Quiz Session Summary</span>
                              </div>
                              <Badge tone="good">Completed</Badge>
                            </div>

                            <div>
                              <p className="text-xs text-ink-400">
                                Topic: <span className="font-medium text-ink-200">{quizSummary.noteTitle}</span>
                              </p>
                              {quizSummary.scoreText && (
                                <div className="mt-2 rounded-lg border border-ink-800 bg-ink-900/80 p-2.5">
                                  <div className="flex items-baseline justify-between text-xs mb-1.5">
                                    <span className="text-ink-400">Final Score:</span>
                                    <span className="font-bold text-accent text-sm">
                                      {quizSummary.scoreText} ({quizSummary.pct}%)
                                    </span>
                                  </div>
                                  <div className="h-2 w-full overflow-hidden rounded-full bg-ink-800">
                                    <div
                                      className={cx(
                                        'h-full rounded-full transition-all duration-500',
                                        quizSummary.pct >= 80
                                          ? 'bg-accent'
                                          : quizSummary.pct >= 50
                                          ? 'bg-amber-400'
                                          : 'bg-danger',
                                      )}
                                      style={{ width: `${Math.max(8, quizSummary.pct)}%` }}
                                    />
                                  </div>
                                </div>
                              )}
                              <p className="mt-2 text-xs text-ink-300 leading-relaxed">
                                {quizSummary.feedbackNote}
                              </p>
                            </div>

                            <div className="mt-1 flex flex-wrap gap-2 pt-2 border-t border-ink-800">
                              <button
                                type="button"
                                onClick={() => {
                                  tap();
                                  void sendChat('Quiz me on my notes', speak);
                                }}
                                disabled={sending}
                                className="rounded-md bg-accent/20 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/30 disabled:opacity-40"
                              >
                                🚀 Start Another Quiz
                              </button>
                            </div>
                          </div>
                        ) : evaluation || nextQuestion ? (
                          /* 2. Rich Evaluation + Continuous Next Question Card */
                          <div className="flex flex-col gap-2.5">
                            {/* Evaluation Part */}
                            {evaluation && (
                              <div className="flex flex-col gap-2">
                                <div className="flex items-center gap-2">
                                  <Badge tone={evaluation.tone}>{evaluation.label}</Badge>
                                  <span className="text-xs font-medium text-ink-300">Answer Evaluation</span>
                                </div>

                                {userAnswer && (
                                  <div className="rounded-lg border border-ink-800 bg-ink-900/70 p-2 text-xs">
                                    <span className="text-[10px] font-semibold text-ink-400 uppercase tracking-wider">
                                      What You Answered:
                                    </span>
                                    <p className="mt-0.5 font-medium text-ink-100">“{userAnswer.content}”</p>
                                  </div>
                                )}

                                <div className="text-sm leading-relaxed text-ink-200 whitespace-pre-wrap">
                                  {evaluation.feedback}
                                </div>

                                {evaluation.suggestion && (
                                  <div className="rounded-lg border border-accent/20 bg-accent/5 p-2 text-xs text-accent">
                                    <span className="font-semibold">💡 What to do next: </span>
                                    <span>{evaluation.suggestion}</span>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Next Question Part */}
                            {nextQuestion && (
                              <div
                                className={cx(
                                  'flex flex-col gap-2',
                                  evaluation && 'pt-2.5 border-t border-ink-800',
                                )}
                              >
                                <div className="flex items-center justify-between">
                                  <Badge tone="info">Question · {nextQuestion.noteTitle}</Badge>
                                </div>

                                <p
                                  dir="auto"
                                  className="font-medium text-ink-100 leading-relaxed break-words whitespace-pre-wrap"
                                >
                                  {nextQuestion.question}
                                </p>

                                {nextQuestion.options.length > 0 && (
                                  <div className="mt-1 flex flex-col gap-1.5">
                                    {nextQuestion.options.map((opt, optIdx) => (
                                      <button
                                        key={optIdx}
                                        type="button"
                                        onClick={() => {
                                          tap();
                                          void sendChat(opt, speak);
                                        }}
                                        disabled={sending}
                                        className="w-full rounded-lg border border-ink-750 bg-ink-900/60 px-3 py-2 text-left text-xs text-ink-200 transition-colors hover:border-accent hover:bg-accent/10 disabled:opacity-40"
                                      >
                                        <span className="font-semibold text-accent mr-2">
                                          {String.fromCharCode(65 + optIdx)})
                                        </span>
                                        {opt}
                                      </button>
                                    ))}
                                  </div>
                                )}

                                <div className="mt-1 flex items-center justify-between text-[11px] text-ink-400">
                                  <span>
                                    {handsFree
                                      ? '🎙️ Continuous mode listening… speak your answer aloud.'
                                      : nextQuestion.prompt}
                                  </span>
                                </div>

                                {/* Continuous Quiz Action Chips */}
                                <div className="mt-1 flex flex-wrap gap-1.5 pt-1.5 border-t border-ink-800">
                                  <button
                                    type="button"
                                    onClick={() => {
                                      tap();
                                      void sendChat('Next question', speak);
                                    }}
                                    disabled={sending}
                                    className="rounded-md bg-accent/20 px-2.5 py-1 text-xs font-medium text-accent hover:bg-accent/30 disabled:opacity-40"
                                  >
                                    ➡️ Next question
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      tap();
                                      void sendChat('Explain this topic in detail from my notes', speak);
                                    }}
                                    disabled={sending}
                                    className="rounded-md bg-ink-800 px-2.5 py-1 text-xs text-ink-300 hover:bg-ink-700 hover:text-ink-100 disabled:opacity-40"
                                  >
                                    📖 Explain topic
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      tap();
                                      void sendChat('Stop quiz', speak);
                                    }}
                                    disabled={sending}
                                    className="rounded-md bg-ink-800 px-2.5 py-1 text-xs text-danger/80 hover:bg-danger/20 hover:text-danger disabled:opacity-40"
                                  >
                                    🛑 End quiz
                                  </button>
                                </div>
                              </div>
                            )}
                          </div>
                        ) : (
                          /* 3. Standard Chat Bubble */
                          <p dir="auto" className="leading-relaxed break-words whitespace-pre-wrap">
                            {message.content}
                          </p>
                        )}

                        <p className={cx('mt-1.5 text-[10px]', mine ? 'text-accent/70' : 'text-ink-400')}>
                          {message.role === 'assistant' ? 'DeskMate' : 'You'} ·{' '}
                          {formatTimeOfDay(message.created_at)}
                        </p>
                      </div>
                    </li>
                  );
                })}

                {sending && (
                  <li className="flex justify-start">
                    <div className="flex items-center gap-2 rounded-2xl rounded-bl-md bg-ink-850 px-3.5 py-2.5">
                      <Spinner />
                      <span className="text-xs text-ink-400">thinking…</span>
                    </div>
                  </li>
                )}
              </ul>
            )}
          </div>

          {/* Chat input form */}
          <form
            className="mt-4 border-t border-ink-800 pt-3"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <div className="flex items-end gap-2">
              <label htmlFor="chat-input" className="sr-only">
                Message
              </label>
              <textarea
                id="chat-input"
                rows={1}
                value={draft}
                maxLength={2000}
                placeholder={
                  isListening
                    ? 'Listening… say your answer or "Next question"'
                    : 'Type answer, or say "Ask me a question from my notes"…'
                }
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' && !event.shiftKey) {
                    event.preventDefault();
                    submit();
                  }
                }}
                className="max-h-32 min-h-10 flex-1 resize-y rounded-lg border border-ink-700 bg-ink-900 px-3 py-2.5 text-sm text-ink-200 placeholder:text-ink-400 focus:border-accent focus:outline-none"
              />
              <Button type="submit" variant="primary" disabled={!draft.trim() || sending} aria-label="Send message">
                <IconSend className="size-4" />
              </Button>
            </div>

            <div className="mt-2.5 flex flex-wrap items-center justify-between gap-3 text-[11px] text-ink-400">
              <div className="flex items-center gap-4">
                {SpeechRecognitionClass && (
                  <label className="flex items-center gap-2 cursor-pointer select-none">
                    <Toggle checked={handsFree} onChange={setHandsFree} label="Laptop microphone fallback mode" />
                    <span className={cx('flex items-center gap-1 font-medium', handsFree ? 'text-emerald-400' : 'text-ink-400')}>
                      <IconMic className="size-3.5" /> Laptop Mic (Fallback)
                    </span>
                  </label>
                )}

                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <Toggle checked={speak} onChange={setSpeak} label="Speak reply on device speaker" />
                  <span className="flex items-center gap-1 font-medium text-ink-200">
                    🔊 Hardware DeskBuddy Speaker & Mic
                  </span>
                </label>
              </div>

              <span>Enter to send · Shift+Enter for newline</span>
            </div>
          </form>
        </Card>

        {/* Right sidebar */}
        <div className="flex flex-col gap-4">
          <Card title="Try these" subtitle="All handled locally · English or Hindi">
            <div className="flex flex-col gap-3">
              {SUGGESTIONS.map(({ group, items }) => (
                <section key={group} aria-label={group}>
                  <p className="mb-1.5 text-[11px] font-medium tracking-wide text-ink-400 uppercase">{group}</p>
                  <ul className="flex flex-col gap-2">
                    {items.map((suggestion) => (
                      <li key={suggestion}>
                        <button
                          type="button"
                          onClick={() => {
                            tap();
                            void sendChat(suggestion, speak);
                          }}
                          disabled={sending}
                          className="w-full rounded-lg border border-ink-800 px-3 py-2 text-left text-xs text-ink-300 transition-colors hover:border-ink-600 hover:text-ink-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
                        >
                          {suggestion}
                        </button>
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          </Card>

          <Card title="Command log" subtitle="Voice, touch, dashboard">
            {commands.length === 0 ? (
              <EmptyState title="Nothing logged yet" />
            ) : (
              <ul className="flex max-h-72 flex-col gap-2.5 overflow-y-auto">
                {commands.slice(0, 12).map((command) => (
                  <li key={command.id} className="text-xs">
                    <div className="flex items-start justify-between gap-2">
                      <p dir="auto" className="min-w-0 flex-1 leading-relaxed text-ink-200">
                        “{command.transcript}”
                      </p>
                      <Badge tone={command.handled_locally ? 'good' : 'info'}>
                        {intentLabel(command.intent)}
                      </Badge>
                    </div>
                    {command.response_text && (
                      <p dir="auto" className="mt-0.5 text-ink-400">
                        {command.response_text}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </>
  );
}
