// Small line icons for the interview room (24x24, stroke = currentColor)

function Icon({ className = "h-5 w-5", children, ...props }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export const MicIcon = (p) => (
  <Icon {...p}>
    <rect x="9" y="2" width="6" height="12" rx="3" />
    <path d="M19 10v1a7 7 0 0 1-14 0v-1M12 18v4" />
  </Icon>
);

export const MicOffIcon = (p) => (
  <Icon {...p}>
    <path d="M9 9v2a3 3 0 0 0 5.1 2.1M15 9.3V5a3 3 0 0 0-5.9-.7" />
    <path d="M19 10v1a7 7 0 0 1-.6 2.9M5 10v1a7 7 0 0 0 11.6 5.3M12 18v4M3 3l18 18" />
  </Icon>
);

export const CameraIcon = (p) => (
  <Icon {...p}>
    <rect x="2" y="6" width="14" height="12" rx="2" />
    <path d="m16 10 6-3v10l-6-3" />
  </Icon>
);

export const CameraOffIcon = (p) => (
  <Icon {...p}>
    <path d="M10.7 6H14a2 2 0 0 1 2 2v3.3l6-3.3v9M16 16a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h2M3 3l18 18" />
  </Icon>
);

export const ScreenShareIcon = (p) => (
  <Icon {...p}>
    <rect x="2" y="4" width="20" height="13" rx="2" />
    <path d="M8 21h8M12 17v4M9 10l3-3 3 3M12 7v6" />
  </Icon>
);

export const LeaveIcon = (p) => (
  <Icon {...p}>
    <path d="M10 17l-5-5 5-5M5 12h11M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" />
  </Icon>
);

export const ChatIcon = (p) => (
  <Icon {...p}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" />
  </Icon>
);

export const PanelIcon = (p) => (
  <Icon {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M9 4v16" />
  </Icon>
);

export const CloseIcon = (p) => (
  <Icon {...p}>
    <path d="M18 6 6 18M6 6l12 12" />
  </Icon>
);

export const SparkIcon = (p) => (
  <Icon {...p}>
    <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z" />
  </Icon>
);

export const TranscriptIcon = (p) => (
  <Icon {...p}>
    <path d="M4 6h16M4 10h16M4 14h10M4 18h7" />
  </Icon>
);
