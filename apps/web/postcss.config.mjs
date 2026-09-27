// Tailwind 4 通过 PostCSS 插件接入。v4 不再需要 tailwind.config.js——主题与扫描范围写在 CSS 里。
export default {
  plugins: { "@tailwindcss/postcss": {} },
};