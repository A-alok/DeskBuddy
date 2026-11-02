import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  IconBook,
  IconFocus,
  IconRefresh,
  IconSwords,
  IconTrophy,
} from '@/components/icons';
import { Button, Card, EmptyState, Input, PageHeader, cx } from '@/components/ui';
import { api } from '@/lib/api';
import { formatRelative } from '@/lib/format';
import { tap } from '@/lib/native';
import type { CompetitiveActivity, CompetitiveSummary, InvitesList, LeaderboardEntry } from '@/lib/types';
import { useDeskmate } from '@/store/useDeskmate';

const LEAGUE_COLORS: Record<string, { bg: string; text: string; border: string; glow: string; icon: string }> = {
  Bronze: {
    bg: 'bg-amber-950/40',
    text: 'text-amber-400',
    border: 'border-amber-600/50',
    glow: 'shadow-[0_0_20px_rgba(217,119,6,0.2)]',
    icon: '🥉',
  },
  Silver: {
    bg: 'bg-slate-800/60',
    text: 'text-slate-200',
    border: 'border-slate-400/50',
    glow: 'shadow-[0_0_20px_rgba(203,213,225,0.25)]',
    icon: '🥈',
  },
  Gold: {
    bg: 'bg-yellow-950/40',
    text: 'text-yellow-400',
    border: 'border-yellow-500/50',
    glow: 'shadow-[0_0_25px_rgba(234,179,8,0.3)]',
    icon: '🥇',
  },
  Platinum: {
    bg: 'bg-cyan-950/40',
    text: 'text-cyan-300',
    border: 'border-cyan-400/50',
    glow: 'shadow-[0_0_25px_rgba(6,182,212,0.3)]',
    icon: '💠',
  },
  Diamond: {
    bg: 'bg-violet-950/40',
    text: 'text-violet-300',
    border: 'border-violet-400/50',
    glow: 'shadow-[0_0_30px_rgba(168,85,247,0.35)]',
    icon: '💎',
  },
};

export function CompetitivePage() {
  const device = useDeskmate((state) => state.device);
  const currentUser = useDeskmate((state) => state.currentUser);
  const pushToast = useDeskmate((state) => state.pushToast);

  const [summary, setSummary] = useState<CompetitiveSummary | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [activity, setActivity] = useState<CompetitiveActivity[]>([]);
  const [invites, setInvites] = useState<InvitesList>({ incoming: [], outgoing: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Challenge form state
  const [competitorCode, setCompetitorCode] = useState('');
  const [challenging, setChallenging] = useState(false);
  const [actingInviteId, setActingInviteId] = useState<string | null>(null);
  const [copiedCode, setCopiedCode] = useState(false);

  const loadData = async (showSpinner = true) => {
    if (showSpinner) setLoading(true);
    else setRefreshing(true);
    try {
      const [sum, lb, act, inv] = await Promise.all([
        api.competitive.summary(),
        api.competitive.leaderboard(),
        api.competitive.activity(),
        api.competitive.invites(),
      ]);
      setSummary(sum);
      setLeaderboard(lb);
      setActivity(act);
      setInvites(inv);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, [currentUser]);

  const handleSendChallenge = async (e: React.FormEvent) => {
    e.preventDefault();
    const code = competitorCode.trim().toUpperCase();
    if (!code) return;

    tap();
    setChallenging(true);

    try {
      const res = await api.competitive.challenge(code);
      pushToast({
        kind: 'success',
        title: '⚔️ Challenge Sent!',
        body: res.message || 'Challenge sent! The competition will start once your friend accepts.',
      });
      setCompetitorCode('');
      await loadData(false);
    } catch (err: any) {
      const msg = err?.detail || err?.message || 'Failed to send challenge';
      pushToast({
        kind: 'error',
        title: 'Challenge Failed',
        body: msg,
      });
    } finally {
      setChallenging(false);
    }
  };

  const handleAcceptInvite = async (inviteId: string, senderName: string) => {
    tap();
    setActingInviteId(inviteId);
    try {
      const res = await api.competitive.acceptInvite(inviteId);
      pushToast({
        kind: 'success',
        title: '🎉 Competition Started!',
        body: res.message || `Challenge accepted! You and ${senderName} are now competing.`,
      });
      await loadData(false);
    } catch (err: any) {
      pushToast({
        kind: 'error',
        title: 'Could Not Accept',
        body: err?.detail || err?.message || 'Error accepting challenge',
      });
    } finally {
      setActingInviteId(null);
    }
  };

  const handleDeclineInvite = async (inviteId: string) => {
    tap();
    setActingInviteId(inviteId);
    try {
      await api.competitive.declineInvite(inviteId);
      pushToast({
        kind: 'info',
        title: 'Challenge Declined',
        body: 'You declined the competition challenge.',
      });
      await loadData(false);
    } catch (err: any) {
      pushToast({
        kind: 'error',
        title: 'Error Declining',
        body: err?.detail || err?.message || 'Error declining challenge',
      });
    } finally {
      setActingInviteId(null);
    }
  };

  const handleCancelInvite = async (inviteId: string) => {
    tap();
    setActingInviteId(inviteId);
    try {
      await api.competitive.cancelInvite(inviteId);
      pushToast({
        kind: 'info',
        title: 'Challenge Cancelled',
        body: 'Your challenge request was cancelled.',
      });
      await loadData(false);
    } catch (err: any) {
      pushToast({
        kind: 'error',
        title: 'Error Cancelling',
        body: err?.detail || err?.message || 'Error cancelling challenge',
      });
    } finally {
      setActingInviteId(null);
    }
  };

  const handleRemoveCompetitor = async (code: string, name: string) => {
    tap();
    try {
      await api.competitive.removeCompetitor(code);
      pushToast({
        kind: 'info',
        title: 'Competitor Removed',
        body: `Removed ${name} from your study circle`,
      });
      await loadData(false);
    } catch (err: any) {
      pushToast({
        kind: 'error',
        title: 'Error Removing',
        body: err?.detail || err?.message || 'Could not remove competitor',
      });
    }
  };

  const copyMyCode = () => {
    const code = currentUser?.competition_code || summary?.competition_code || summary?.my_referral_code;
    if (!code) return;
    tap();
    void navigator.clipboard.writeText(code);
    setCopiedCode(true);
    pushToast({
      kind: 'info',
      title: 'Competition Code Copied!',
      body: `Copied ${code} to clipboard! Share it with a classmate to challenge each other.`,
    });
    setTimeout(() => setCopiedCode(false), 3000);
  };

  const myCode = currentUser?.competition_code || summary?.competition_code || summary?.my_referral_code || 'CODE';
  const leagueConfig = summary ? LEAGUE_COLORS[summary.league] || LEAGUE_COLORS.Bronze : LEAGUE_COLORS.Bronze;

  return (
    <>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <PageHeader
          title="Competitive Study Arena"
          subtitle="Challenge classmates by code. When accepted, the live study competition starts!"
        />
        <Button
          variant="outline"
          size="sm"
          className="self-start sm:self-auto gap-2"
          onClick={() => {
            tap();
            void loadData(false);
          }}
          disabled={refreshing}
        >
          <IconRefresh className={cx('size-4', refreshing && 'animate-spin')} />
          <span>Refresh Stats</span>
        </Button>
      </div>

      {loading && !summary ? (
        <div className="py-20 flex flex-col items-center justify-center gap-3">
          <div className="size-8 rounded-full border-2 border-accent border-t-transparent animate-spin" />
          <p className="text-xs text-ink-400 font-medium">Loading Study League Data...</p>
        </div>
      ) : summary ? (
        <div className="flex flex-col gap-6 mt-4">
          {/* 1. Independent Competition Code & Send Challenge Card */}
          <div className="rounded-3xl border border-amber-500/30 bg-gradient-to-r from-ink-950 via-ink-900 to-amber-950/20 p-5 sm:p-6 shadow-[0_0_25px_rgba(245,158,11,0.1)]">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-center">
              {/* Left: Your Unique Code */}
              <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                <div className="size-14 rounded-2xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-3xl shrink-0 shadow-inner">
                  🤝
                </div>
                <div>
                  <span className="text-[10px] uppercase font-bold tracking-wider text-amber-400 block">
                    Your Independent Competition Code
                  </span>
                  <div className="flex items-center gap-2.5 mt-1">
                    <span className="font-mono text-xl sm:text-2xl font-black text-ink-100 px-3.5 py-1 rounded-xl bg-ink-950 border border-ink-800 tracking-wider">
                      {myCode}
                    </span>
                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      onClick={copyMyCode}
                      className="!rounded-xl text-xs font-bold gap-1.5 !bg-amber-500 hover:!bg-amber-400 !text-ink-950"
                    >
                      {copiedCode ? '✓ Copied' : '📋 Copy Code'}
                    </Button>
                  </div>
                  <p className="text-xs text-ink-400 mt-1.5 leading-snug">
                    Share this code with your classmates so they can challenge you.
                  </p>
                </div>
              </div>

              {/* Right: Challenge a Classmate by Code */}
              <form onSubmit={handleSendChallenge} className="flex flex-col gap-2 pt-4 lg:pt-0 border-t lg:border-t-0 lg:border-l border-ink-800 lg:pl-6">
                <span className="text-[10px] uppercase font-bold tracking-wider text-accent block">
                  ⚔️ Challenge a Friend to Compete
                </span>
                <div className="flex gap-2">
                  <Input
                    value={competitorCode}
                    onChange={(e) => setCompetitorCode(e.target.value.toUpperCase())}
                    placeholder="Enter friend's code (e.g. SARA-8840)"
                    className="h-11 font-mono uppercase font-semibold text-xs tracking-wider"
                    maxLength={24}
                    required
                  />
                  <Button
                    type="submit"
                    variant="primary"
                    size="md"
                    disabled={challenging || !competitorCode.trim()}
                    className="h-11 px-4 whitespace-nowrap font-bold gap-1.5 shadow-sm"
                  >
                    {challenging ? (
                      <span className="flex items-center gap-1.5">
                        <span className="size-3.5 border-2 border-ink-950 border-t-transparent rounded-full animate-spin" />
                        Sending...
                      </span>
                    ) : (
                      <>
                        <IconSwords className="size-4" />
                        <span>Challenge</span>
                      </>
                    )}
                  </Button>
                </div>
                <span className="text-[11px] text-ink-400">
                  Sends an invitation challenge. <strong>Competition starts once your friend accepts!</strong>
                </span>
              </form>
            </div>
          </div>

          {/* 2. PENDING CHALLENGES: Incoming & Outgoing Banners */}
          {invites.incoming.length > 0 && (
            <div className="rounded-3xl border border-accent/40 bg-gradient-to-r from-accent/15 via-ink-900 to-accent/10 p-5 shadow-[0_0_30px_rgba(20,184,166,0.15)] flex flex-col gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xl">⚔️</span>
                <h3 className="text-sm font-bold text-accent tracking-wide uppercase">
                  Incoming Competition Challenges ({invites.incoming.length})
                </h3>
              </div>
              <p className="text-xs text-ink-300">
                A friend wants to start a study competition with you! Accept to start competing on the leaderboard:
              </p>

              <div className="flex flex-col gap-2.5 mt-1">
                {invites.incoming.map((inv) => (
                  <div
                    key={inv.id}
                    className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-3.5 rounded-2xl bg-ink-950/80 border border-ink-800"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="text-2xl shrink-0">{inv.sender_avatar || '⚡'}</span>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-ink-100">{inv.sender_name}</span>
                          <span className="font-mono text-xs text-amber-400 bg-ink-900 px-2 py-0.5 rounded border border-ink-800">
                            {inv.sender_code}
                          </span>
                        </div>
                        <p className="text-xs text-ink-400 mt-0.5 truncate">
                          Challenged you {formatRelative(inv.created_at)}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        variant="primary"
                        size="sm"
                        disabled={actingInviteId === inv.id}
                        onClick={() => handleAcceptInvite(inv.id, inv.sender_name)}
                        className="font-bold gap-1 !bg-accent !text-ink-950 shadow-md"
                      >
                        {actingInviteId === inv.id ? 'Starting...' : '✓ Accept & Start Competition'}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={actingInviteId === inv.id}
                        onClick={() => handleDeclineInvite(inv.id)}
                        className="text-ink-400 hover:text-danger text-xs"
                      >
                        Decline
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {invites.outgoing.length > 0 && (
            <div className="rounded-2xl border border-ink-800 bg-ink-900/60 p-4 flex flex-col gap-2.5 text-xs">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-ink-300 flex items-center gap-1.5">
                  <span>⏳</span>
                  <span>Sent Challenges Waiting for Acceptance ({invites.outgoing.length})</span>
                </span>
                <span className="text-[11px] text-ink-400">Competition starts as soon as they accept</span>
              </div>

              <div className="flex flex-col gap-2">
                {invites.outgoing.map((inv) => (
                  <div
                    key={inv.id}
                    className="flex items-center justify-between p-2.5 rounded-xl bg-ink-950 border border-ink-850"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <span className="text-lg">{inv.recipient_avatar || '🎓'}</span>
                      <div className="min-w-0">
                        <span className="font-semibold text-ink-200">{inv.recipient_name}</span>
                        <span className="font-mono text-amber-400 ml-2">({inv.recipient_code})</span>
                        <span className="text-ink-500 ml-2">• Waiting for acceptance</span>
                      </div>
                    </div>

                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={actingInviteId === inv.id}
                      onClick={() => handleCancelInvite(inv.id)}
                      className="text-ink-400 hover:text-danger text-[11px] h-7 px-2"
                    >
                      Cancel
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 3. Hero Player League Banner */}
          <div
            className={cx(
              'relative overflow-hidden rounded-3xl border p-6 sm:p-8 transition-all duration-500',
              leagueConfig.bg,
              leagueConfig.border,
              leagueConfig.glow,
            )}
          >
            <div className="absolute -right-16 -top-16 size-64 rounded-full bg-accent/10 blur-3xl pointer-events-none" />

            <div className="relative z-10 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
              {/* Left Identity & Rank */}
              <div className="flex items-center gap-5">
                <div className="relative size-16 sm:size-20 rounded-2xl bg-ink-900 border border-ink-700/80 flex items-center justify-center text-3xl sm:text-4xl shadow-inner">
                  <span>{currentUser?.avatar || leagueConfig.icon}</span>
                  <div className="absolute -bottom-2 -right-2 px-2 py-0.5 rounded-full bg-accent text-ink-950 text-xs font-black uppercase font-mono shadow-md">
                    LVL {summary.level}
                  </div>
                </div>

                <div>
                  <div className="flex items-center gap-2.5">
                    <h2 className="text-xl sm:text-2xl font-bold text-ink-100 tracking-tight">
                      {currentUser?.display_name || device?.name || 'Study Scholar'}
                    </h2>
                    <span
                      className={cx(
                        'px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider border font-mono',
                        leagueConfig.text,
                        leagueConfig.border,
                        'bg-ink-900/60',
                      )}
                    >
                      {summary.league} League
                    </span>
                  </div>

                  <p className="mt-1 text-sm text-ink-300 font-medium flex items-center gap-2">
                    <span>🏆 League Rank: <strong className="text-accent font-bold">#{summary.rank}</strong></span>
                    <span>•</span>
                    <span className="text-amber-400 font-semibold">🔥 {summary.streak_days} Day Streak</span>
                    <span>•</span>
                    <span className="text-ink-400 font-mono text-xs">@{currentUser?.username || 'user'}</span>
                  </p>
                </div>
              </div>

              {/* Right Level Progress Bar */}
              <div className="lg:w-80 flex flex-col gap-2 rounded-2xl bg-ink-900/80 border border-ink-800 p-4 shadow-sm backdrop-blur-sm">
                <div className="flex items-baseline justify-between text-xs">
                  <span className="text-ink-300 font-medium">Level {summary.level} Progress</span>
                  <span className="font-mono font-bold text-accent">
                    {summary.current_level_xp} / {summary.next_level_xp} XP ({summary.progress_pct}%)
                  </span>
                </div>

                <div className="h-3 w-full overflow-hidden rounded-full bg-ink-950 border border-ink-800">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-accent to-amber-400 transition-all duration-700 shadow-sm"
                    style={{ width: `${Math.max(6, summary.progress_pct)}%` }}
                  />
                </div>

                <div className="flex items-center justify-between text-[11px] text-ink-400 font-medium mt-0.5">
                  <span>Total Earned: <strong className="text-ink-200">{summary.total_xp} XP</strong></span>
                  <span>{summary.next_level_xp - summary.current_level_xp} XP to LVL {summary.level + 1}</span>
                </div>
              </div>
            </div>
          </div>

          {/* 4. The 3 Core Mastery Pillars */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-ink-300">
                Study Pillars & XP Breakdown
              </h3>
              <span className="text-xs text-ink-400">All real activities automatically award XP</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Pillar 1: Pomodoro Focus */}
              <Card className="rounded-3xl border border-ink-850 p-5 bg-ink-950 shadow-[var(--shadow-neo)] flex flex-col justify-between hover:border-accent/40 transition-all duration-300">
                <div>
                  <div className="flex items-center justify-between border-b border-ink-850 pb-3 mb-3">
                    <div className="flex items-center gap-2.5">
                      <div className="size-9 rounded-xl bg-red-500/15 border border-red-500/30 flex items-center justify-center text-lg">
                        🍅
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-ink-100">Pomodoro Focus</h4>
                        <p className="text-[11px] text-ink-400">Deep study sessions</p>
                      </div>
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-xs font-mono font-bold bg-accent/15 text-accent border border-accent/30">
                      +{summary.pomodoro.xp} XP
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 my-2 text-xs">
                    <div className="p-2.5 rounded-xl bg-ink-900/60 border border-ink-850">
                      <span className="block text-ink-400 text-[11px]">Completed Cycles</span>
                      <strong className="text-base text-ink-100 font-mono">
                        {summary.pomodoro.details.completed_sessions || 0}
                      </strong>
                    </div>
                    <div className="p-2.5 rounded-xl bg-ink-900/60 border border-ink-850">
                      <span className="block text-ink-400 text-[11px]">Focus Time</span>
                      <strong className="text-base text-ink-100 font-mono">
                        {summary.pomodoro.details.focus_minutes || 0}m
                      </strong>
                    </div>
                  </div>
                </div>

                <Link to="/pomodoro" className="mt-4">
                  <Button variant="subtle" size="sm" className="w-full gap-2 !rounded-xl">
                    <IconFocus className="size-3.5" /> Start Focus Session
                  </Button>
                </Link>
              </Card>

              {/* Pillar 2: Competitive Tasks */}
              <Card className="rounded-3xl border border-amber-500/20 p-5 bg-gradient-to-b from-ink-950 to-amber-950/10 shadow-[var(--shadow-neo)] flex flex-col justify-between hover:border-amber-500/40 transition-all duration-300">
                <div>
                  <div className="flex items-center justify-between border-b border-ink-850 pb-3 mb-3">
                    <div className="flex items-center gap-2.5">
                      <div className="size-9 rounded-xl bg-amber-500/15 border border-amber-500/30 flex items-center justify-center text-lg">
                        ⚔️
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-amber-300">Competitive Tasks</h4>
                        <p className="text-[11px] text-ink-400">Challenges & Milestones</p>
                      </div>
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                      +{summary.tasks.xp} XP
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 my-2 text-xs">
                    <div className="p-2.5 rounded-xl bg-ink-900/60 border border-ink-850">
                      <span className="block text-ink-400 text-[11px]">Challenges Crushed</span>
                      <strong className="text-base text-amber-300 font-mono">
                        {summary.tasks.details.competitive_done || 0} / {summary.tasks.details.competitive_total || 0}
                      </strong>
                    </div>
                    <div className="p-2.5 rounded-xl bg-ink-900/60 border border-ink-850">
                      <span className="block text-ink-400 text-[11px]">Personal Done</span>
                      <strong className="text-base text-ink-100 font-mono">
                        {summary.tasks.details.personal_done || 0} / {summary.tasks.details.personal_total || 0}
                      </strong>
                    </div>
                  </div>
                </div>

                <Link to="/tasks" className="mt-4">
                  <Button variant="subtle" size="sm" className="w-full gap-2 !rounded-xl !border-amber-500/30 hover:!border-amber-400">
                    <IconSwords className="size-3.5 text-amber-400" /> Manage Challenges
                  </Button>
                </Link>
              </Card>

              {/* Pillar 3: Quizzes */}
              <Card className="rounded-3xl border border-ink-850 p-5 bg-ink-950 shadow-[var(--shadow-neo)] flex flex-col justify-between hover:border-accent/40 transition-all duration-300">
                <div>
                  <div className="flex items-center justify-between border-b border-ink-850 pb-3 mb-3">
                    <div className="flex items-center gap-2.5">
                      <div className="size-9 rounded-xl bg-blue-500/15 border border-blue-500/30 flex items-center justify-center text-lg">
                        🎯
                      </div>
                      <div>
                        <h4 className="text-sm font-bold text-ink-100">Quiz Arena</h4>
                        <p className="text-[11px] text-ink-400">Study notes testing</p>
                      </div>
                    </div>
                    <span className="px-2 py-0.5 rounded-full text-xs font-mono font-bold bg-accent/15 text-accent border border-accent/30">
                      +{summary.quizzes.xp} XP
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-2 my-2 text-xs">
                    <div className="p-2.5 rounded-xl bg-ink-900/60 border border-ink-850">
                      <span className="block text-ink-400 text-[11px]">Accuracy Score</span>
                      <strong className="text-base text-accent font-mono">
                        {summary.quizzes.details.accuracy_pct || 0}%
                      </strong>
                    </div>
                    <div className="p-2.5 rounded-xl bg-ink-900/60 border border-ink-850">
                      <span className="block text-ink-400 text-[11px]">Questions Aced</span>
                      <strong className="text-base text-ink-100 font-mono">
                        {summary.quizzes.details.correct_answers || 0} / {summary.quizzes.details.questions_answered || 0}
                      </strong>
                    </div>
                  </div>
                </div>

                <Link to="/study" className="mt-4">
                  <Button variant="subtle" size="sm" className="w-full gap-2 !rounded-xl">
                    <IconBook className="size-3.5" /> Open Quiz Arena
                  </Button>
                </Link>
              </Card>
            </div>
          </div>

          {/* 5. Live Leaderboard & Recent Activity Grid */}
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] items-start">
            {/* Live Leaderboard Card (100% Real Accounts, ZERO Mock Data) */}
            <Card
              title={
                <div className="flex items-center justify-between w-full">
                  <span className="flex items-center gap-2 text-ink-100">
                    <IconTrophy className="size-5 text-amber-400" />
                    <span>Active Study Competition</span>
                  </span>
                  <span className="text-xs text-ink-400 font-normal">
                    {leaderboard.length} {leaderboard.length === 1 ? 'Competitor' : 'Competitors'}
                  </span>
                </div>
              }
              className="rounded-3xl border border-ink-850 bg-ink-950 p-6 shadow-[var(--shadow-neo)]"
            >
              <div className="flex flex-col gap-2.5 mt-2">
                {leaderboard.map((entry) => {
                  const isTop3 = entry.rank <= 3;
                  const medal = entry.rank === 1 ? '🥇' : entry.rank === 2 ? '🥈' : entry.rank === 3 ? '🥉' : null;

                  return (
                    <div
                      key={entry.competition_code || entry.name}
                      className={cx(
                        'flex items-center justify-between p-3.5 rounded-2xl transition-all duration-300 border',
                        entry.is_user
                          ? 'bg-accent/15 border-accent/50 shadow-[0_0_15px_rgba(20,184,166,0.2)]'
                          : isTop3
                          ? 'bg-ink-900/80 border-ink-700/60'
                          : 'bg-ink-900/40 border-ink-850',
                      )}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="w-7 text-center font-mono font-bold text-sm shrink-0">
                          {medal ? (
                            <span className="text-base">{medal}</span>
                          ) : (
                            <span className={entry.is_user ? 'text-accent' : 'text-ink-400'}>
                              #{entry.rank}
                            </span>
                          )}
                        </div>

                        <div className="size-9 rounded-xl bg-ink-800 border border-ink-700 flex items-center justify-center text-lg shrink-0">
                          {entry.avatar || '🎓'}
                        </div>

                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 truncate">
                            <span
                              className={cx(
                                'text-sm font-semibold truncate',
                                entry.is_user ? 'text-accent' : 'text-ink-100',
                              )}
                            >
                              {entry.name}
                            </span>
                            {entry.is_user && (
                              <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-accent text-ink-950 uppercase font-mono">
                                YOU
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-2 text-[11px] text-ink-400 truncate">
                            {entry.competition_code && (
                              <span className="font-mono text-[10px] text-amber-400/90 font-bold">
                                {entry.competition_code}
                              </span>
                            )}
                            <span>•</span>
                            <span>{entry.status}</span>
                            <span>•</span>
                            <span className="text-amber-400">🔥 {entry.streak_days}d</span>
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center gap-2.5 shrink-0 ml-2">
                        <span className="hidden sm:inline-block text-[11px] font-mono font-medium text-ink-400 px-2 py-0.5 rounded bg-ink-950 border border-ink-800">
                          LVL {entry.level}
                        </span>
                        <span className="font-mono font-bold text-sm text-ink-100">
                          {entry.total_xp} <span className="text-xs text-accent">XP</span>
                        </span>

                        {!entry.is_user && entry.competition_code && (
                          <button
                            type="button"
                            onClick={() => handleRemoveCompetitor(entry.competition_code!, entry.name)}
                            className="text-ink-500 hover:text-danger p-1 rounded-lg transition-colors text-xs ml-1"
                            title="Remove from competition"
                          >
                            ✕
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}

                {/* Solo empty state callout */}
                {leaderboard.length === 1 && (
                  <div className="mt-3 p-4 rounded-2xl bg-ink-900/50 border border-dashed border-ink-800 text-center">
                    <span className="text-2xl block mb-1">🎯</span>
                    <h5 className="text-xs font-bold text-ink-200">You are currently solo on the leaderboard!</h5>
                    <p className="text-[11px] text-ink-400 mt-1 max-w-sm mx-auto leading-relaxed">
                      Send a challenge to a classmate above (e.g. <strong className="font-mono text-amber-400">SARA-8840</strong>). Once they accept your challenge, your competition officially starts and they will appear on this leaderboard!
                    </p>
                  </div>
                )}
              </div>
            </Card>

            {/* Right Column: Achievements & Activity */}
            <div className="flex flex-col gap-6">
              {/* Badges Card */}
              <Card
                title={
                  <span className="flex items-center gap-2">
                    <span>🎖️</span> Achievements & Badges
                  </span>
                }
                className="rounded-3xl border border-ink-850 bg-ink-950 p-6 shadow-[var(--shadow-neo)]"
              >
                <div className="grid grid-cols-2 gap-2.5 mt-2">
                  {summary.badges.map((badge) => (
                    <div
                      key={badge.id}
                      className={cx(
                        'p-3 rounded-2xl border transition-all duration-300 flex flex-col gap-1',
                        badge.unlocked
                          ? 'bg-ink-900 border-accent/40 shadow-sm'
                          : 'bg-ink-950/60 border-ink-900 opacity-45',
                      )}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-2xl">{badge.icon}</span>
                        {badge.unlocked ? (
                          <span className="text-[10px] font-bold text-accent uppercase font-mono">Unlocked</span>
                        ) : (
                          <span className="text-[10px] font-mono text-ink-500">Locked</span>
                        )}
                      </div>
                      <h5 className="text-xs font-bold text-ink-100 truncate mt-1">{badge.name}</h5>
                      <p className="text-[10px] text-ink-400 leading-tight line-clamp-2">{badge.description}</p>
                    </div>
                  ))}
                </div>
              </Card>

              {/* Recent Activity Stream */}
              <Card
                title={
                  <span className="flex items-center gap-2">
                    <span>⚡</span> Recent Activity Feed
                  </span>
                }
                className="rounded-3xl border border-ink-850 bg-ink-950 p-6 shadow-[var(--shadow-neo)]"
              >
                {activity.length === 0 ? (
                  <EmptyState
                    title="No recorded activities yet"
                    body="Complete a Pomodoro, crush a competitive task, or take a quiz to log activity here!"
                  />
                ) : (
                  <ul className="flex flex-col gap-3 mt-1 max-h-[340px] overflow-y-auto pr-1">
                    {activity.slice(0, 8).map((item) => (
                      <li
                        key={item.id}
                        className="flex items-start justify-between gap-3 p-3 rounded-2xl bg-ink-900/60 border border-ink-850 text-xs"
                      >
                        <div className="flex items-start gap-2.5 min-w-0">
                          <span className="text-base shrink-0 mt-0.5">
                            {item.kind === 'pomodoro' ? '🍅' : item.kind === 'task' ? '⚔️' : '🎯'}
                          </span>
                          <div className="min-w-0">
                            <h6 className="font-semibold text-ink-100 truncate">{item.title}</h6>
                            <p className="text-[11px] text-ink-400 truncate">{item.description}</p>
                            <span className="text-[10px] text-ink-500 block mt-0.5">
                              {formatRelative(item.timestamp)}
                            </span>
                          </div>
                        </div>

                        <span className="shrink-0 px-2 py-0.5 rounded-full font-mono font-bold text-[11px] bg-accent/15 text-accent border border-accent/30">
                          +{item.xp_earned} XP
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          </div>
        </div>
      ) : null}
    </>
  );
}
