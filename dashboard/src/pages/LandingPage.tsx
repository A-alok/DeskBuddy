import { useState, useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useDeskmate } from '@/store/useDeskmate';
import {
  IconArrowRight,
  IconCheck,
  IconChip,
  IconLogout,
  IconMic,
  IconShieldCheck,
  IconSparkles,
  IconSwords,
  IconTrophy,
  IconUsers,
  IconZap,
} from '@/components/icons';
import { cx } from '@/components/ui';

export function LandingPage() {
  const navigate = useNavigate();
  const currentUser = useDeskmate((state) => state.currentUser);
  const status = useDeskmate((state) => state.status);

  // Virtual DeskMate Interactive Simulator State
  const [activeScreen, setActiveScreen] = useState<'clock' | 'pomodoro' | 'voice' | 'quiz'>('clock');
  const [lampOn, setLampOn] = useState(false);
  const [micActive, setMicActive] = useState(false);
  const [simulatedTime, setSimulatedTime] = useState('14:32:05');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setSimulatedTime(now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }));
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const cycleScreen = () => {
    const screens: Array<'clock' | 'pomodoro' | 'voice' | 'quiz'> = ['clock', 'pomodoro', 'voice', 'quiz'];
    const nextIdx = (screens.indexOf(activeScreen) + 1) % screens.length;
    setActiveScreen(screens[nextIdx]);
  };

  const toggleMic = () => {
    setActiveScreen('voice');
    setMicActive(true);
    setTimeout(() => setMicActive(false), 3000);
  };

  const handleEnterDashboard = () => {
    if (currentUser) {
      navigate('/app');
    } else {
      navigate('/login', { state: { from: { pathname: '/app' } } });
    }
  };

  return (
    <div className="min-h-screen bg-ink-950 text-ink-200 selection:bg-accent/30 selection:text-accent font-sans antialiased overflow-x-hidden">
      {/* --------------------------------------------------------------------- */}
      {/* Top Navigation Bar */}
      {/* --------------------------------------------------------------------- */}
      <header className="sticky top-0 z-50 backdrop-blur-md bg-ink-950/80 border-b border-ink-900/80 px-4 sm:px-8 py-3.5 transition-all">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          {/* Logo & Brand */}
          <Link to="/" className="flex items-center gap-3 group">
            <div className="size-10 rounded-xl bg-accent/15 border border-accent/30 flex items-center justify-center text-accent shadow-[var(--shadow-neo-glow)] group-hover:scale-105 transition-transform">
              <IconChip className="size-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-lg text-ink-100 tracking-tight">AI DeskMate</span>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-accent/15 text-accent border border-accent/30">
                  ESP32-S3
                </span>
              </div>
              <p className="text-[11px] text-ink-400 font-medium">Smart Voice Assistant & Study League</p>
            </div>
          </Link>

          {/* Desktop Nav Links */}
          <nav className="hidden md:flex items-center gap-7 text-xs font-semibold text-ink-400">
            <a href="#overview" className="hover:text-ink-100 transition-colors">Overview</a>
            <a href="#hardware" className="hover:text-ink-100 transition-colors">Hardware</a>
            <a href="#voice-ai" className="hover:text-ink-100 transition-colors">Voice AI</a>
            <a href="#competitive" className="hover:text-ink-100 transition-colors">Competitive League</a>
            <a href="#study-notes" className="hover:text-ink-100 transition-colors">Study Quizzer</a>
            <a href="#architecture" className="hover:text-ink-100 transition-colors">Architecture</a>
          </nav>

          {/* Action Buttons */}
          <div className="flex items-center gap-3">
            {currentUser ? (
              <div className="flex items-center gap-2">
                <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-xl border border-ink-800 bg-ink-900/80 text-xs font-semibold text-ink-200">
                  <span>{currentUser.avatar || '⚡'}</span>
                  <span className="max-w-[100px] truncate">{currentUser.display_name}</span>
                </div>
                <Link
                  to="/logout"
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-danger/30 bg-danger/10 text-xs font-semibold text-danger hover:bg-danger/20 transition-all"
                  title="Sign Out"
                >
                  <IconLogout className="size-3.5" />
                  <span className="hidden sm:inline">Sign Out</span>
                </Link>
                <Link
                  to="/app"
                  className="flex items-center gap-2 px-4 py-2 rounded-xl bg-accent text-ink-950 font-bold text-xs shadow-[var(--shadow-neo-glow)] hover:opacity-95 active:scale-95 transition-all"
                >
                  <span>Dashboard</span>
                  <IconArrowRight className="size-4" />
                </Link>
              </div>
            ) : (
              <div className="flex items-center gap-2 sm:gap-3">
                <Link
                  to="/login"
                  className="px-3.5 py-1.5 rounded-xl border border-ink-800 hover:border-ink-700 bg-ink-900 text-xs font-semibold text-ink-200 hover:text-ink-100 transition-all"
                >
                  Sign In
                </Link>
                <button
                  type="button"
                  onClick={handleEnterDashboard}
                  className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-accent text-ink-950 font-bold text-xs shadow-[var(--shadow-neo-glow)] hover:opacity-95 active:scale-95 transition-all"
                >
                  <span>Launch App</span>
                  <IconArrowRight className="size-3.5" />
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* --------------------------------------------------------------------- */}
      {/* Hero Section */}
      {/* --------------------------------------------------------------------- */}
      <section id="overview" className="relative pt-12 pb-20 px-4 sm:px-8 max-w-7xl mx-auto">
        {/* Glow ambient background elements */}
        <div className="absolute top-10 left-1/2 -translate-x-1/2 w-[600px] h-[350px] bg-accent/10 blur-[130px] rounded-full pointer-events-none -z-10" />

        <div className="grid lg:grid-cols-12 gap-12 items-center">
          {/* Left Column: Headline and Value Props */}
          <div className="lg:col-span-7 flex flex-col gap-6 text-left">
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-accent/10 border border-accent/25 w-fit">
              <span className="animate-pulse flex h-2 w-2 rounded-full bg-accent" />
              <span className="text-xs font-semibold text-accent tracking-wide uppercase">
                Offline-First Embedded AI Companion
              </span>
            </div>

            <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black text-ink-100 tracking-tight leading-[1.12]">
              The Physical Desktop Assistant for <span className="text-accent underline decoration-accent/40 decoration-4 underline-offset-6">Unstoppable</span> Focus.
            </h1>

            <p className="text-base sm:text-lg text-ink-300 leading-relaxed max-w-2xl">
              Meet <strong>AI DeskMate</strong>: a custom ESP32-S3 powered hardware companion equipped with a high-contrast 1.3" OLED, digital voice input, edge-to-cloud reasoning via Groq LLMs, smart desk lighting relay, and a competitive study league that turns productivity into an esports ranking.
            </p>

            {/* CTA Buttons */}
            <div className="flex flex-wrap items-center gap-3.5 pt-2">
              <button
                type="button"
                onClick={handleEnterDashboard}
                className="flex items-center gap-2.5 px-6 py-3.5 rounded-2xl bg-accent text-ink-950 font-extrabold text-sm shadow-[var(--shadow-neo-glow)] hover:scale-[1.02] active:scale-95 transition-all"
              >
                <span>Launch Web Dashboard</span>
                <IconArrowRight className="size-4" />
              </button>

              <button
                type="button"
                onClick={() => navigate('/login')}
                className="flex items-center gap-2 px-5 py-3.5 rounded-2xl border border-ink-800 bg-ink-900 text-ink-200 font-bold text-sm hover:border-ink-700 hover:text-ink-100 hover:bg-ink-850 transition-all shadow-[var(--shadow-neo-sm)]"
              >
                <IconUsers className="size-4 text-accent" />
                <span>Join Student League</span>
              </button>
            </div>

            {/* Quick Feature Badges */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-4 border-t border-ink-900">
              <div className="flex items-center gap-2.5 text-xs text-ink-300">
                <span className="p-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <IconShieldCheck className="size-4" />
                </span>
                <span><strong>100% Offline</strong> Core Tools</span>
              </div>
              <div className="flex items-center gap-2.5 text-xs text-ink-300">
                <span className="p-1 rounded-lg bg-accent/10 text-accent border border-accent/20">
                  <IconMic className="size-4" />
                </span>
                <span>Groq <strong>Whisper & LLMs</strong></span>
              </div>
              <div className="flex items-center gap-2.5 text-xs text-ink-300">
                <span className="p-1 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
                  <IconTrophy className="size-4" />
                </span>
                <span><strong>Competitive</strong> Study XP</span>
              </div>
            </div>
          </div>

          {/* Right Column: Interactive Virtual DeskMate Hardware Mockup */}
          <div className="lg:col-span-5 flex flex-col items-center">
            <div className="w-full max-w-md rounded-3xl p-6 bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)] relative">
              {/* Virtual Desk Lamp Light Beam Effect */}
              {lampOn && (
                <div className="absolute -top-12 -right-8 w-44 h-44 bg-amber-400/25 blur-3xl rounded-full pointer-events-none transition-all duration-500" />
              )}

              {/* Hardware Device Shell Header */}
              <div className="flex items-center justify-between pb-4 border-b border-ink-800/80 mb-5">
                <div className="flex items-center gap-2">
                  <span className="size-2.5 rounded-full bg-emerald-500 animate-pulse" />
                  <span className="font-mono text-xs font-bold text-ink-200">ESP32-S3-N16R8</span>
                </div>
                <div className="flex items-center gap-2 text-[11px] font-mono text-ink-400">
                  <span>OLED: 128×64 I2C</span>
                  <span className="text-amber-400 font-bold">84% ⚡</span>
                </div>
              </div>

              {/* Simulated Physical 1.3" OLED Display (SH1106 mono style) */}
              <div className="rounded-2xl p-4 bg-black border-2 border-ink-700 shadow-inner font-mono text-white min-h-[160px] flex flex-col justify-between relative overflow-hidden select-none">
                {/* Screen Mode 1: Clock & Home */}
                {activeScreen === 'clock' && (
                  <div className="flex flex-col h-full justify-between py-1">
                    <div className="flex items-center justify-between text-[11px] border-b border-neutral-800 pb-1 text-neutral-400">
                      <span>WIFI ● -52dBm</span>
                      <span>BATT: 84%</span>
                    </div>
                    <div className="my-auto text-center">
                      <div className="text-3xl font-extrabold tracking-wider">{simulatedTime}</div>
                      <div className="text-[11px] text-neutral-300 mt-1 uppercase tracking-widest">
                        TUE • 03 NOV 2026
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-neutral-400 pt-1 border-t border-neutral-800">
                      <span>FOCUS: 42m</span>
                      <span className={lampOn ? 'text-amber-300 font-bold' : ''}>
                        RELAY: {lampOn ? 'ON 💡' : 'OFF'}
                      </span>
                    </div>
                  </div>
                )}

                {/* Screen Mode 2: Pomodoro */}
                {activeScreen === 'pomodoro' && (
                  <div className="flex flex-col h-full justify-between py-1">
                    <div className="flex items-center justify-between text-[11px] border-b border-neutral-800 pb-1 text-neutral-400">
                      <span>POMODORO #3</span>
                      <span className="text-emerald-400 font-bold">FOCUS</span>
                    </div>
                    <div className="my-auto text-center">
                      <div className="text-3xl font-black tracking-widest text-emerald-300">21:45</div>
                      <div className="text-[11px] text-neutral-400 mt-1">Goal: Machine Learning Rev</div>
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-neutral-400 pt-1 border-t border-neutral-800">
                      <span>CYCLE: 25m / 5m</span>
                      <span>TODAY: 3h 15m</span>
                    </div>
                  </div>
                )}

                {/* Screen Mode 3: Voice Interaction */}
                {activeScreen === 'voice' && (
                  <div className="flex flex-col h-full justify-between py-1">
                    <div className="flex items-center justify-between text-[11px] border-b border-neutral-800 pb-1 text-neutral-400">
                      <span className="text-accent font-bold animate-pulse">● LISTENING (I2S)</span>
                      <span>INMP441</span>
                    </div>
                    <div className="my-auto text-center">
                      {micActive ? (
                        <div className="flex items-center justify-center gap-1.5 py-2">
                          <span className="h-6 w-1.5 bg-accent animate-pulse rounded-full" />
                          <span className="h-10 w-1.5 bg-accent animate-pulse delay-75 rounded-full" />
                          <span className="h-4 w-1.5 bg-accent animate-pulse delay-150 rounded-full" />
                          <span className="h-8 w-1.5 bg-accent animate-pulse delay-100 rounded-full" />
                          <span className="h-5 w-1.5 bg-accent animate-pulse delay-200 rounded-full" />
                        </div>
                      ) : (
                        <p className="text-xs text-neutral-300 leading-tight">
                          "Hey DeskMate, quiz me on my Physics notes!"
                        </p>
                      )}
                      <p className="text-[10px] text-accent mt-1">Groq Whisper STT → GPT-OSS-20B</p>
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-neutral-400 pt-1 border-t border-neutral-800">
                      <span>TTS: EDGE-TTS</span>
                      <span>SPEAKER: MAX98357</span>
                    </div>
                  </div>
                )}

                {/* Screen Mode 4: Study Quiz */}
                {activeScreen === 'quiz' && (
                  <div className="flex flex-col h-full justify-between py-1">
                    <div className="flex items-center justify-between text-[10px] border-b border-neutral-800 pb-1 text-neutral-400">
                      <span className="text-amber-400 font-bold">QUIZ Q2/5</span>
                      <span>+50 XP</span>
                    </div>
                    <div className="my-auto text-center px-1">
                      <p className="text-[11px] text-neutral-200 font-medium leading-snug">
                        MT3608 boost module is set to what output voltage?
                      </p>
                      <div className="mt-1 text-[10px] text-emerald-400 font-bold">
                        ✓ [B] 5.00V (Safe for ESP32)
                      </div>
                    </div>
                    <div className="flex items-center justify-between text-[10px] text-neutral-400 pt-1 border-t border-neutral-800">
                      <span>SCORE: 100%</span>
                      <span>LEAGUE: GOLD</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Hardware Controls Simulator Toolbar */}
              <div className="mt-5 pt-4 border-t border-ink-800/80 flex flex-col gap-2.5">
                <span className="text-[11px] font-semibold text-ink-400 uppercase tracking-wider block text-center">
                  Try Virtual Hardware Controls
                </span>

                <div className="grid grid-cols-3 gap-2">
                  <button
                    type="button"
                    onClick={cycleScreen}
                    className="p-2.5 rounded-xl border border-ink-800 bg-ink-950 hover:border-accent text-center text-xs font-semibold text-ink-200 transition-all hover:shadow-[var(--shadow-neo-sm)]"
                  >
                    <span className="block text-base mb-1">👆</span>
                    <span className="text-[11px]">Tap Sensor</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setLampOn(!lampOn)}
                    className={cx(
                      'p-2.5 rounded-xl border text-center text-xs font-semibold transition-all',
                      lampOn
                        ? 'border-amber-400/50 bg-amber-500/15 text-amber-300 shadow-[var(--shadow-neo-glow)]'
                        : 'border-ink-800 bg-ink-950 text-ink-200 hover:border-amber-400/40',
                    )}
                  >
                    <span className="block text-base mb-1">💡</span>
                    <span className="text-[11px]">{lampOn ? 'Lamp ON' : 'Lamp OFF'}</span>
                  </button>

                  <button
                    type="button"
                    onClick={toggleMic}
                    className="p-2.5 rounded-xl border border-ink-800 bg-ink-950 hover:border-accent text-center text-xs font-semibold text-ink-200 transition-all hover:shadow-[var(--shadow-neo-sm)]"
                  >
                    <span className="block text-base mb-1">🎙️</span>
                    <span className="text-[11px]">Speak AI</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* Offline First & Real-Time Sync Section */}
      {/* --------------------------------------------------------------------- */}
      <section className="py-16 px-4 sm:px-8 bg-ink-900/40 border-y border-ink-900">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <h2 className="text-xs font-bold text-accent uppercase tracking-widest mb-3">Guiding Philosophy</h2>
            <h3 className="text-3xl sm:text-4xl font-extrabold text-ink-100 tracking-tight">
              Hardware Reliability That Never Relies on Wi-Fi
            </h3>
            <p className="mt-3 text-sm sm:text-base text-ink-300">
              Your desk assistant should never become an idle brick when the internet drops. AI DeskMate decouples essential productivity from cloud dependencies.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            <div className="rounded-2xl p-6 bg-ink-950 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-3">
              <div className="size-10 rounded-xl bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
                <IconShieldCheck className="size-6" />
              </div>
              <h4 className="text-lg font-bold text-ink-100">100% Offline Productivity</h4>
              <p className="text-xs text-ink-300 leading-relaxed">
                Clock, timer, stopwatch, alarms, Pomodoro cycles, capacitive touch handling, relay lamp control, and the OLED UI run natively on the ESP32-S3 microcontroller without internet.
              </p>
            </div>

            <div className="rounded-2xl p-6 bg-ink-950 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-3">
              <div className="size-10 rounded-xl bg-accent/10 border border-accent/30 flex items-center justify-center text-accent">
                <IconZap className="size-6" />
              </div>
              <h4 className="text-lg font-bold text-ink-100">Bi-directional WebSocket Sync</h4>
              <p className="text-xs text-ink-300 leading-relaxed">
                When online, the device and the web dashboard mirror each other instantly. Start a timer on the physical OLED screen, and your web browser reflects it without polling.
              </p>
            </div>

            <div className="rounded-2xl p-6 bg-ink-950 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-3">
              <div className="size-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
                <IconSparkles className="size-6" />
              </div>
              <h4 className="text-lg font-bold text-ink-100">Intelligent Cloud Layer</h4>
              <p className="text-xs text-ink-300 leading-relaxed">
                GroqCloud Whisper STT, GPT-OSS-20B conversational LLM, and Edge-TTS audio stream voice responses, schedule multi-step tasks, and evaluate your study notes on demand.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* Competitive Study League & Rivalries Section */}
      {/* --------------------------------------------------------------------- */}
      <section id="competitive" className="py-20 px-4 sm:px-8 max-w-7xl mx-auto">
        <div className="grid lg:grid-cols-12 gap-12 items-center">
          <div className="lg:col-span-6 flex flex-col gap-5">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-500/10 border border-amber-500/20 w-fit text-xs font-bold text-amber-400">
              <IconTrophy className="size-4" />
              <span>Gamified Study Productivity</span>
            </div>

            <h3 className="text-3xl sm:text-4xl font-extrabold text-ink-100 tracking-tight">
              Challenge Classmates With Your Unique Competition Code.
            </h3>

            <p className="text-sm sm:text-base text-ink-300 leading-relaxed">
              Every student account receives an independent, shareable competition code (like <code className="text-amber-300 font-mono font-bold bg-ink-900 px-2 py-0.5 rounded border border-ink-800">ALEX-4821</code>). Add friends, set study rivalries, and rise through the ranks.
            </p>

            <ul className="flex flex-col gap-3 text-xs sm:text-sm text-ink-300">
              <li className="flex items-center gap-2.5">
                <IconCheck className="size-4 text-emerald-400 shrink-0" />
                <span><strong>5 League Tiers:</strong> Bronze, Silver, Gold, Platinum, and Diamond.</span>
              </li>
              <li className="flex items-center gap-2.5">
                <IconCheck className="size-4 text-emerald-400 shrink-0" />
                <span><strong>Three XP Pillars:</strong> Earn XP from verified Pomodoro minutes, task completions, and AI quiz scores.</span>
              </li>
              <li className="flex items-center gap-2.5">
                <IconCheck className="size-4 text-emerald-400 shrink-0" />
                <span><strong>Live Streaks & Badges:</strong> Maintain daily study streaks to unlock exclusive digital achievements.</span>
              </li>
            </ul>

            <div className="pt-2">
              <button
                type="button"
                onClick={() => navigate('/login')}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-amber-400 text-ink-950 font-bold text-xs shadow-md hover:opacity-95 transition-all"
              >
                <span>Get Your Competition Code</span>
                <IconArrowRight className="size-3.5" />
              </button>
            </div>
          </div>

          <div className="lg:col-span-6">
            <div className="rounded-3xl p-6 bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)]">
              <div className="flex items-center justify-between pb-4 border-b border-ink-800">
                <div className="flex items-center gap-2">
                  <IconSwords className="size-5 text-amber-400" />
                  <span className="font-bold text-sm text-ink-100">Study League Leaderboard</span>
                </div>
                <span className="px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-300 text-xs font-bold font-mono">
                  GOLD LEAGUE
                </span>
              </div>

              {/* Sample Leaderboard Items */}
              <div className="mt-4 flex flex-col gap-2.5">
                <div className="flex items-center justify-between p-3 rounded-xl bg-accent/15 border border-accent/40 shadow-sm">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-sm text-accent">#1</span>
                    <span className="text-xl">👩‍🎓</span>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-ink-100">Sarah Jenkins</span>
                        <span className="text-[10px] font-bold bg-accent text-ink-950 px-1.5 rounded">YOU</span>
                      </div>
                      <span className="text-[10px] font-mono text-ink-400">@sarah • SARAH-9102</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-mono font-bold text-accent">3,420 XP</span>
                    <span className="text-[10px] text-ink-400 block">7d streak 🔥</span>
                  </div>
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl bg-ink-950 border border-ink-800">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-sm text-ink-400">#2</span>
                    <span className="text-xl">🧑‍💻</span>
                    <div>
                      <span className="text-xs font-bold text-ink-100">Alex Miller</span>
                      <span className="text-[10px] font-mono text-ink-400 block">@alex • ALEX-4821</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-mono font-bold text-ink-200">2,980 XP</span>
                    <span className="text-[10px] text-ink-400 block">5d streak</span>
                  </div>
                </div>

                <div className="flex items-center justify-between p-3 rounded-xl bg-ink-950 border border-ink-800">
                  <div className="flex items-center gap-3">
                    <span className="font-bold text-sm text-ink-400">#3</span>
                    <span className="text-xl">🦁</span>
                    <div>
                      <span className="text-xs font-bold text-ink-100">David Kumar</span>
                      <span className="text-[10px] font-mono text-ink-400 block">@david • DAVI-1140</span>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-xs font-mono font-bold text-ink-200">2,450 XP</span>
                    <span className="text-[10px] text-ink-400 block">3d streak</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* Study Notes & AI Quizzer Section */}
      {/* --------------------------------------------------------------------- */}
      <section id="study-notes" className="py-20 px-4 sm:px-8 bg-ink-900/30 border-y border-ink-900">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <h2 className="text-xs font-bold text-accent uppercase tracking-widest mb-3">AI Exam Preparation</h2>
            <h3 className="text-3xl sm:text-4xl font-extrabold text-ink-100 tracking-tight">
              Turn Any Lecture Notes Into an Instant AI Quizzer
            </h3>
            <p className="mt-3 text-sm sm:text-base text-ink-300">
              Upload PDF textbooks, Word docs, Excel spreadsheets, or markdown notes. Our backend extracts the text and Groq LLMs generate quizzes strictly grounded in your materials.
            </p>
          </div>

          <div className="grid md:grid-cols-4 gap-5">
            <div className="rounded-2xl p-5 bg-ink-950 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-2.5">
              <span className="text-2xl">📄</span>
              <h4 className="text-sm font-bold text-ink-100">1. Upload Files</h4>
              <p className="text-xs text-ink-400">Supports PDF, DOCX, XLSX, and raw text notes. Fast backend extraction with pypdf and python-docx.</p>
            </div>

            <div className="rounded-2xl p-5 bg-ink-950 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-2.5">
              <span className="text-2xl">🧠</span>
              <h4 className="text-sm font-bold text-ink-100">2. Grounded AI Generation</h4>
              <p className="text-xs text-ink-400">Questions are strictly synthesized from your notes — zero hallucinated questions outside your syllabus.</p>
            </div>

            <div className="rounded-2xl p-5 bg-ink-950 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-2.5">
              <span className="text-2xl">✍️</span>
              <h4 className="text-sm font-bold text-ink-100">3. Interactive Drill</h4>
              <p className="text-xs text-ink-400">Practice via multiple-choice and short-answer prompts on the dashboard or voice-prompted via DeskMate.</p>
            </div>

            <div className="rounded-2xl p-5 bg-ink-950 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-2.5">
              <span className="text-2xl">🏆</span>
              <h4 className="text-sm font-bold text-ink-100">4. Score & Earn XP</h4>
              <p className="text-xs text-ink-400">Receive in-depth explanations for mistakes and earn XP directly into your student league standings.</p>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* Hardware Engineering & Pinout Section */}
      {/* --------------------------------------------------------------------- */}
      <section id="hardware" className="py-20 px-4 sm:px-8 max-w-7xl mx-auto">
        <div className="text-center max-w-3xl mx-auto mb-14">
          <h2 className="text-xs font-bold text-accent uppercase tracking-widest mb-3">Custom Hardware Engineering</h2>
          <h3 className="text-3xl sm:text-4xl font-extrabold text-ink-100 tracking-tight">
            Built On Tested, Validated Embedded Electronics
          </h3>
          <p className="mt-3 text-sm sm:text-base text-ink-300">
            A cohesive hardware platform pairing high-performance audio, I2C visuals, capacitive touch, and safe power regulation.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {/* Card 1 */}
          <div className="p-5 rounded-2xl bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-accent bg-accent/15 px-2 py-0.5 rounded">MCU</span>
              <span className="text-xs text-ink-400 font-mono">USB 5V / 3.3V</span>
            </div>
            <h4 className="font-bold text-base text-ink-100">ESP32-S3-N16R8</h4>
            <p className="text-xs text-ink-300 leading-relaxed">
              Dual-core Xtensa LX7 up to 240MHz with 16MB Flash and 8MB PSRAM. Drives real-time audio I2S pipelines, Wi-Fi 4, and device state machine.
            </p>
          </div>

          {/* Card 2 */}
          <div className="p-5 rounded-2xl bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-emerald-400 bg-emerald-500/15 px-2 py-0.5 rounded">DISPLAY</span>
              <span className="text-xs text-ink-400 font-mono">GPIO 8 (SDA), 9 (SCL)</span>
            </div>
            <h4 className="font-bold text-base text-ink-100">1.3" SH1106 OLED Display</h4>
            <p className="text-xs text-ink-300 leading-relaxed">
              128×64 monochrome high-contrast panel at I2C address 0x3C. Renders clocks, countdown rings, voice animations, and status indicators.
            </p>
          </div>

          {/* Card 3 */}
          <div className="p-5 rounded-2xl bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-purple-400 bg-purple-500/15 px-2 py-0.5 rounded">VOICE RX</span>
              <span className="text-xs text-ink-400 font-mono">GPIO 4, 5, 6 (I2S RX)</span>
            </div>
            <h4 className="font-bold text-base text-ink-100">INMP441 Digital Microphone</h4>
            <p className="text-xs text-ink-300 leading-relaxed">
              Omnidirectional MEMS mic delivering pristine 24-bit audio directly into the ESP32 DMA buffer for low-latency Whisper speech-to-text.
            </p>
          </div>

          {/* Card 4 */}
          <div className="p-5 rounded-2xl bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-blue-400 bg-blue-500/15 px-2 py-0.5 rounded">AUDIO TX</span>
              <span className="text-xs text-ink-400 font-mono">GPIO 15, 16, 7 (I2S TX)</span>
            </div>
            <h4 className="font-bold text-base text-ink-100">MAX98357 DAC/Amp + Speaker</h4>
            <p className="text-xs text-ink-300 leading-relaxed">
              Class D digital audio amplifier delivering crystal-clear Edge-TTS speech and alarm chimes directly through the desktop speaker.
            </p>
          </div>

          {/* Card 5 */}
          <div className="p-5 rounded-2xl bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-amber-400 bg-amber-500/15 px-2 py-0.5 rounded">ACTUATOR</span>
              <span className="text-xs text-ink-400 font-mono">GPIO 13 (Active LOW)</span>
            </div>
            <h4 className="font-bold text-base text-ink-100">5V Isolated Relay Module</h4>
            <p className="text-xs text-ink-300 leading-relaxed">
              Switches low-voltage desktop lighting and appliances. Triggered by double-tap touch, natural speech ("light chalu karo"), or the dashboard.
            </p>
          </div>

          {/* Card 6 */}
          <div className="p-5 rounded-2xl bg-ink-900 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-mono font-bold text-rose-400 bg-rose-500/15 px-2 py-0.5 rounded">POWER</span>
              <span className="text-xs text-ink-400 font-mono">MT3608 Boost to 5.0V</span>
            </div>
            <h4 className="font-bold text-base text-ink-100">Battery & Power Circuit</h4>
            <p className="text-xs text-ink-300 leading-relaxed">
              18650 Li-ion cell protected by TP4056 USB-C charger, boosted safely to steady 5.0V via MT3608 DC-DC converter for untethered mobility.
            </p>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* System Architecture Section */}
      {/* --------------------------------------------------------------------- */}
      <section id="architecture" className="py-20 px-4 sm:px-8 bg-ink-900/30 border-t border-ink-900">
        <div className="max-w-7xl mx-auto">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <h2 className="text-xs font-bold text-accent uppercase tracking-widest mb-3">System Architecture</h2>
            <h3 className="text-3xl sm:text-4xl font-extrabold text-ink-100 tracking-tight">
              Full-Stack Harmony: Firmware, Backend & Frontend
            </h3>
            <p className="mt-3 text-sm sm:text-base text-ink-300">
              A synchronized pipeline designed for minimal latency, robust fallback modes, and zero drift between hardware and web views.
            </p>
          </div>

          <div className="rounded-3xl p-6 sm:p-8 bg-ink-950 border border-ink-800 shadow-[var(--shadow-neo)]">
            <div className="grid md:grid-cols-4 gap-6 relative">
              <div className="flex flex-col gap-2 p-4 rounded-xl bg-ink-900/60 border border-ink-800">
                <span className="text-xs font-bold text-accent font-mono">01. FIRMWARE</span>
                <h5 className="font-bold text-ink-100">ESP32-S3 Arduino C++</h5>
                <p className="text-xs text-ink-400">
                  Local timers, FreeRTOS audio tasks, I2S capture/playback, SH1106 OLED graphics, capacitive touch debouncing.
                </p>
              </div>

              <div className="flex flex-col gap-2 p-4 rounded-xl bg-ink-900/60 border border-ink-800">
                <span className="text-xs font-bold text-emerald-400 font-mono">02. SYNC HUB</span>
                <h5 className="font-bold text-ink-100">FastAPI & WebSockets</h5>
                <p className="text-xs text-ink-400">
                  Bi-directional event dispatch, state snapshots, REST APIs, and MongoDB Atlas persistence via asynchronous motor.
                </p>
              </div>

              <div className="flex flex-col gap-2 p-4 rounded-xl bg-ink-900/60 border border-ink-800">
                <span className="text-xs font-bold text-purple-400 font-mono">03. AI SERVICES</span>
                <h5 className="font-bold text-ink-100">GroqCloud & Edge-TTS</h5>
                <p className="text-xs text-ink-400">
                  Whisper STT with Hindi/Hinglish support, GPT-OSS-20B conversational reasoning with 8-turn memory, and Edge-TTS audio stream.
                </p>
              </div>

              <div className="flex flex-col gap-2 p-4 rounded-xl bg-ink-900/60 border border-ink-800">
                <span className="text-xs font-bold text-amber-400 font-mono">04. CLIENT APPS</span>
                <h5 className="font-bold text-ink-100">React 19 + Capacitor</h5>
                <p className="text-xs text-ink-400">
                  Vite + Tailwind v4 + Zustand single source of truth. Runs in browsers and builds directly as native Android/iOS APK.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* Bottom CTA Banner */}
      {/* --------------------------------------------------------------------- */}
      <section className="py-20 px-4 sm:px-8 max-w-5xl mx-auto text-center">
        <div className="rounded-3xl p-8 sm:p-12 bg-gradient-to-b from-ink-900 to-ink-950 border border-ink-800 shadow-[var(--shadow-neo)] flex flex-col items-center gap-6">
          <div className="size-14 rounded-2xl bg-accent/15 border border-accent/30 flex items-center justify-center text-accent shadow-[var(--shadow-neo-glow)]">
            <IconChip className="size-8" />
          </div>

          <h3 className="text-3xl sm:text-4xl font-extrabold text-ink-100 tracking-tight max-w-xl">
            Upgrade Your Desk Setup With Ambient Intelligence.
          </h3>

          <p className="text-sm sm:text-base text-ink-300 max-w-lg">
            Experience the combination of tactile hardware and cutting-edge cloud AI. Explore the live dashboard, set up your competition profile, and start focusing.
          </p>

          <div className="flex flex-wrap items-center justify-center gap-4">
            <button
              type="button"
              onClick={handleEnterDashboard}
              className="flex items-center gap-2 px-7 py-3.5 rounded-2xl bg-accent text-ink-950 font-extrabold text-sm shadow-[var(--shadow-neo-glow)] hover:scale-105 active:scale-95 transition-all"
            >
              <span>Enter Web Dashboard</span>
              <IconArrowRight className="size-4" />
            </button>

            <button
              type="button"
              onClick={() => navigate('/login')}
              className="flex items-center gap-2 px-6 py-3.5 rounded-2xl border border-ink-800 bg-ink-900 text-ink-200 font-bold text-sm hover:border-ink-700 transition-all shadow-[var(--shadow-neo-sm)]"
            >
              <span>Sign In / Create Account</span>
            </button>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------------------- */}
      {/* Footer */}
      {/* --------------------------------------------------------------------- */}
      <footer className="border-t border-ink-900 py-8 px-4 sm:px-8 bg-ink-950 text-xs text-ink-400">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <span className="font-bold text-ink-200">AI DeskMate</span>
            <span>•</span>
            <span>ESP32-S3 IoT Assistant</span>
            <span>•</span>
            <span className="text-[11px] font-mono">Backend Socket: {status}</span>
          </div>

          <div className="flex items-center gap-6">
            <Link to="/app" className="hover:text-accent transition-colors">Dashboard</Link>
            <Link to="/login" className="hover:text-accent transition-colors">Login / Register</Link>
            <a href="#hardware" className="hover:text-accent transition-colors">Pinout & Specs</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
