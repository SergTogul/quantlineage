import js from "@eslint/js";
import react from "eslint-plugin-react";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

/**
 * M9.7 staged ESLint gate for the Vite/React SPA (JSX + .mjs helpers).
 * Start with recommended + React Hooks; disable noisy rules for existing UI debt.
 */
export default [
  {
    ignores: ["dist/**", "runtime-dist/**", "node_modules/**"],
  },
  js.configs.recommended,
  {
    files: ["**/*.{js,jsx,mjs}"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        ...globals.browser,
        ...globals.node,
      },
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    plugins: {
      react,
      "react-hooks": reactHooks,
    },
    settings: {
      react: { version: "detect" },
    },
    rules: {
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      // SPA uses the classic JSX transform via @vitejs/plugin-react.
      "react/react-in-jsx-scope": "off",
      "react/prop-types": "off",
      // Staged: existing console usage in UI error paths — tighten later.
      "no-console": "off",
      // Staged: large App.jsx surface — pay down unused vars gradually.
      "no-unused-vars": [
        "error",
        {
          argsIgnorePattern: "^_",
          varsIgnorePattern: "^_",
          ignoreRestSiblings: true,
        },
      ],
    },
  },
];
