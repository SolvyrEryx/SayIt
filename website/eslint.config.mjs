// eslint-config-next@16 ships native flat configs — import them directly.
import coreWebVitals from "eslint-config-next/core-web-vitals";
import typescriptConfig from "eslint-config-next/typescript";

const eslintConfig = [
  {
    ignores: ["node_modules/**", ".next/**", "out/**", "coverage/**"],
  },
  ...coreWebVitals,
  ...typescriptConfig,
];

export default eslintConfig;
