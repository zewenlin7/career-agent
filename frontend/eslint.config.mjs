import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTypescript,
  {
    files: ["src/components/**/*.tsx", "src/app/**/*.tsx"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@/lib/api/server", "**/lib/api/server"],
              message:
                "Keep backend access in feature server modules or explicit BFF handlers, not shell/UI components.",
            },
          ],
        },
      ],
    },
  },
  globalIgnores([".next/**", "out/**", "next-env.d.ts"]),
]);
