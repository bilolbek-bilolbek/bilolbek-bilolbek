/** Kairo mark: a ring with a dot on it, the moment on the clock face. */
export default function Logo({ live }: { live: boolean }) {
  return (
    <span className="logo">
      <svg viewBox="0 0 32 32" width="26" height="26" aria-hidden="true">
        <circle cx="16" cy="16" r="11" fill="none" stroke="var(--gold)" strokeWidth="2.4" opacity="0.35" />
        <path d="M16 5 A11 11 0 0 1 27 16" fill="none" stroke="var(--gold)" strokeWidth="2.4" strokeLinecap="round" />
        <circle cx="27" cy="16" r="3.4" fill="var(--gold-2)" className={live ? "logo-pulse" : ""} />
      </svg>
      <span className="wordmark">kairo</span>
    </span>
  );
}
