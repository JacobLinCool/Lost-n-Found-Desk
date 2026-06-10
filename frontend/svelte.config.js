import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
  // Enables <script lang="ts"> in .svelte components and is used by svelte-check.
  preprocess: vitePreprocess(),
};
