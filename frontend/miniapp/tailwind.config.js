/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        tg: {
          bg: 'var(--tg-bg, #ffffff)',
          text: 'var(--tg-text, #000000)',
          hint: 'var(--tg-hint, #999999)',
          link: 'var(--tg-link, #2678b6)',
          button: 'var(--tg-button, #3390ec)',
          'button-text': 'var(--tg-button-text, #ffffff)',
          'bg-secondary': 'var(--tg-bg-secondary, #f0f0f0)',
        },
      },
    },
  },
  plugins: [],
};
