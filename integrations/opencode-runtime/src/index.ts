/**
 * Plugin entrypoint for the Context Lab intervention runtime.
 *
 * OpenCode resolves a plugin directory through its entry file, so this
 * module exists to expose the frozen Stage 6D hook in the
 * loader-required shape. It holds no injection logic: the hook lives
 * in `./runtime.ts` and the block helpers in `./blocks.ts`.
 */

export { default } from "./runtime.ts";
