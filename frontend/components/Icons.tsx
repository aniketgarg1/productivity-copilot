interface IconProps {
  size?: number;
  stroke?: string;
  className?: string;
}

const base = (size: number, stroke: string) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke,
  strokeWidth: 1.6,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const FlagIcon = ({ size = 18, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)}>
    <path d="M4 19V5" />
    <path d="M4 7h9l-1.5 3L13 13H4" />
  </svg>
);

export const CalendarIcon = ({ size = 18, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)}>
    <rect x="3" y="5" width="18" height="16" rx="2" />
    <path d="M3 10h18M8 3v4M16 3v4" />
  </svg>
);

export const ChartIcon = ({ size = 18, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)}>
    <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
  </svg>
);

export const PhoneIcon = ({ size = 18, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)}>
    <path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A15 15 0 0 1 3 6a2 2 0 0 1 2-2Z" />
  </svg>
);

export const SparkIcon = ({ size = 14, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={2}>
    <path d="M12 3v3M5.5 5.5l2 2M3 12h3M18 12h3M16.5 7.5l2-2" />
    <circle cx="12" cy="15" r="5" />
  </svg>
);

export const CheckCircleIcon = ({ size = 17, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={2}>
    <circle cx="12" cy="12" r="9" />
    <path d="m8.5 12 2.5 2.5 4.5-5" />
  </svg>
);

export const ClockIcon = ({ size = 17, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={2}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
);

export const CircleIcon = ({ size = 17, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={1.8}>
    <circle cx="12" cy="12" r="9" />
  </svg>
);

export const SkipIcon = ({ size = 17, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={1.8}>
    <circle cx="12" cy="12" r="9" />
    <path d="M9 9l6 6M15 9l-6 6" />
  </svg>
);

export const MicIcon = ({ size = 17, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={1.7}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);

export const ArrowRightIcon = ({ size = 17, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={1.9}>
    <path d="M5 12h13M12 6l6 6-6 6" />
  </svg>
);

export const SyncIcon = ({ size = 15, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={1.8}>
    <path d="M21 12a9 9 0 0 1-9 9 9 9 0 0 1-7.5-4M3 12a9 9 0 0 1 9-9 9 9 0 0 1 7.5 4" />
    <path d="M20 3v5h-5M4 21v-5h5" />
  </svg>
);

export const TrashIcon = ({ size = 15, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={1.7}>
    <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" />
  </svg>
);

export const ChevronLeftIcon = ({ size = 15, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={1.8}>
    <path d="M14 6l-6 6 6 6" />
  </svg>
);

export const ChevronRightIcon = ({ size = 15, stroke = "currentColor" }: IconProps) => (
  <svg {...base(size, stroke)} strokeWidth={1.8}>
    <path d="M10 6l6 6-6 6" />
  </svg>
);
