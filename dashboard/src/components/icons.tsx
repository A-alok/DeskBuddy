/** Inline stroke icons. Inline rather than an icon package: 14 glyphs, no deps. */

import type { SVGProps } from 'react';

function Base({ children, ...rest }: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const IconHome = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z" />
  </Base>
);

export const IconTimer = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <circle cx="12" cy="13" r="8" />
    <path d="M12 9v4l2.5 2.5M9 2h6" />
  </Base>
);

export const IconStopwatch = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <circle cx="12" cy="13" r="8" />
    <path d="M12 13V8M10 2h4M18.5 6.5 20 5" />
  </Base>
);

export const IconAlarm = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <circle cx="12" cy="13" r="7" />
    <path d="M12 10v3l2 2M5 4 3 6M19 4l2 2" />
  </Base>
);

export const IconFocus = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="3.5" />
  </Base>
);

export const IconTasks = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M9 6h11M9 12h11M9 18h11M4 6l1.5 1.5L8 5M4 12l1.5 1.5L8 11M4 18l1.5 1.5L8 17" />
  </Base>
);

export const IconBell = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M6 9a6 6 0 1 1 12 0c0 4 1.5 5.5 1.5 5.5H4.5S6 13 6 9z" />
    <path d="M10 18a2 2 0 0 0 4 0" />
  </Base>
);

export const IconChart = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M4 20V4M4 20h16M8 20v-6M12 20V9M16 20v-9M20 20v-4" />
  </Base>
);

export const IconChip = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <rect x="7" y="7" width="10" height="10" rx="2" />
    <path d="M10 3v2M14 3v2M10 19v2M14 19v2M3 10h2M3 14h2M19 10h2M19 14h2" />
  </Base>
);

export const IconChat = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M20 12c0 3.9-3.6 7-8 7a9 9 0 0 1-2.6-.4L5 20l1-3.2A6.6 6.6 0 0 1 4 12c0-3.9 3.6-7 8-7s8 3.1 8 7z" />
  </Base>
);

export const IconGear = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <circle cx="12" cy="12" r="3" />
    <path d="M12 3v2.5M12 18.5V21M4.9 7.5l2.2 1.3M16.9 15.2l2.2 1.3M4.9 16.5l2.2-1.3M16.9 8.8l2.2-1.3" />
  </Base>
);

export const IconMore = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <circle cx="5" cy="12" r="1.4" />
    <circle cx="12" cy="12" r="1.4" />
    <circle cx="19" cy="12" r="1.4" />
  </Base>
);

export const IconPlay = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M8 5.5v13l11-6.5z" />
  </Base>
);

export const IconPause = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M9 5v14M15 5v14" />
  </Base>
);

export const IconStop = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <rect x="6" y="6" width="12" height="12" rx="1.5" />
  </Base>
);

export const IconSkip = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M6 5.5v13l9-6.5zM18 5v14" />
  </Base>
);

export const IconFlag = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M6 21V4M6 4h11l-2 4 2 4H6" />
  </Base>
);

export const IconRefresh = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6" />
  </Base>
);

export const IconPower = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M12 3v8M7.5 7a7 7 0 1 0 9 0" />
  </Base>
);

/** Open book — study notes. */
export const IconBook = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M12 6c-1.5-1-3.5-1.5-5-1.5S4 4.8 3 5v13c1-.3 2.5-.8 4-.8s3.5.5 5 1.5c1.5-1 3.5-1.5 5-1.5s3 .5 4 .8V5c-1-.3-2.5-.5-4-.5s-3.5.5-5 1.5Zm0 0v13" />
  </Base>
);

/** Light bulb — the relay-switched LED light. */
export const IconBulb = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.5 1 1.2 1 2V16h5v-.1c0-.8.4-1.5 1-2A6 6 0 0 0 12 3Z" />
  </Base>
);

export const IconTrash = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13M10 11v6M14 11v6" />
  </Base>
);

export const IconPlus = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M12 5v14M5 12h14" />
  </Base>
);

export const IconSend = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M4 12 20 4l-7 16-2-7z" />
  </Base>
);

export const IconMic = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <rect x="9" y="3" width="6" height="10" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </Base>
);

export const IconTrophy = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M6 9H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h2M18 9h2a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2h-2M6 3h12v7a6 6 0 0 1-12 0V3zM9 21h6M12 16v5" />
  </Base>
);

export const IconSwords = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M14.5 17.5 3 6V3h3l11.5 11.5M13 19l6 2 2-6-4.5-4.5M16 16l4 4M19 13l2 2M9.5 17.5 21 6V3h-3L6.5 14.5M11 19l-6 2-2-6 4.5-4.5M8 16l-4 4M5 13l-2 2" />
  </Base>
);

export const IconArrowRight = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M5 12h14M12 5l7 7-7 7" />
  </Base>
);

export const IconSparkles = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z" />
  </Base>
);

export const IconShieldCheck = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    <path d="m9 12 2 2 4-4" />
  </Base>
);

export const IconCheck = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="m5 13 4 4L19 7" />
  </Base>
);

export const IconLogout = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
  </Base>
);

export const IconExternal = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3" />
  </Base>
);

export const IconZap = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
  </Base>
);

export const IconUsers = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
    <circle cx="9" cy="7" r="4" />
    <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
  </Base>
);

export const IconLock = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  </Base>
);

export const IconEye = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z" />
    <circle cx="12" cy="12" r="3" />
  </Base>
);

export const IconEyeOff = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
    <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" />
    <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" />
    <line x1="2" y1="2" x2="22" y2="22" />
  </Base>
);

export const IconWifi = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="M5 12.55a11 11 0 0 1 14.08 0M1.42 9a16 16 0 0 1 21.16 0M8.53 16.11a6 6 0 0 1 6.95 0M12 20h.01" />
  </Base>
);

export const IconBluetooth = (p: SVGProps<SVGSVGElement>) => (
  <Base {...p}>
    <path d="m7 7 10 10-5 5V2l5 5L7 17" />
  </Base>
);




