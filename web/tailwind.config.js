/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'fantasy-dark': '#0f0f13',
        'fantasy-panel': '#1a1a24',
        'fantasy-border': '#2d2d3f',
        'fantasy-accent': '#c9a25e',
        'fantasy-accent-hover': '#e3b86b',
        'health': '#e53935',
        'mana': '#1e88e5',
        'stamina': '#43a047'
      },
      fontFamily: {
        rpg: ['Cinzel', 'serif'],
        sans: ['Inter', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
