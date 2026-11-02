import { formatDayLabel, formatMinutes } from '@/lib/format';
import type { DailyPoint } from '@/lib/types';

/**
 * Focus-minutes-per-day bars. Hand-rolled rather than pulling in a chart
 * library: it is one series, and this keeps the mobile bundle small.
 */
export function FocusBarChart({ data }: { data: DailyPoint[] }) {
  const peak = Math.max(1, ...data.map((point) => point.focus_minutes));

  return (
    <div>
      <ol className="flex h-40 items-end gap-1.5 sm:gap-2" aria-hidden>
        {data.map((point) => {
          const ratio = point.focus_minutes / peak;
          const heightPercent = point.focus_minutes === 0 ? 2 : Math.max(6, ratio * 100);
          return (
            <li key={point.date} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
              <span className="tabular text-[10px] text-ink-400">
                {point.focus_minutes > 0 ? point.focus_minutes : ''}
              </span>
              <div
                className={
                  point.focus_minutes > 0
                    ? 'w-full rounded-t bg-accent/70'
                    : 'w-full rounded-t bg-ink-800'
                }
                style={{ height: `${heightPercent}%` }}
              />
              <span className="text-[10px] text-ink-400">{formatDayLabel(point.date)}</span>
            </li>
          );
        })}
      </ol>

      {/* Screen-reader equivalent of the chart. */}
      <table className="sr-only">
        <caption>Focus minutes per day</caption>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Focus</th>
            <th scope="col">Sessions</th>
            <th scope="col">Tasks completed</th>
          </tr>
        </thead>
        <tbody>
          {data.map((point) => (
            <tr key={point.date}>
              <th scope="row">{point.date}</th>
              <td>{formatMinutes(point.focus_minutes)}</td>
              <td>{point.sessions}</td>
              <td>{point.tasks_completed}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
