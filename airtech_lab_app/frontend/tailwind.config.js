/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50:  '#eef6fd',
          100: '#d0e9f9',
          300: '#7bbde8',
          400: '#4da1dc',
          500: '#2b87d4',
          600: '#1e7ec8',
          700: '#1a6bab',
          900: '#0d3d65',
        },
        surface: {
          900: '#f0f4f8',
          800: '#ffffff',
          700: '#f8fafc',
          600: '#e2e8f0',
          500: '#cbd5e1',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
