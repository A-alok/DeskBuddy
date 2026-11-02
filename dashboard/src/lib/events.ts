/** Mirrors backend/app/events.py. Keep the two in step. */

export const EV = {
  hello: 'hello',
  deviceOnline: 'device.online',
  deviceOffline: 'device.offline',
  deviceStatus: 'device.status',
  ping: 'ping',
  pong: 'pong',

  timerStarted: 'timer.started',
  timerPaused: 'timer.paused',
  timerResumed: 'timer.resumed',
  timerCancelled: 'timer.cancelled',
  timerFinished: 'timer.finished',

  stopwatchStarted: 'stopwatch.started',
  stopwatchStopped: 'stopwatch.stopped',
  stopwatchLapped: 'stopwatch.lapped',
  stopwatchReset: 'stopwatch.reset',

  alarmCreated: 'alarm.created',
  alarmUpdated: 'alarm.updated',
  alarmDeleted: 'alarm.deleted',
  alarmTriggered: 'alarm.triggered',

  pomodoroStarted: 'pomodoro.started',
  pomodoroPaused: 'pomodoro.paused',
  pomodoroResumed: 'pomodoro.resumed',
  pomodoroStopped: 'pomodoro.stopped',
  pomodoroPhaseChanged: 'pomodoro.phase_changed',
  pomodoroSkipped: 'pomodoro.skipped',

  taskCreated: 'task.created',
  taskUpdated: 'task.updated',
  taskDeleted: 'task.deleted',

  reminderCreated: 'reminder.created',
  reminderUpdated: 'reminder.updated',
  reminderDeleted: 'reminder.deleted',
  reminderDue: 'reminder.due',

  relaySet: 'relay.set',
  screenChanged: 'screen.changed',
  touch: 'touch',

  voiceCommand: 'voice.command',
  voiceListening: 'voice.listening',
  chatMessage: 'chat.message',

  settingsUpdated: 'settings.updated',
  weatherUpdated: 'weather.updated',
  error: 'error',
  ack: 'ack',
} as const;

export type EventName = (typeof EV)[keyof typeof EV];
