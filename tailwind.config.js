/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.{html,js}",
    "./static/**/*.{js,css}",
  ],
  darkMode: 'class', // Activar modo oscuro basado en clase
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#1976D2',
          dark: '#1565C0',
        }
      },
      borderRadius: {
        'message': '15px',
      }
    },
  },
  plugins: [],
} 