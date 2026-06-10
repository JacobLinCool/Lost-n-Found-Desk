<script lang="ts">
  import Icon from './Icon.svelte';

  export let text: string;
  export let label = 'Copy';

  let copied = false;
  let failed = false;
  let timer: ReturnType<typeof setTimeout> | undefined;

  async function copy(): Promise<void> {
    clearTimeout(timer);
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
      failed = false;
    } catch (_) {
      copied = false;
      failed = true;
    }
    timer = setTimeout(() => {
      copied = false;
      failed = false;
    }, 1800);
  }
</script>

<button class="btn btn-link btn-sm" class:copied type="button" on:click={copy}>
  {#if copied}
    <span class="pop"><Icon name="check" size={14} /></span>Copied
  {:else if failed}
    Couldn't copy — select it manually
  {:else}
    <Icon name="copy" size={14} />{label}
  {/if}
</button>
<span class="sr-only" role="status">{copied ? 'Copied to clipboard' : ''}</span>

<style>
  .copied {
    color: var(--ok-on-soft);
    background: var(--ok-soft);
  }

  .copied:hover:not(:disabled) {
    color: var(--ok-on-soft);
    background: var(--ok-soft);
  }

  .pop {
    display: inline-grid;
    place-items: center;
    animation: pop var(--dur-2) var(--ease-spring);
  }
</style>
