import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}', './node_modules/rizzui/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        surface: '#f6f7f9',
        ink: '#151922',
        muted: '#667085',
        line: '#d9dee7',
        teal: '#0f766e',
        amber: '#b7791f',
        rose: '#be123c',
        indigo: '#4338ca',
      },
      boxShadow: {
        panel: '0 1px 2px rgba(15, 23, 42, 0.08)',
      },
    },
  },
  plugins: [],
} satisfies Config;
