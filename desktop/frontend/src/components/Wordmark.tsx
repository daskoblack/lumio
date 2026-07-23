export function Wordmark({ size = 32 }: { size?: number }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-display)',
        fontWeight: 800,
        fontSize: size,
        letterSpacing: '-0.03em',
        display: 'flex',
        alignItems: 'baseline',
      }}
    >
      Lumi
      <span
        aria-hidden
        style={{
          display: 'inline-block',
          width: '0.62em',
          height: '0.62em',
          borderRadius: '50%',
          background:
            'radial-gradient(circle at 35% 30%, #fff8e8, var(--glow) 55%, var(--glow-2) 120%)',
          boxShadow: '0 0 16px 2px color-mix(in srgb, var(--glow) 55%, transparent)',
          margin: '0 1px',
          transform: 'translateY(0.05em)',
        }}
      />
    </div>
  );
}
