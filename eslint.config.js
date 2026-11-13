import js from '@eslint/js'
import prettier from 'eslint-config-prettier'
import { defineConfig } from 'eslint/config'
import vue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default defineConfig(
  {
    ignores: ['**/dist/**', '**/coverage/**', '**/htmlcov/**', '.venv/**', 'apps/server/**'],
  },

  js.configs.recommended,
  tseslint.configs.recommendedTypeChecked,
  vue.configs['flat/recommended'],

  {
    languageOptions: {
      parserOptions: {
        // Type-aware rules use the tsconfig next to each file.
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
        extraFileExtensions: ['.vue'],
      },
    },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: { parser: tseslint.parser },
    },
  },
  {
    files: ['**/*.config.{js,ts}', 'scripts/**'],
    languageOptions: { globals: globals.node },
  },
  {
    files: ['apps/web/src/**'],
    languageOptions: { globals: globals.browser },
  },
  {
    // Plain JavaScript (configs, scripts) is not part of a TypeScript project.
    files: ['**/*.{js,mjs}'],
    extends: [tseslint.configs.disableTypeChecked],
  },

  {
    rules: {
      // Fakes implement async interfaces even when they answer right away.
      '@typescript-eslint/require-await': 'off',
      eqeqeq: ['error', 'smart'],
      '@typescript-eslint/consistent-type-imports': ['error', { fixStyle: 'inline-type-imports' }],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // Views and shadcn primitives are named after what they are (Button, HomeView).
      'vue/multi-word-component-names': 'off',
      // Optional typed props (`defineProps<{ x?: T }>()`) are meant to be undefined by default.
      'vue/require-default-prop': 'off',
    },
  },
  {
    // shadcn-vue primitives are copied from the registry as they are.
    files: ['apps/web/src/core/ui/**'],
    rules: {
      'vue/no-template-shadow': 'off',
      // Props types imported from sibling .vue files are not resolved by the type-aware lint.
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-redundant-type-constituents': 'off',
    },
  },
  {
    // Mocks, fakes and test harness components are untyped by nature.
    files: ['apps/*/test/**'],
    rules: {
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-return': 'off',
      '@typescript-eslint/unbound-method': 'off',
      'vue/one-component-per-file': 'off',
    },
  },

  // Formatting is Prettier's job.
  prettier,
)
