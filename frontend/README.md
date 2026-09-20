Created by Claude Code in GOAL.md phase 2:
  npx create-next-app@latest . --ts --tailwind --app --src-dir --eslint --no-import-alias
  npx shadcn@latest init && npx shadcn@latest add button card input dialog progress
Keep next.config.ts (output: "export"). The build output `out/` is copied into the API image by the
Dockerfile and served by FastAPI at "/". The gallery page is /g/ and reads ?o=<order>&t=<token>.
NEXT_PUBLIC_* values are written by CI from GitHub variables into .env.production. Never a secret.
