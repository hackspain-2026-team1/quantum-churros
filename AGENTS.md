# Repository instructions

## Frontend stack

- Use SvelteKit 5 with TypeScript and Bun for all frontend work.
- Bun is the only JavaScript package manager and task runner in this repository. Use `bun install`, `bun add`, `bun run` and `bunx`; never introduce npm, pnpm, Yarn or their lockfiles.
- Commit `bun.lock` and keep dependency changes reproducible.

## Component-first UI with shadcn-svelte

- Build every frontend feature component-first from shadcn-svelte. Before writing UI markup or introducing another component library, check the existing local components and the shadcn-svelte registry for the required primitive or pattern.
- Initialize shadcn-svelte with `bunx shadcn-svelte@latest init -c frontend`. Add primitives with `bunx shadcn-svelte@latest add <component> -c frontend` so dependencies, aliases and source files remain consistent with `frontend/components.json`.
- Treat `frontend/components.json` as the source of truth for registry configuration and aliases. Registry primitives live under `frontend/src/lib/components/ui/`.
- Compose registry primitives into product and domain components under `frontend/src/lib/components/`. Routes should assemble components and load data; they should not duplicate reusable controls or large interface sections.
- A custom primitive is allowed only when neither the installed components nor the shadcn-svelte registry provides the required behavior. Build it with the same tokens, accessibility conventions and variant patterns as the local shadcn-svelte components.
- Extend shared primitives centrally when a behavior or style must propagate across the application. Do not fork a primitive per screen or reproduce it with page-local markup.
- Preserve keyboard interaction, focus states, semantic labels, loading states, empty states and error states when composing or adapting components.

## Dependency direction

- `frontend` may consume generated contracts but must not import Python code or research artifacts.
- `backend` may import `engine`; `engine` must not import `backend`.
- `research` may import `engine`; production code must never import `research`.
