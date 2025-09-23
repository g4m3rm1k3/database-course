/** @type {import('tailwindcss').Config} */
const colors = require("tailwindcss/colors");

module.exports = {
  darkMode: "class",
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        primary: colors.slate,
        accent: {
          DEFAULT: "#C00000",
          hover: "#A50000",
        },
        "mc-dark-bg": "#1C2526", // Darker for contrast
        "mc-dark-accent": "#2D3333", // Darker for contrast
        "mc-light-bg": "#ECECEC", // Slightly darker for contrast
        "mc-light-accent": "#B0B0B0", // Darker for contrast
        "mc-text-dark": "#F5F5F5", // Brighter for contrast
        "mc-text-light": "#1A1A1A", // Darker for contrast
      },
      fontFamily: {
        sans: ["Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif"],
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
