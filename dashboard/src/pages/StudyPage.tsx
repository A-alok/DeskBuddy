/**
 * Study Notes — upload exam-prep files, then get quizzed on them by the AI.
 *
 * Notes and quiz sessions are page-local state (not in the global store): they
 * are only used here, and the backend is the source of truth. Every mutation
 * goes through the store's `run()` helper so failures surface as a toast.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { IconBook, IconChat, IconPlus, IconRefresh, IconSend, IconTrash } from '@/components/icons';
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  PageHeader,
  Select,
  Spinner,
  cx,
} from '@/components/ui';
import { api } from '@/lib/api';
import { formatRelative } from '@/lib/format';
import { tap } from '@/lib/native';
import type { Note, QuizSession } from '@/lib/types';
import { useDeskmate } from '@/store/useDeskmate';

const ACCEPT = '.pdf,.docx,.xlsx,.xlsm,.txt,.md,.csv,.tsv';

export function StudyPage() {
  const navigate = useNavigate();
  const run = useDeskmate((state) => state.run);
  const pushToast = useDeskmate((state) => state.pushToast);

  const [notes, setNotes] = useState<Note[]>([]);
  const [loadingNotes, setLoadingNotes] = useState(true);
  const [uploading, setUploading] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  const [selected, setSelected] = useState<Note | null>(null);
  const [count, setCount] = useState(5);
  const [style, setStyle] = useState<'mixed' | 'mcq' | 'open'>('mixed');
  const [difficulty, setDifficulty] = useState<'mixed' | 'easy' | 'medium' | 'hard'>('mixed');

  const [quiz, setQuiz] = useState<QuizSession | null>(null);
  const [starting, setStarting] = useState(false);
  const [answer, setAnswer] = useState('');
  const [grading, setGrading] = useState(false);

  const loadNotes = () => {
    setLoadingNotes(true);
    void api.study
      .notes()
      .then(setNotes)
      .catch(() => {})
      .finally(() => setLoadingNotes(false));
  };
  useEffect(loadNotes, []);

  const onPickFile = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    const note = await run('Upload note', () => api.study.upload(file));
    setUploading(false);
    if (fileInput.current) fileInput.current.value = '';
    if (note) {
      setNotes((prev) => [note, ...prev.filter((n) => n.id !== note.id)]);
      pushToast({ kind: 'success', title: 'Note added', body: `${note.title} · ${note.char_count} chars` });
    }
  };

  const removeNote = async (note: Note) => {
    const ok = await run('Delete note', () => api.study.removeNote(note.id));
    if (ok) {
      setNotes((prev) => prev.filter((n) => n.id !== note.id));
      if (selected?.id === note.id) setSelected(null);
    }
  };

  const startQuiz = async () => {
    if (!selected) return;
    tap();
    setStarting(true);
    const session = await run('Start quiz', () =>
      api.study.startQuiz({ note_id: selected.id, count, style, difficulty }),
    );
    setStarting(false);
    if (session) {
      setQuiz(session);
      setAnswer('');
    }
  };

  const submitAnswer = async () => {
    if (!quiz || grading) return;
    const text = answer.trim();
    if (!text) return;
    tap();
    setGrading(true);
    const updated = await run('Submit answer', () => api.study.answer(quiz.id, text));
    setGrading(false);
    if (updated) {
      setQuiz(updated);
      setAnswer('');
    }
  };

  // ---- Active quiz view ---------------------------------------------------
  if (quiz) {
    const total = quiz.total;
    const idx = quiz.current_index;
    const justGraded = idx > 0 ? quiz.questions[idx - 1] : null;
    const current = !quiz.finished ? quiz.questions[idx] : null;

    return (
      <>
        <PageHeader
          title="Quiz"
          subtitle={quiz.note_title}
          actions={
            <Button size="sm" variant="ghost" onClick={() => setQuiz(null)}>
              Exit quiz
            </Button>
          }
        />
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          <div className="flex items-center justify-between text-xs text-ink-400">
            <span>
              Question {Math.min(idx + (quiz.finished ? 0 : 1), total)} of {total}
            </span>
            <span>
              Score {quiz.correct_count}/{quiz.finished ? total : idx}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-ink-800">
            <div
              className="h-full bg-accent transition-all"
              style={{ width: `${total ? (idx / total) * 100 : 0}%` }}
            />
          </div>

          {/* feedback on the answer just submitted */}
          {justGraded && justGraded.feedback && (
            <Card className={cx(justGraded.correct ? 'border-accent/30' : 'border-danger/30')}>
              <div className="flex items-start gap-2">
                <Badge tone={justGraded.correct ? 'good' : 'bad'}>
                  {justGraded.correct ? 'Correct' : 'Not quite'}
                </Badge>
                <div className="min-w-0 flex-1 text-sm">
                  <p dir="auto" className="text-ink-200">{justGraded.feedback}</p>
                  {!justGraded.correct && justGraded.answer && (
                    <p dir="auto" className="mt-1 text-xs text-ink-400">
                      Answer: {justGraded.answer}
                    </p>
                  )}
                </div>
              </div>
            </Card>
          )}

          {current ? (
            <Card>
              <p dir="auto" className="text-base font-medium text-ink-100">{current.question}</p>

              {current.options.length > 0 ? (
                <div className="mt-4 flex flex-col gap-2">
                  {current.options.map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      disabled={grading}
                      onClick={() => {
                        setAnswer(opt);
                        // auto-submit a chosen option after setting it
                        void (async () => {
                          const text = opt.trim();
                          if (!text) return;
                          tap();
                          setGrading(true);
                          const updated = await run('Submit answer', () => api.study.answer(quiz.id, text));
                          setGrading(false);
                          if (updated) {
                            setQuiz(updated);
                            setAnswer('');
                          }
                        })();
                      }}
                      className="w-full rounded-lg border border-ink-800 px-3 py-2.5 text-left text-sm text-ink-200 transition-colors hover:border-ink-600 hover:bg-ink-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
                    >
                      {opt}
                    </button>
                  ))}
                </div>
              ) : (
                <form
                  className="mt-4 flex items-end gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void submitAnswer();
                  }}
                >
                  <textarea
                    rows={2}
                    value={answer}
                    maxLength={2000}
                    placeholder="Type your answer…"
                    disabled={grading}
                    onChange={(e) => setAnswer(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        void submitAnswer();
                      }
                    }}
                    className="max-h-32 min-h-11 flex-1 resize-y rounded-lg border border-ink-700 bg-ink-900 px-3 py-2.5 text-sm text-ink-200 placeholder:text-ink-400 focus:border-accent focus:outline-none"
                  />
                  <Button type="submit" variant="primary" disabled={!answer.trim() || grading} aria-label="Submit answer">
                    {grading ? <Spinner /> : <IconSend className="size-4" />}
                  </Button>
                </form>
              )}

              {current.hint && (
                <p className="mt-3 text-xs text-ink-400">Hint: {current.hint}</p>
              )}
              {grading && current.options.length > 0 && (
                <p className="mt-3 flex items-center gap-2 text-xs text-ink-400">
                  <Spinner /> grading…
                </p>
              )}
            </Card>
          ) : (
            // finished
            <Card>
              <div className="flex flex-col items-center gap-3 py-4 text-center">
                <p className="text-3xl font-semibold text-ink-100">
                  {quiz.correct_count}/{total}
                </p>
                <p className="text-sm text-ink-300">
                  {quiz.correct_count === total
                    ? 'Perfect score — you know this cold.'
                    : quiz.correct_count >= total / 2
                      ? 'Solid. Review the misses and go again.'
                      : 'Worth another pass through the notes.'}
                </p>
                <div className="mt-2 flex gap-2">
                  <Button variant="primary" onClick={() => void startQuizAgain()}>
                    <IconRefresh className="size-4" /> New quiz
                  </Button>
                  <Button variant="outline" onClick={() => setQuiz(null)}>
                    Back to notes
                  </Button>
                </div>
              </div>
            </Card>
          )}
        </div>
      </>
    );

    async function startQuizAgain() {
      if (!quiz) return;
      setStarting(true);
      const session = await run('Start quiz', () =>
        api.study.startQuiz({ note_id: quiz.note_id, count, style, difficulty }),
      );
      setStarting(false);
      if (session) {
        setQuiz(session);
        setAnswer('');
      }
    }
  }

  // ---- Notes + setup view -------------------------------------------------
  return (
    <>
      <PageHeader
        title="Study Notes"
        subtitle="Upload your notes and let the assistant quiz you on them."
        actions={
          <Button size="sm" variant="ghost" aria-label="Reload notes" onClick={loadNotes}>
            <IconRefresh className="size-4" />
          </Button>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        {/* notes list */}
        <Card
          title="Your notes"
          subtitle="PDF, Word, Excel or text"
          actions={
            <>
              <input
                ref={fileInput}
                type="file"
                accept={ACCEPT}
                className="hidden"
                onChange={(e) => void onPickFile(e.target.files?.[0])}
              />
              <Button
                size="sm"
                variant="primary"
                disabled={uploading}
                onClick={() => fileInput.current?.click()}
              >
                {uploading ? <Spinner /> : <IconPlus className="size-4" />}
                {uploading ? 'Reading…' : 'Upload'}
              </Button>
            </>
          }
        >
          {loadingNotes && notes.length === 0 ? (
            <p className="text-xs text-ink-400">Loading…</p>
          ) : notes.length === 0 ? (
            <EmptyState
              title="No notes yet"
              body="Upload a PDF, Word doc, spreadsheet or text file of your revision material."
            />
          ) : (
            <ul className="flex flex-col divide-y divide-ink-800">
              {notes.map((note) => (
                <li key={note.id} className="flex items-center gap-3 py-2.5">
                  <IconBook className="size-4 shrink-0 text-ink-400" />
                  <button
                    type="button"
                    onClick={() => setSelected(note)}
                    className={cx(
                      'min-w-0 flex-1 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
                    )}
                  >
                    <span dir="auto" className="block truncate text-sm text-ink-200">
                      {note.title}
                    </span>
                    <span className="text-[11px] text-ink-400">
                      {note.kind} · {note.char_count.toLocaleString()} chars · {formatRelative(note.created_at)}
                    </span>
                  </button>
                  {selected?.id === note.id && <Badge tone="good">selected</Badge>}
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Ask question from ${note.title} in chat`}
                    title="Ask question in AI Chat"
                    onClick={(e) => {
                      e.stopPropagation();
                      tap();
                      navigate(`/chat?prompt=${encodeURIComponent(`Ask me a question from ${note.title}`)}`);
                    }}
                  >
                    <IconChat className="size-4 text-accent" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    aria-label={`Delete ${note.title}`}
                    onClick={() => void removeNote(note)}
                  >
                    <IconTrash className="size-4" />
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* quiz setup */}
        <Card title="Start a quiz" subtitle={selected ? selected.title : 'Pick a note first'}>
          {selected ? (
            <div className="flex flex-col gap-3">
              <Field label="Questions" htmlFor="q-count">
                <Select id="q-count" value={count} onChange={(e) => setCount(Number(e.target.value))}>
                  {[3, 5, 7, 10].map((n) => (
                    <option key={n} value={n}>
                      {n} questions
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Type" htmlFor="q-style">
                <Select id="q-style" value={style} onChange={(e) => setStyle(e.target.value as typeof style)}>
                  <option value="mixed">Mixed</option>
                  <option value="mcq">Multiple choice</option>
                  <option value="open">Short answer</option>
                </Select>
              </Field>
              <Field label="Difficulty" htmlFor="q-diff">
                <Select
                  id="q-diff"
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value as typeof difficulty)}
                >
                  <option value="mixed">Mixed</option>
                  <option value="easy">Easy</option>
                  <option value="medium">Medium</option>
                  <option value="hard">Hard</option>
                </Select>
              </Field>
              <div className="flex flex-col gap-2 pt-1">
                <Button variant="primary" disabled={starting} onClick={() => void startQuiz()}>
                  {starting ? <Spinner /> : <IconBook className="size-4" />}
                  {starting ? 'Generating…' : 'Quiz me here'}
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    tap();
                    navigate(`/chat?prompt=${encodeURIComponent(`Ask me a question from ${selected.title}`)}`);
                  }}
                >
                  <IconChat className="size-4 text-accent" /> Practice in AI Chat
                </Button>
              </div>
              <p className="text-[11px] text-ink-400">
                You can quiz here on this page, or chat conversationally with the AI assistant.
              </p>
            </div>
          ) : (
            <EmptyState title="No note selected" body="Choose a note from the list to generate a quiz." />
          )}
        </Card>
      </div>
    </>
  );
}
