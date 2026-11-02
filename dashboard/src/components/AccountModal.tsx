import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button, Modal } from './ui';
import { IconChip, IconLock, IconLogout } from './icons';
import { tap } from '@/lib/native';
import { useDeskmate } from '@/store/useDeskmate';

interface AccountModalProps {
  open: boolean;
  onClose: () => void;
}

export function AccountModal({ open, onClose }: AccountModalProps) {
  const navigate = useNavigate();
  const currentUser = useDeskmate((state) => state.currentUser);
  const logout = useDeskmate((state) => state.logout);
  const pushToast = useDeskmate((state) => state.pushToast);
  const [copiedCode, setCopiedCode] = useState(false);

  const handleCopyCode = (code: string) => {
    tap();
    void navigator.clipboard.writeText(code);
    setCopiedCode(true);
    pushToast({
      kind: 'info',
      title: 'Competition Code Copied!',
      body: `Code ${code} copied to clipboard. Share it with friends to invite them to study leagues!`,
    });
    setTimeout(() => setCopiedCode(false), 3000);
  };

  const handleSignOut = () => {
    tap();
    logout();
    onClose();
    pushToast({
      kind: 'info',
      title: 'Signed Out',
      body: 'You have been safely signed out.',
    });
    navigate('/login');
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={
        <div className="flex items-center gap-2 text-ink-100">
          <span className="p-1 rounded-lg bg-accent/15 text-accent">
            <IconChip className="size-4" />
          </span>
          <span>Account Profile</span>
        </div>
      }
    >
      <div className="space-y-4">
        {currentUser ? (
          <>
            {/* Active User Card */}
            <div className="rounded-2xl border border-ink-800 bg-ink-950 p-4 shadow-[var(--shadow-neo-sm)]">
              <div className="flex items-center gap-3.5">
                <div className="size-14 rounded-2xl bg-ink-900 border border-ink-800 flex items-center justify-center text-3xl shadow-inner">
                  {currentUser.avatar || '⚡'}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="size-2 rounded-full bg-emerald-400" />
                    <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">
                      Authenticated
                    </span>
                  </div>
                  <h4 className="text-base font-bold text-ink-100 truncate">
                    {currentUser.display_name}
                  </h4>
                  <p className="text-xs text-ink-400 font-mono">
                    @{currentUser.username}
                  </p>
                </div>
              </div>

              {/* Competition Code Highlight Box */}
              {currentUser.competition_code && (
                <div className="mt-4 p-3.5 rounded-xl bg-ink-900 border border-amber-500/30 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 shadow-[var(--shadow-neo-pressed)]">
                  <div>
                    <span className="text-[10px] uppercase font-bold text-amber-400 tracking-wider block">
                      Your Unique Competition Code
                    </span>
                    <p className="text-[11px] text-ink-300 mt-0.5">
                      Classmates enter this code to add you to their study league.
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="font-mono font-extrabold text-base px-3 py-1 rounded-lg bg-ink-950 border border-ink-800 text-amber-300 tracking-wider">
                      {currentUser.competition_code}
                    </span>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleCopyCode(currentUser.competition_code)}
                      className="!rounded-lg text-xs cursor-pointer font-bold"
                    >
                      {copiedCode ? '✓ Copied' : 'Copy'}
                    </Button>
                  </div>
                </div>
              )}

              {/* Device Binding */}
              <div className="mt-3 pt-3 border-t border-ink-900 flex justify-between items-center text-xs text-ink-400">
                <span>Associated Device:</span>
                <span className="font-mono text-ink-200">
                  {currentUser.device_id || 'dev-default'}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-2.5 pt-1">
              <Button
                variant="outline"
                onClick={onClose}
                className="w-1/2 cursor-pointer font-medium"
              >
                Close
              </Button>
              <Button
                variant="primary"
                onClick={handleSignOut}
                className="w-1/2 !bg-danger hover:!bg-danger/90 !text-white flex items-center justify-center gap-2 cursor-pointer font-bold"
              >
                <IconLogout className="size-4" />
                <span>Sign Out</span>
              </Button>
            </div>
          </>
        ) : (
          <div className="text-center py-6 space-y-4">
            <div className="size-12 rounded-2xl bg-accent/15 border border-accent/30 text-accent flex items-center justify-center mx-auto">
              <IconLock className="size-6" />
            </div>
            <div>
              <h4 className="text-base font-bold text-ink-100">Not Signed In</h4>
              <p className="text-xs text-ink-400 mt-1">
                Please sign in to view your profile and competition code.
              </p>
            </div>
            <Button
              variant="primary"
              onClick={() => {
                onClose();
                navigate('/login');
              }}
              className="w-full font-bold cursor-pointer"
            >
              Go to Sign In →
            </Button>
          </div>
        )}
      </div>
    </Modal>
  );
}
