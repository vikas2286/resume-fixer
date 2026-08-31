const defaultTheme = require("tailwindcss/defaultTheme");

module.exports = {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Resume Fixer "paper & ink" identity: warm cream canvas, ink-black
        // text, a single burnt-sienna accent, warm hairline borders and a
        // restrained semantic set. No gradients, no glow.
        primary: "#b4530f",       // burnt sienna — the one accent
        "primary-dim": "#8a3f0c", // pressed / hover depth of the accent
        danger: "#b3372a",        // brick red (warm, readable on paper)
        success: "#3d7a5c",       // deep sage green
        warn: "#a87b1a",          // dark gold
        canvas: "#f6f1e7",        // warm paper page background
        surface: "#fdfaf3",       // card stock (a step lighter than canvas)
        "surface-2": "#efe7d8",   // inset wells / kraft tint
        line: "#ddd2bc",          // warm hairline border
        ink: "#211b13",           // warm near-black text
        mute: "#5d564b",          // secondary text
        faint: "#948b7b",         // tertiary text
      },
      fontFamily: {
        // Fraunces: crafted display serif for headings & big numbers.
        display: ["Fraunces", "Georgia", "Times New Roman", "serif"],
        // Instrument Sans: clean, slightly warm body face (not the default
        // geometric-SaaS look).
        sans: ["Instrument Sans", ...defaultTheme.fontFamily.sans],
      },
      boxShadow: {
        // Grounded, physical shadows — a tight contact line plus a soft
        // drop. No colored glow.
        glow: "0 1px 2px rgba(138, 63, 12, 0.28)",
        card: "0 1px 2px rgba(63, 45, 20, 0.05), 0 12px 32px -16px rgba(63, 45, 20, 0.22)",
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

