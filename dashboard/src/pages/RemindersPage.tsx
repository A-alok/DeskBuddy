import { useState } from 'react';
import { IconPlus, IconTrash } from '@/components/icons';
import { Badge, Button, Card, EmptyState, Field, Input, PageHeader, cx } from '@/components/ui';
import { api } from '@/lib/api';
import { formatDateTime, formatRelative } from '@/lib/format';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';

const QUICK = [
  { label: '10 min', minutes: 10 },
  { label: '30 min', minutes: 30 },
  { label: '1 hour', minutes: 60 },
  { label: '3 hours', minutes: 180 },
];

export function RemindersPage() {
  const reminders = useDeskmate((state) => state.reminders);
  const run = useDeskmate((state) => state.run);

  const [text, setText] = useState('');
  const [mode, setMode] = useState<'in' | 'at'>('in');
  const [inMinutes, setInMinutes] = useState(30);
  const [atLocal, setAtLocal] = useState(defaultLocalDateTime());

  const pending = reminders.filter((reminder) => !reminder.done);
  const done = reminders.filter((reminder) => reminder.done);

  const create = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    tap();

    if (mode === 'in') {
      void run('Create reminder', () => api.reminders.create({ text: trimmed, in_minutes: inMinutes }));
    } else {
      // datetime-local is local wall time; convert to UTC ISO for the backend.
      const ms = Date.parse(atLocal);
      if (Number.isNaN(ms)) return;
      void run('Create reminder', () =>
        api.reminders.create({ text: trimmed, remind_at: new Date(ms).toISOString() }),
      );
    }
    setText('');
  };

  return (
    <>
      <PageHeader title="Reminders" subtitle="One-shot nudges. The backend fires them and the device speaks up." />

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="flex flex-col gap-4">
          <Card title={`Upcoming (${pending.length})`}>
            {pending.length === 0 ? (
              <EmptyState
                title="Nothing scheduled"
                body="Try “remind me to stretch in 20 minutes” by voice, or add one on the right."
              />
            ) : (
              <ul className="flex flex-col divide-y divide-ink-800">
                {pending.map((reminder) => {
                  const overdue = reminder.seconds_until <= 0;
                  return (
                    <li key={reminder.id} className="flex items-start gap-3 py-3">
                      <input
                        type="checkbox"
                        id={`reminder-${reminder.id}`}
                        checked={false}
                        aria-label={`Mark "${reminder.text}" done`}
                        onChange={() => {
                          tap();
                          void run('Update reminder', () => api.reminders.update(reminder.id, { done: true }));
                        }}
                        className="mt-0.5 size-4 shrink-0 accent-[var(--color-accent)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
                      />
                      <div className="min-w-0 flex-1">
                        <label htmlFor={`reminder-${reminder.id}`} className="block cursor-pointer text-sm text-ink-100">
                          {reminder.text}
                        </label>
                        <p className="mt-0.5 flex flex-wrap items-center gap-2 text-[11px] text-ink-400">
                          <span>{formatDateTime(reminder.remind_at)}</span>
                          <Badge tone={overdue ? 'warn' : 'info'}>
                            {overdue ? (reminder.notified_at ? 'fired' : 'due') : formatRelative(reminder.remind_at)}
                          </Badge>
                          <span>via {reminder.source}</span>
                        </p>
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        aria-label={`Delete reminder ${reminder.text}`}
                        onClick={() => void run('Delete reminder', () => api.reminders.remove(reminder.id))}
                      >
                        <IconTrash className="size-4" />
                      </Button>
                    </li>
                  );
                })}
              </ul>
            )}
          </Card>

          {done.length > 0 && (
            <Card title={`Done (${done.length})`}>
              <ul className="flex flex-col divide-y divide-ink-800">
                {done.slice(0, 12).map((reminder) => (
                  <li key={reminder.id} className="flex items-center justify-between gap-3 py-2">
                    <span className={cx('min-w-0 flex-1 truncate text-sm', 'text-ink-400 line-through')}>
                      {reminder.text}
                    </span>
                    <span className="shrink-0 text-[11px] text-ink-400">{formatDateTime(reminder.remind_at)}</span>
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Delete reminder ${reminder.text}`}
                      onClick={() => void run('Delete reminder', () => api.reminders.remove(reminder.id))}
                    >
                      <IconTrash className="size-4" />
                    </Button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <Card title="New reminder">
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              create();
            }}
          >
            <Field label="What" htmlFor="reminder-text">
              <Input
                id="reminder-text"
                value={text}
                maxLength={280}
                required
                placeholder="Check the battery voltage"
                onChange={(event) => setText(event.target.value)}
              />
            </Field>

            <div role="tablist" aria-label="When" className="flex gap-1 rounded-lg bg-ink-850 p-0.5">
              {(['in', 'at'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={mode === value}
                  onClick={() => setMode(value)}
                  className={cx(
                    'flex-1 rounded-md py-1.5 text-xs transition-colors',
                    'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent',
                    mode === value ? 'bg-ink-700 text-ink-100' : 'text-ink-400 hover:text-ink-200',
                  )}
                >
                  {value === 'in' ? 'In a while' : 'At a time'}
                </button>
              ))}
            </div>

            {mode === 'in' ? (
              <>
                <div className="grid grid-cols-4 gap-2">
                  {QUICK.map((quick) => (
                    <Button
                      key={quick.label}
                      type="button"
                      size="sm"
                      variant={inMinutes === quick.minutes ? 'primary' : 'outline'}
                      onClick={() => setInMinutes(quick.minutes)}
                    >
                      {quick.label}
                    </Button>
                  ))}
                </div>
                <Field label="Minutes from now" htmlFor="reminder-in">
                  <Input
                    id="reminder-in"
                    type="number"
                    min={1}
                    max={525600}
                    value={inMinutes}
                    onChange={(event) => {
                      const parsed = Number.parseInt(event.target.value, 10);
                      setInMinutes(Number.isNaN(parsed) ? 1 : Math.max(1, parsed));
                    }}
                  />
                </Field>
              </>
            ) : (
              <Field label="Date and time" htmlFor="reminder-at" hint="Your local time; stored as UTC.">
                <Input
                  id="reminder-at"
                  type="datetime-local"
                  value={atLocal}
                  onChange={(event) => setAtLocal(event.target.value)}
                />
              </Field>
            )}

            <Button type="submit" variant="primary" disabled={!text.trim()}>
              <IconPlus className="size-4" /> Add reminder
            </Button>
          </form>
        </Card>
      </div>
    </>
  );
}

function defaultLocalDateTime(): string {
  const now = new Date(Date.now() + 30 * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}
