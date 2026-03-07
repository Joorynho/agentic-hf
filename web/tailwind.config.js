/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'bg-primary': '#0b0f14',
        'bg-secondary': '#1a1f2e',
        'text-primary': '#ffffff',
        'text-secondary': '#a0aec0',
        'accent-cyan': '#00d9ff',
        'accent-red': '#ff4757',
        'steel-blue': '#4a5568',
      },
      fontFamily: {
        'mono': ['"JetBrains Mono"', '"Courier New"', 'monospace'],
      },
      backgroundColor: {
        'gray-950': '#0b0f14',
        'gray-900': '#1a1f2e',
        'gray-800': '#2d3748',
      },
      borderColor: {
        'gray-700': '#3d4556',
        'gray-800': '#2d3748',
      },
      textColor: {
        'gray-300': '#cbd5e0',
        'gray-400': '#a0aec0',
        'gray-500': '#718096',
      },
    },
  },
  plugins: [],
}
