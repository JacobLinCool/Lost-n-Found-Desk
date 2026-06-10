<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from './api';
  import { parseRoute, type Route } from './router';
  import type { PublicConfig } from './types';
  import Home from './lib/Home.svelte';
  import PublicClaim from './lib/PublicClaim.svelte';
  import StaffConsole from './lib/StaffConsole.svelte';
  import Toasts from './lib/ui/Toasts.svelte';

  let route: Route = parseRoute(location.pathname);
  let config: PublicConfig = { app_name: 'Lost & Found Desk', prefer_gradio_client_for_models: false };
  let announcement = '';

  function sync(): void {
    route = parseRoute(location.pathname);
    // A fresh "page": reset scroll, move SR/keyboard focus to the new main
    // landmark, and announce the change (title updates alone aren't read out).
    window.scrollTo(0, 0);
    requestAnimationFrame(() => {
      (document.querySelector('main') as HTMLElement | null)?.focus({ preventScroll: true });
      announcement = document.title;
    });
  }

  // Keep the tab title oriented to where the user is.
  $: document.title =
    route.name === 'staff'
      ? `Staff console · ${config.app_name}`
      : route.name === 'public-claim'
        ? `Report a lost item · ${config.app_name}`
        : config.app_name;

  onMount(() => {
    window.addEventListener('popstate', sync);
    api<PublicConfig>('/api/config')
      .then((c) => (config = c))
      .catch(() => {});
    return () => window.removeEventListener('popstate', sync);
  });
</script>

<Toasts />
<div class="sr-only" role="status" aria-live="polite">{announcement}</div>

{#if route.name === 'home'}
  <Home {config} />
{:else if route.name === 'public-claim'}
  {#key `${route.eventId}/${route.claimId}`}
    <PublicClaim eventId={route.eventId} claimId={route.claimId} {config} />
  {/key}
{:else if route.name === 'staff'}
  {#key route.eventId}
    <StaffConsole eventId={route.eventId} {config} />
  {/key}
{/if}
