/** @type {import('tailwindcss').Config} */
module.exports = {
  // Enable dark mode based on the 'class' strategy
  darkMode: "class",
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        // Define our custom gold accent color
        gold: "#eeaf00",
      },
    },
  },
  plugins: [],
};
