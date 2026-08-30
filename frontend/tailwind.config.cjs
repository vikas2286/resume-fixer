module.exports = {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Resume Fixer dark identity: deep navy canvas, cyan accent,
        // muted slate text hierarchy, semantic status hues.
        primary: "#22d3ee",
        "primary-dim": "#155e75",
        danger: "#f87171",
        success: "#34d399",
        warn: "#fbbf24",
        canvas: "#0b1120",
        surface: "#111a2e",
        "surface-2": "#18233c",
        line: "#24314f",
        ink: "#e2e8f0",
        mute: "#94a3b8",
        faint: "#5b6b8c",
      },
      boxShadow: {
        glow: "0 0 24px rgba(34, 211, 238, 0.18)",
        card: "0 8px 28px rgba(2, 6, 23, 0.55)",
      },
      keyframes: {
        fadeUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
      },
      animation: {
        fadeUp: "fadeUp 0.35s ease-out both",
        pulseSoft: "pulseSoft 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

