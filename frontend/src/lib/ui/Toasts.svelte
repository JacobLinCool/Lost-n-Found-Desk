<script lang="ts">
  import { toasts } from './toast';
  import Icon from './Icon.svelte';

  const ICON = { success: 'check', error: 'error', info: 'info' } as const;
</script>

<div class="toasts" aria-live="polite">
  {#each $toasts as t (t.id)}
    <div
      class={`toast toast-${t.kind}`}
      role={t.kind === 'error' ? 'alert' : 'status'}
      on:mouseenter={() => toasts.hold(t.id)}
      on:mouseleave={() => toasts.release(t.id, t.kind)}
      on:focusin={() => toasts.hold(t.id)}
      on:focusout={() => toasts.release(t.id, t.kind)}
    >
      <span class="toast-icon"><Icon name={ICON[t.kind]} size={16} /></span>
      <p>{t.message}</p>
      <button class="toast-close" type="button" on:click={() => toasts.dismiss(t.id)} aria-label="Dismiss notification">
        <Icon name="x" size={14} />
      </button>
    </div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    top: var(--s-4);
    right: var(--s-4);
    z-index: 90;
    display: grid;
    gap: var(--s-2);
    width: min(92vw, 24rem);
    pointer-events: none;
  }

  .toast {
    pointer-events: auto;
    display: flex;
    align-items: flex-start;
    gap: var(--s-2);
    padding: var(--s-3) var(--s-3) var(--s-3) var(--s-4);
    border-radius: var(--r-md);
    border: 1px solid var(--line);
    background: var(--surface);
    box-shadow: var(--shadow-3);
    animation: toast-in var(--dur-3) var(--ease-spring);
  }

  .toast p {
    margin: 0;
    flex: 1;
    font-size: var(--text-sm);
    line-height: 1.45;
    color: var(--ink);
    padding-top: 0.05rem;
  }

  .toast-icon {
    display: grid;
    place-items: center;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 50%;
    flex: none;
  }

  .toast-success .toast-icon {
    background: var(--ok-soft);
    color: var(--ok-on-soft);
  }

  .toast-error .toast-icon {
    background: var(--danger-soft);
    color: var(--danger-on-soft);
  }

  .toast-info .toast-icon {
    background: var(--accent-soft);
    color: var(--accent-on-soft);
  }

  .toast-success { border-left: 3px solid var(--ok); }
  .toast-error { border-left: 3px solid var(--danger); }
  .toast-info { border-left: 3px solid var(--accent); }

  .toast-close {
    border: 0;
    background: transparent;
    color: var(--ink-3);
    cursor: pointer;
    border-radius: var(--r-sm);
    padding: 0.25rem;
    min-width: 1.5rem;
    min-height: 1.5rem;
    display: grid;
    place-items: center;
    transition: color var(--dur-1) var(--ease-out), background-color var(--dur-1) var(--ease-out);
  }

  .toast-close:hover {
    color: var(--ink);
    background: var(--surface-3);
  }

  @keyframes toast-in {
    from { opacity: 0; transform: translateX(0.75rem); }
    to { opacity: 1; transform: translateX(0); }
  }
</style>
