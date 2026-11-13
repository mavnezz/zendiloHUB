// Lets plain TypeScript tooling (e.g. ESLint's type-aware rules) see .vue imports
// as components; vue-tsc and Vite still use the real component types.
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent
  export default component
}
