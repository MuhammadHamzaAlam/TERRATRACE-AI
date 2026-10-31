/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 950: "#070d17", 900: "#0b1422", 850: "#0f1b2d", 800: "#142238", 700: "#1d2f4a", 600: "#2a4163" },
        slate2: { 100: "#e6ebf2", 300: "#aab6c8", 400: "#8594ab", 500: "#64748b" },
        signal: { DEFAULT: "#3fb8af", dim: "#2a8a83" },
        amber2: "#e0a458", rose2: "#e06c75", mint: "#7bd88f",
      },
      fontFamily: { sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"], mono: ["JetBrains Mono", "ui-monospace", "monospace"] },
    },
  },
  plugins: [],
};
