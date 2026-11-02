import { useState } from 'react';
import { IconPlus, IconTrash } from '@/components/icons';
import { Badge, Button, Card, EmptyState, Field, Input, PageHeader, Toggle, cx } from '@/components/ui';
import { api } from '@/lib/api';
import { DAY_SHORT_NAMES, formatDaysOfWeek, formatRelative } from '@/lib/format';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';

export function AlarmsPage() {
  const alarms = useDeskmate((state) => state.alarms);
  const settings = useDeskmate((state) => state.settings);
  const run = useDeskmate((state) => state.run);

  const [label, setLabel] = useState('');
  const [time, setTime] = useState('07:00');
  const [days, setDays] = useState<number[]>([]);
  const [saving, setSaving] = useState(false);

  const tzOffset = Number(settings.tz_offset_minutes ?? 0);

  const toggleDay = (day: number) => {
    setDays((current) =>
      current.includes(day) ? current.filter((d) => d !== day) : [...current, day].sort((a, b) => a - b),
    );
  };

  const create = async () => {
    setSaving(true);
    tap();
    await run('Create alarm', () =>
      api.alarms.create({ label: label.trim() || 'Alarm', time_of_day: time, days_of_week: days }),
    );
    setSaving(false);
    setLabel('');
    setDays([]);
  };

  return (
    <>
      <PageHeader
        title="Alarms"
        subtitle="Wall-clock times on the device. The backend resolves the next absolute fire time."
      />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px] items-start mt-4">
        <Card 
          title={`Alarms (${alarms.length})`}
          className="shadow-[var(--shadow-neo-pressed)] bg-ink-950 border-0 rounded-3xl p-6"
        >
          {alarms.length === 0 ? (
            <EmptyState title="No alarms" body="Create one on the right, or say “set an alarm for 6:45 am”." />
          ) : (
            <ul className="flex flex-col gap-4 mt-2">
              {alarms.map((alarm) => (
                <li 
                  key={alarm.id} 
                  className={cx(
                    "flex flex-col sm:flex-row sm:items-center gap-4 p-5 rounded-2xl transition-all duration-300 border border-ink-900",
                    alarm.enabled
                      ? "bg-ink-950 shadow-[var(--shadow-neo)] hover:shadow-[var(--shadow-neo-glow)]"
                      : "bg-ink-950 shadow-[var(--shadow-neo-pressed)] opacity-60"
                  )}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-3">
                      <p
                        className={cx(
                          'tabular text-2xl font-bold transition-colors',
                          alarm.enabled ? 'text-ink-100' : 'text-ink-400 line-through',
                        )}
                      >
                        {alarm.time_of_day}
                      </p>
                      <p className="truncate text-sm text-ink-300 font-medium">{alarm.label}</p>
                    </div>
                    <p className="mt-2 flex flex-wrap items-center gap-3 text-xs text-ink-400 font-medium">
                      <span className="flex items-center gap-1.5">
                        <span className="size-1.5 rounded-full bg-ink-600 shadow-[var(--shadow-neo-sm)]"></span>
                        {formatDaysOfWeek(alarm.days_of_week)}
                      </span>
                      {alarm.enabled && alarm.next_trigger_at && (
                        <Badge tone="info">{formatRelative(alarm.next_trigger_at)}</Badge>
                      )}
                      {alarm.last_triggered_at && (
                        <span className="flex items-center gap-1.5">
                          <span className="size-1.5 rounded-full bg-ink-600 shadow-[var(--shadow-neo-sm)]"></span>
                          last rang {formatRelative(alarm.last_triggered_at)}
                        </span>
                      )}
                    </p>
                  </div>

                  <div className="flex items-center gap-3 mt-3 sm:mt-0 self-end sm:self-auto">
                    <Toggle
                      checked={alarm.enabled}
                      label={`${alarm.enabled ? 'Disable' : 'Enable'} alarm ${alarm.label} at ${alarm.time_of_day}`}
                      onChange={(next) => {
                        tap();
                        void run('Update alarm', () => api.alarms.update(alarm.id, { enabled: next }));
                      }}
                    />

                    <Button
                      size="md"
                      variant="ghost"
                      className="px-2 w-10 h-10 !rounded-xl shadow-[var(--shadow-neo-pressed)]"
                      aria-label={`Delete alarm ${alarm.label}`}
                      onClick={() => void run('Delete alarm', () => api.alarms.remove(alarm.id))}
                    >
                      <IconTrash className="size-4" />
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="New alarm" className="shadow-[var(--shadow-neo)] bg-ink-950 border-0 rounded-3xl p-6">
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              void create();
            }}
          >
            <Field label="Time" htmlFor="alarm-time" hint="24-hour clock, device local time.">
              <Input
                id="alarm-time"
                type="time"
                value={time}
                required
                onChange={(event) => setTime(event.target.value)}
              />
            </Field>

            <Field label="Label" htmlFor="alarm-label">
              <Input
                id="alarm-label"
                value={label}
                maxLength={64}
                placeholder="Wake up"
                onChange={(event) => setLabel(event.target.value)}
              />
            </Field>

            <fieldset>
              <legend className="mb-1.5 text-xs font-medium text-ink-300">Repeat</legend>
              <div className="flex gap-1">
                {DAY_SHORT_NAMES.map((name, index) => {
                  const active = days.includes(index);
                  return (
                    <button
                      key={name}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggleDay(index)}
                      className={cx(
                        'flex-1 rounded-md py-2 text-[11px] transition-colors',
                        'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent',
                        active ? 'bg-accent text-ink-950 font-semibold' : 'bg-ink-800 text-ink-300 hover:bg-ink-700',
                      )}
                    >
                      {name}
                    </button>
                  );
                })}
              </div>
              <p className="mt-1.5 text-[11px] text-ink-400">
                {days.length === 0 ? 'Once — fires at the next occurrence, then disables itself.' : formatDaysOfWeek(days)}
              </p>
            </fieldset>

            <Button type="submit" variant="primary" disabled={saving}>
              <IconPlus className="size-4" /> Add alarm
            </Button>

            <p className="text-[11px] text-ink-400">
              Device timezone offset is {tzOffset >= 0 ? '+' : ''}
              {tzOffset} minutes. Change it on the Settings page if alarms fire at the wrong hour.
            </p>
          </form>
        </Card>
      </div>
    </>
  );
}
