<script lang="ts">
  import Icon from './Icon.svelte';
  import type { IconName } from './Icon.svelte';

  export let icon: IconName = 'package';
  export let title: string;
  export let description = '';
</script>

<div class="empty">
  <span class="empty-icon"><Icon name={icon} size={20} /></span>
  <p class="empty-title">{title}</p>
  {#if description}<p class="empty-desc">{description}</p>{/if}
  {#if $$slots.default}
    <div class="empty-action"><slot /></div>
  {/if}
</div>

<style>
  .empty {
    display: grid;
    justify-items: center;
    gap: var(--s-2);
    padding: var(--s-6) var(--s-4);
    border: 1px dashed var(--line-strong);
    border-radius: var(--r-md);
    text-align: center;
    animation: fade-in var(--dur-3) var(--ease-out);
  }

  .empty-icon {
    display: grid;
    place-items: center;
    width: 2.6rem;
    height: 2.6rem;
    border-radius: 50%;
    background: var(--surface-2);
    color: var(--ink-3);
  }

  .empty-title {
    margin: 0;
    font-weight: 650;
    color: var(--ink-2);
  }

  .empty-desc {
    margin: 0;
    max-width: 26rem;
    color: var(--ink-3);
    font-size: var(--text-sm);
    line-height: 1.55;
  }

  .empty-action {
    margin-top: var(--s-2);
  }
</style>
