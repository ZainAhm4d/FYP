/** Tailwind v3 config — scans all pages + JS (template-literal classes included). */
module.exports = {
  content: [
    './*.html',
    './js/**/*.js',
  ],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Space Grotesk"', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        // Brand — single primary family (consolidates the blue/purple/violet drift)
        primary: {
          50:  '#EEF2FF',
          100: '#E0E7FF',
          200: '#C7D2FE',
          300: '#A5B4FC',
          400: '#818CF8',
          500: '#6366F1',
          600: '#4F46E5',
          700: '#4338CA',
          800: '#3730A3',
          900: '#312E81',
        },
        // Data accent — live data, freshness, positive data states
        data: {
          50:  '#F0FDFA',
          100: '#CCFBF1',
          500: '#14B8A6',
          600: '#0D9488',
          700: '#0F766E',
        },
      },
      boxShadow: {
        'xs': '0 1px 2px rgba(15, 23, 42, 0.05)',
        'card': '0 1px 3px rgba(15, 23, 42, 0.06), 0 4px 12px rgba(15, 23, 42, 0.05)',
        'raised': '0 4px 12px rgba(15, 23, 42, 0.08), 0 12px 32px rgba(15, 23, 42, 0.08)',
      },
      borderRadius: {
        'card': '14px',
      },
    },
  },
  plugins: [],
};
