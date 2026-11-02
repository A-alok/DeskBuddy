/**
 * TypeScript mirrors of the backend's pydantic schemas (backend/app/schemas.py).
 *
 * Timestamps arrive as ISO-8601 UTC strings. Anything countdown-shaped carries
 * an absolute `ends_at`; `remaining_seconds` is only a snapshot for first paint.
 */

export type RunState = 'idle' | 'running' | 'paused' | 'finished' | 'cancelled';
export type PomodoroPhase = 'idle' | 'focus' | 'short_break' | 'long_break';
export type Priority = 'low' | 'normal' | 'high';
export type CommandSource = 'voice' | 'touch' | 'dashboard' | 'mobile' | 'device' | 'system';
export type SessionKind = 'pomodoro_focus' | 'pomodoro_break' | 'timer' | 'manual';

export interface WifiConfig {
  device_id: string;
  ssid: string;
  password_set: boolean;
  configured_at: string | null;
}

export interface Device {
  id: string;
  name: string;
  firmware_version: string | null;
  online: boolean;
  websocket_connected: boolean;
  last_seen_at: string | null;
  seconds_since_seen: number | null;
  wifi_connected: boolean;
  wifi_ssid: string | null;
  wifi_rssi: number | null;
  ip_address: string | null;
  battery_percent: number | null;
  battery_voltage: number | null;
  charging: boolean;
  free_heap_bytes: number | null;
  uptime_seconds: number | null;
  relay_on: boolean;
  current_screen: string;
}

export interface Timer {
  id: string;
  device_id: string;
  label: string;
  duration_seconds: number;
  state: RunState;
  ends_at: string | null;
  remaining_seconds: number;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Stopwatch {
  device_id: string;
  state: RunState;
  started_at: string | null;
  accumulated_ms: number;
  elapsed_ms: number;
  laps: number[];
  updated_at: string;
}

export interface Alarm {
  id: string;
  device_id: string;
  label: string;
  time_of_day: string;
  days_of_week: number[];
  enabled: boolean;
  sound: string;
  next_trigger_at: string | null;
  seconds_until_trigger: number | null;
  last_triggered_at: string | null;
  created_at: string;
}

export interface Reminder {
  id: string;
  device_id: string;
  text: string;
  remind_at: string;
  seconds_until: number;
  done: boolean;
  notified_at: string | null;
  source: CommandSource;
  created_at: string;
}

export interface Task {
  id: string;
  device_id: string;
  title: string;
  notes: string | null;
  priority: Priority;
  done: boolean;
  due_at: string | null;
  completed_at: string | null;
  list_type?: 'personal' | 'competitive';
  xp?: number;
  source: CommandSource;
  created_at: string;
  updated_at: string;
}

export interface Pomodoro {
  device_id: string;
  phase: PomodoroPhase;
  state: RunState;
  focus_minutes: number;
  short_break_minutes: number;
  long_break_minutes: number;
  cycles_before_long_break: number;
  completed_focus_cycles: number;
  ends_at: string | null;
  remaining_seconds: number;
  phase_total_seconds: number;
  updated_at: string;
  /** Present only on pomodoro.phase_changed / pomodoro.skipped events. */
  previous_phase?: PomodoroPhase;
}

export interface FocusSession {
  id: string;
  device_id: string;
  kind: SessionKind;
  planned_seconds: number;
  actual_seconds: number;
  completed: boolean;
  started_at: string;
  ended_at: string | null;
}

export interface VoiceCommand {
  id: string;
  device_id: string;
  transcript: string;
  intent: string | null;
  entities: Record<string, unknown>;
  response_text: string | null;
  handled_locally: boolean;
  source: CommandSource;
  latency_ms: number | null;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  device_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  source: CommandSource;
  created_at: string;
}

export interface ChatResponse {
  reply: string;
  intent: string | null;
  entities: Record<string, unknown>;
  action_taken: string | null;
  provider: string;
  messages: ChatMessage[];
}

export interface DailyPoint {
  date: string;
  focus_minutes: number;
  sessions: number;
  tasks_completed: number;
}

export interface Analytics {
  range_days: number;
  focus_minutes_today: number;
  focus_minutes_total: number;
  sessions_today: number;
  sessions_total: number;
  tasks_completed_today: number;
  tasks_open: number;
  tasks_completed_total: number;
  pomodoro_cycles_today: number;
  current_streak_days: number;
  voice_commands_total: number;
  daily: DailyPoint[];
}

export interface SettingsValues {
  [key: string]: unknown;
}

export interface Weather {
  location: string;
  temperature: number;
  feels_like: number;
  humidity: number;
  wind_speed: number;
  precipitation: number;
  is_day: boolean;
  weather_code: number;
  description: string;
  short: string;
  temp_max: number;
  temp_min: number;
  precipitation_chance: number;
  sunrise: string;
  sunset: string;
  temperature_unit: string;
  wind_unit: string;
  stale: boolean;
}

export interface Snapshot {
  server_time: string;
  device: Device;
  timer: Timer | null;
  timers: Timer[];
  stopwatch: Stopwatch;
  pomodoro: Pomodoro;
  alarms: Alarm[];
  reminders: Reminder[];
  tasks: Task[];
  recent_commands: VoiceCommand[];
  analytics: Analytics;
  settings: SettingsValues;
  weather?: Weather;
}

export interface Health {
  status: 'ok' | 'degraded' | string;
  server_time: string;
  environment: string;
  auth_required: boolean;
  /** MongoDB Atlas. `detail` carries the reason when status is 'down'. */
  database: {
    status: 'ok' | 'down' | string;
    database?: string;
    server_version?: string;
    detail?: string;
  };
  /** `mode` is either "groq:<model>" or "offline-mock". */
  ai: {
    provider: string;
    mode: string;
    model: string;
    key_present: boolean;
  };
  connections: { devices: number; dashboards: number };
}

/** The envelope every WebSocket frame uses, both directions. */
export interface WsEnvelope<T = unknown> {
  type: string;
  device_id: string | null;
  origin: string;
  ts: string;
  payload: T;
}


// --------------------------------------------------------------------------- //
// Study notes & quizzes
// --------------------------------------------------------------------------- //

export interface Note {
  id: string;
  device_id: string;
  title: string;
  kind: string; // pdf | docx | xlsx | text
  char_count: number;
  text?: string | null; // only present on GET /notes/{id}
  source: CommandSource;
  created_at: string;
}

export interface QuizQuestion {
  question: string;
  options: string[];
  hint: string;
  user_answer?: string | null;
  correct?: boolean | null;
  score?: number | null;
  feedback?: string | null;
  answer?: string | null; // reference answer, revealed only after grading
}

export interface QuizSession {
  id: string;
  device_id: string;
  note_id: string;
  note_title: string;
  questions: QuizQuestion[];
  current_index: number;
  finished: boolean;
  correct_count: number;
  total: number;
  created_at: string;
}

// --------------------------------------------------------------------------- //
// Competitive Learning
// --------------------------------------------------------------------------- //

export interface Badge {
  id: string;
  name: string;
  description: string;
  icon: string;
  unlocked: boolean;
  unlocked_at: string | null;
}

export interface CompetitivePillarStats {
  xp: number;
  details: Record<string, any>;
}

export interface CompetitiveSummary {
  total_xp: number;
  level: number;
  current_level_xp: number;
  next_level_xp: number;
  progress_pct: number;
  league: string; // Bronze | Silver | Gold | Platinum | Diamond
  rank: number;
  streak_days: number;
  unlocked: boolean;
  my_referral_code: string;
  competition_code: string;
  competitors: string[];
  referred_by: string | null;
  referrals_count: number;
  pomodoro: CompetitivePillarStats;
  tasks: CompetitivePillarStats;
  quizzes: CompetitivePillarStats;
  badges: Badge[];
}

export interface ReferralAccess {
  unlocked: boolean;
  my_referral_code: string;
  referred_by: string | null;
  referrals_count: number;
  message?: string;
}

export interface LeaderboardEntry {
  rank: number;
  name: string;
  avatar: string;
  league: string;
  level: number;
  total_xp: number;
  streak_days: number;
  is_user: boolean;
  status: string;
  competition_code?: string;
}

export interface CompetitiveActivity {
  id: string;
  kind: 'pomodoro' | 'task' | 'quiz';
  title: string;
  description: string;
  xp_earned: number;
  timestamp: string;
}

export interface UserAccount {
  id: string;
  username: string;
  display_name: string;
  competition_code: string;
  device_id: string;
  avatar: string;
  status: string;
  competitors: string[];
  token?: string;
  has_password?: boolean;
  created_at: string;
}

export interface CompetitorAddResult {
  ok: boolean;
  message: string;
  competitor_name: string;
  competitor_code: string;
  competitors: string[];
}

export interface CompetitionInvite {
  id: string;
  sender_user_id: string;
  sender_username: string;
  sender_name: string;
  sender_code: string;
  sender_device_id: string;
  sender_avatar: string;
  recipient_user_id: string;
  recipient_username: string;
  recipient_name: string;
  recipient_code: string;
  recipient_device_id: string;
  recipient_avatar: string;
  status: 'pending' | 'accepted' | 'declined' | 'cancelled';
  created_at: string;
  responded_at: string | null;
}

export interface InvitesList {
  incoming: CompetitionInvite[];
  outgoing: CompetitionInvite[];
}

export interface ChallengeResult {
  ok: boolean;
  message: string;
  invite: CompetitionInvite;
}

export interface InviteActionResult {
  ok: boolean;
  message: string;
  competitor_name?: string;
  competitor_code?: string;
}



