/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        racing: {
          bg: '#121212',
          card: '#1E1E1E',
          red: '#FF1E1E',
          gold: '#FFD700',
          white: '#FFFFFF',
          gray: '#A0A0A0',
          dark: '#0A0A0A'
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      }
    },
  },
  plugins: [],
}
