// ESLint 9+ flat config. Replaces .eslintrc.cjs: same rule set, same ignores, expressed the new way.
import js from '@eslint/js';
import tseslint from 'typescript-eslint';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';

export default tseslint.config(
  { ignores: ['dist', 'src/api/schema.d.ts', 'eslint.config.js'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2020, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      // The two hook rules this project has always enforced. eslint-plugin-react-hooks 7 also
      // ships the React Compiler rule set in its recommended config (set-state-in-effect, refs,
      // purity, ...); adopting those is a separate, deliberate change, not a dependency bump.
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      'react-refresh/only-export-components': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',
    },
  },
);
