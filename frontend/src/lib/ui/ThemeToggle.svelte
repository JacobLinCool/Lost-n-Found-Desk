<script lang="ts">
  import Icon from './Icon.svelte';
  import { themePref, cycleTheme } from './theme';

  const META = {
    system: { icon: 'monitor', label: 'Theme: match system' },
    light: { icon: 'sun', label: 'Theme: light' },
    dark: { icon: 'moon', label: 'Theme: dark' },
  } as const;

  $: meta = META[$themePref];
</script>

<button
  class="btn btn-ghost btn-icon"
  type="button"
  on:click={cycleTheme}
  aria-label={`${meta.label} — switch theme`}
  title={meta.label}
>
  {#key $themePref}
    <span class="swap"><Icon name={meta.icon} size={16} /></span>
  {/key}
</button>

<style>
  .swap {
    display: inline-grid;
    place-items: center;
    animation: pop var(--dur-2) var(--ease-spring);
  }
</style>
