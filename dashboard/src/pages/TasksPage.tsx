import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { IconPlus, IconSwords, IconTrash, IconTrophy } from '@/components/icons';
import { Badge, Button, Card, EmptyState, Field, Input, PageHeader, Select, Stat, cx } from '@/components/ui';
import { api } from '@/lib/api';
import { formatRelative } from '@/lib/format';
import { tap } from '@/lib/native';
import type { Priority } from '@/lib/types';
import { useDeskmate } from '@/store/useDeskmate';

type StatusFilter = 'open' | 'done' | 'all';
type ListCategory = 'personal' | 'competitive';

const PRIORITY_TONE: Record<Priority, 'bad' | 'neutral' | 'info'> = {
  high: 'bad',
  normal: 'neutral',
  low: 'info',
};

export function TasksPage() {
  const tasks = useDeskmate((state) => state.tasks);
  const run = useDeskmate((state) => state.run);

  const [activeList, setActiveList] = useState<ListCategory>('personal');
  const [filter, setFilter] = useState<StatusFilter>('open');
  const [title, setTitle] = useState('');
  const [notes, setNotes] = useState('');
  const [priority, setPriority] = useState<Priority>('normal');
  const [listType, setListType] = useState<ListCategory>('personal');
  const [xpReward, setXpReward] = useState<number>(50);

  // Group tasks by category
  const personalTasks = useMemo(
    () => tasks.filter((t) => (t.list_type || 'personal') !== 'competitive'),
    [tasks],
  );
  const competitiveTasks = useMemo(
    () => tasks.filter((t) => (t.list_type || 'personal') === 'competitive'),
    [tasks],
  );

  const currentCategoryTasks = activeList === 'personal' ? personalTasks : competitiveTasks;

  const visible = useMemo(() => {
    if (filter === 'open') return currentCategoryTasks.filter((task) => !task.done);
    if (filter === 'done') return currentCategoryTasks.filter((task) => task.done);
    return currentCategoryTasks;
  }, [currentCategoryTasks, filter]);

  // Overall statistics
  const personalOpen = personalTasks.filter((t) => !t.done).length;
  const personalDone = personalTasks.filter((t) => t.done).length;
  const compOpen = competitiveTasks.filter((t) => !t.done).length;
  const compDone = competitiveTasks.filter((t) => t.done).length;
  const compXpEarned = competitiveTasks
    .filter((t) => t.done)
    .reduce((sum, t) => sum + (t.xp || 50), 0);

  const add = () => {
    const trimmed = title.trim();
    if (!trimmed) return;
    tap();
    void run(`Create ${listType} task`, () =>
      api.tasks.create({
        title: trimmed,
        notes: notes.trim() || undefined,
        priority,
        list_type: listType,
        xp: listType === 'competitive' ? xpReward : 20,
      }),
    );
    setTitle('');
    setNotes('');
    setPriority('normal');
    // Switch to the list where the user just added the task
    setActiveList(listType);
  };

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <PageHeader
          title="Tasks & Challenges"
          subtitle="Manage your Personal To-Dos and Competitive Study Challenges with real XP rewards."
        />
        <Link to="/competitive" className="self-start sm:self-auto">
          <Button variant="outline" size="sm" className="gap-2">
            <IconTrophy className="size-4 text-amber-400" />
            <span>Competitive Hub</span>
          </Button>
        </Link>
      </div>

      {/* Top Stats Overview */}
      <div className="mb-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat label="Personal Tasks" value={`${personalOpen} Open`} sub={`${personalDone} Completed`} />
        <Stat
          label="Competitive Goals"
          value={`${compOpen} Active`}
          tone={compOpen > 0 ? 'break' : undefined}
          sub={`${compDone} Crushed`}
        />
        <Stat
          label="Challenge XP Earned"
          value={`+${compXpEarned} XP`}
          tone="accent"
          sub="Boosts your League rank"
        />
        <Stat
          label="Active Category"
          value={activeList === 'personal' ? 'Personal' : 'Competitive'}
          sub={`${visible.length} items shown`}
        />
      </div>

      {/* Primary Category Switcher */}
      <div className="flex items-center gap-2 p-1.5 rounded-2xl bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)]">
        <button
          type="button"
          onClick={() => {
            tap();
            setActiveList('personal');
          }}
          className={cx(
            'flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-sm font-semibold transition-all duration-300',
            activeList === 'personal'
              ? 'bg-ink-850 text-ink-100 shadow-[var(--shadow-neo-sm)] border border-ink-700/60'
              : 'text-ink-400 hover:text-ink-200',
          )}
        >
          <span>📋</span>
          <span>Personal Tasks</span>
          <span className="ml-1 text-xs px-2 py-0.5 rounded-full bg-ink-950 text-ink-300 border border-ink-800 font-mono">
            {personalTasks.filter((t) => !t.done).length}
          </span>
        </button>

        <button
          type="button"
          onClick={() => {
            tap();
            setActiveList('competitive');
          }}
          className={cx(
            'flex-1 flex items-center justify-center gap-2 py-2.5 px-4 rounded-xl text-sm font-semibold transition-all duration-300',
            activeList === 'competitive'
              ? 'bg-gradient-to-r from-amber-500/20 to-accent/20 text-amber-300 shadow-[var(--shadow-neo-sm)] border border-amber-500/40'
              : 'text-ink-400 hover:text-ink-200',
          )}
        >
          <IconSwords className="size-4 text-amber-400" />
          <span>Competitive Challenges</span>
          <span className="ml-1 text-xs px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono">
            {competitiveTasks.filter((t) => !t.done).length}
          </span>
        </button>
      </div>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px] items-start mt-4">
        {/* Task List Card */}
        <Card
          title={
            activeList === 'personal' ? (
              <span className="flex items-center gap-2">
                <span>📋</span> Personal To-Do List
              </span>
            ) : (
              <span className="flex items-center gap-2 text-amber-300">
                <IconSwords className="size-5 text-amber-400" />
                Competitive Study Challenges
              </span>
            )
          }
          className="shadow-[var(--shadow-neo-pressed)] bg-ink-950 border-0 rounded-3xl p-6"
          actions={
            <div
              role="tablist"
              aria-label="Filter tasks"
              className="flex gap-1 rounded-xl bg-ink-900 p-1 shadow-[var(--shadow-neo)]"
            >
              {(['open', 'done', 'all'] as StatusFilter[]).map((value) => (
                <button
                  key={value}
                  role="tab"
                  aria-selected={filter === value}
                  type="button"
                  onClick={() => setFilter(value)}
                  className={cx(
                    'rounded-lg px-3 py-1.5 text-xs capitalize transition-all duration-300 font-medium',
                    'focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent',
                    filter === value
                      ? 'bg-ink-850 text-accent shadow-[var(--shadow-neo-sm)]'
                      : 'text-ink-400 hover:text-ink-200',
                  )}
                >
                  {value}
                </button>
              ))}
            </div>
          }
        >
          {visible.length === 0 ? (
            <EmptyState
              title={
                filter === 'done'
                  ? 'Nothing completed yet'
                  : activeList === 'personal'
                  ? 'No personal tasks'
                  : 'No competitive challenges'
              }
              body={
                activeList === 'personal'
                  ? 'Add your daily personal errands and to-dos on the right.'
                  : 'Add study goals, syllabus milestones, or mock tests on the right to earn competitive XP!'
              }
            />
          ) : (
            <ul className="flex flex-col gap-4 mt-2">
              {visible.map((task) => {
                const isCompetitive = (task.list_type || 'personal') === 'competitive';
                const xp = task.xp || 50;

                return (
                  <li
                    key={task.id}
                    className={cx(
                      'flex flex-col sm:flex-row sm:items-start gap-4 p-5 rounded-2xl transition-all duration-300 border',
                      isCompetitive
                        ? 'border-amber-500/20 bg-gradient-to-r from-ink-950 to-amber-950/10'
                        : 'border-ink-900 bg-ink-950',
                      task.done
                        ? 'shadow-[var(--shadow-neo-pressed)] opacity-60'
                        : isCompetitive
                        ? 'shadow-[var(--shadow-neo)] hover:border-amber-500/40 hover:shadow-[0_0_15px_rgba(245,158,11,0.15)]'
                        : 'shadow-[var(--shadow-neo)] hover:shadow-[var(--shadow-neo-glow)]',
                    )}
                  >
                    <label className="relative flex items-center justify-center cursor-pointer sm:mt-1 group">
                      <input
                        type="checkbox"
                        checked={task.done}
                        id={`task-${task.id}`}
                        onChange={(event) => {
                          tap();
                          void run('Update task', () =>
                            api.tasks.update(task.id, { done: event.target.checked }),
                          );
                        }}
                        className="peer sr-only"
                      />
                      <div
                        className={cx(
                          'size-6 rounded-lg border transition-all duration-300 flex items-center justify-center',
                          isCompetitive ? 'group-hover:border-amber-400' : 'group-hover:border-accent',
                          task.done
                            ? isCompetitive
                              ? 'bg-amber-500 border-amber-500 shadow-[0_0_10px_rgba(245,158,11,0.4)]'
                              : 'bg-accent border-accent shadow-[var(--shadow-neo-glow)]'
                            : 'bg-ink-900 border-ink-700 shadow-[var(--shadow-neo-pressed)]',
                        )}
                      >
                        {task.done && <span className="text-ink-950 text-sm font-bold leading-none">✓</span>}
                      </div>
                    </label>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <label
                          htmlFor={`task-${task.id}`}
                          className={cx(
                            'cursor-pointer text-base font-semibold transition-colors',
                            task.done ? 'text-ink-400 line-through' : 'text-ink-100',
                          )}
                        >
                          {task.title}
                        </label>
                        {isCompetitive && (
                          <span
                            className={cx(
                              'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-bold border font-mono',
                              task.done
                                ? 'bg-ink-900 text-ink-400 border-ink-800'
                                : 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse',
                            )}
                          >
                            <IconSwords className="size-3" />
                            {task.done ? `+${xp} XP Claimed` : `+${xp} XP`}
                          </span>
                        )}
                      </div>

                      {task.notes && <p className="mt-1 text-sm text-ink-300 leading-relaxed">{task.notes}</p>}

                      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-ink-400 font-medium">
                        <Badge tone={PRIORITY_TONE[task.priority]}>{task.priority}</Badge>
                        <span className="flex items-center gap-1.5">
                          <span className="size-1.5 rounded-full bg-ink-600 shadow-[var(--shadow-neo-sm)]"></span>
                          via {task.source}
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="size-1.5 rounded-full bg-ink-600 shadow-[var(--shadow-neo-sm)]"></span>
                          {task.done ? `done ${formatRelative(task.completed_at)}` : formatRelative(task.created_at)}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 mt-3 sm:mt-0 self-end sm:self-start">
                      {!task.done && (
                        <Select
                          aria-label={`Priority for ${task.title}`}
                          value={task.priority}
                          className="h-9 w-28 shrink-0 text-xs shadow-[var(--shadow-neo-pressed)]"
                          onChange={(event) =>
                            void run('Update task', () =>
                              api.tasks.update(task.id, { priority: event.target.value as Priority }),
                            )
                          }
                        >
                          <option value="high">High</option>
                          <option value="normal">Normal</option>
                          <option value="low">Low</option>
                        </Select>
                      )}

                      <Button
                        size="md"
                        variant="ghost"
                        className="px-2 w-9 h-9 !rounded-xl"
                        aria-label={`Delete task ${task.title}`}
                        onClick={() => void run('Delete task', () => api.tasks.remove(task.id))}
                      >
                        <IconTrash className="size-4" />
                      </Button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </Card>

        {/* Create Task Card */}
        <Card title="Add New Item">
          <form
            className="flex flex-col gap-4"
            onSubmit={(event) => {
              event.preventDefault();
              add();
            }}
          >
            {/* List Type Selector */}
            <Field label="Task Category" htmlFor="task-list-type">
              <Select
                id="task-list-type"
                value={listType}
                onChange={(e) => setListType(e.target.value as ListCategory)}
              >
                <option value="personal">📋 Personal Task</option>
                <option value="competitive">⚔️ Competitive Challenge</option>
              </Select>
            </Field>

            <Field
              label={listType === 'competitive' ? 'Challenge Title' : 'Title'}
              htmlFor="task-title"
            >
              <Input
                id="task-title"
                value={title}
                maxLength={140}
                required
                placeholder={
                  listType === 'competitive'
                    ? 'e.g. Finish 30 Physics MCQs'
                    : 'e.g. Clean the desk & solder wires'
                }
                onChange={(event) => setTitle(event.target.value)}
              />
            </Field>

            <Field label="Notes" htmlFor="task-notes" hint="Optional details.">
              <Input
                id="task-notes"
                value={notes}
                maxLength={1000}
                placeholder={
                  listType === 'competitive'
                    ? 'e.g. Chapter 4: Wave Optics'
                    : 'e.g. Check polarity before powering'
                }
                onChange={(event) => setNotes(event.target.value)}
              />
            </Field>

            <Field label="Priority" htmlFor="task-priority">
              <Select
                id="task-priority"
                value={priority}
                onChange={(event) => setPriority(event.target.value as Priority)}
              >
                <option value="high">High</option>
                <option value="normal">Normal</option>
                <option value="low">Low</option>
              </Select>
            </Field>

            {listType === 'competitive' && (
              <Field
                label="XP Reward"
                htmlFor="task-xp"
                hint="Earned on completion towards Leaderboard rank."
              >
                <Select
                  id="task-xp"
                  value={xpReward}
                  onChange={(e) => setXpReward(Number(e.target.value))}
                >
                  <option value={30}>+30 XP (Quick Challenge)</option>
                  <option value={50}>+50 XP (Standard Study Goal)</option>
                  <option value={100}>+100 XP (Hard Revision / Mock)</option>
                  <option value={150}>+150 XP (Epic Milestone)</option>
                </Select>
              </Field>
            )}

            <Button
              type="submit"
              variant={listType === 'competitive' ? 'primary' : 'primary'}
              disabled={!title.trim()}
              className={listType === 'competitive' ? '!bg-amber-500 hover:!bg-amber-400 !text-ink-950 font-bold' : ''}
            >
              {listType === 'competitive' ? (
                <>
                  <IconSwords className="size-4" /> Add Challenge (+{xpReward} XP)
                </>
              ) : (
                <>
                  <IconPlus className="size-4" /> Add Task
                </>
              )}
            </Button>
          </form>
        </Card>
      </div>
    </>
  );
}
