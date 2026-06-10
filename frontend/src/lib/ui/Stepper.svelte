<script lang="ts">
  import Icon from './Icon.svelte';

  /** Compact progress stepper. Steps before `current` are done, `current` is
   * active; when `done` is set the final step is complete too. */
  export let steps: string[];
  export let current = 0;
  export let done = false;
</script>

<ol class="stepper" aria-label="Progress">
  {#each steps as step, i}
    {@const state = done || i < current ? 'done' : i === current ? 'active' : 'todo'}
    <li class={state} aria-current={state === 'active' ? 'step' : undefined}>
      <span class="marker">
        {#if state === 'done'}
          <Icon name="check" size={11} />
        {:else}
          {i + 1}
        {/if}
      </span>
      <span class="step-label">{step}</span>
      <span class="sr-only">{state === 'done' ? '(completed)' : state === 'active' ? '(current step)' : '(not started)'}</span>
      {#if i < steps.length - 1}<span class="bar" aria-hidden="true"></span>{/if}
    </li>
  {/each}
</ol>

<style>
  .stepper {
    display: flex;
    align-items: flex-start;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  li {
    position: relative;
    flex: 1;
    display: grid;
    justify-items: center;
    gap: 0.3rem;
    min-width: 0;
  }

  .marker {
    display: grid;
    place-items: center;
    width: 1.45rem;
    height: 1.45rem;
    border-radius: 50%;
    font-size: var(--text-xs);
    font-weight: 700;
    background: var(--surface-2);
    border: 1.5px solid var(--line-strong);
    color: var(--ink-3);
    z-index: 1;
    transition: background-color var(--dur-2) var(--ease-out), border-color var(--dur-2) var(--ease-out), color var(--dur-2) var(--ease-out);
  }

  li.active .marker {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent-on-soft);
  }

  li.done .marker {
    background: var(--ok-soft);
    border-color: var(--ok);
    color: var(--ok-on-soft);
  }

  .step-label {
    font-size: var(--text-xs);
    font-weight: 600;
    color: var(--ink-3);
    text-align: center;
    line-height: 1.3;
    padding: 0 0.2rem;
  }

  li.active .step-label {
    color: var(--ink);
  }

  li.done .step-label {
    color: var(--ink-2);
  }

  .bar {
    position: absolute;
    top: 0.72rem;
    left: calc(50% + 0.85rem);
    width: calc(100% - 1.7rem);
    height: 1.5px;
    background: var(--line-strong);
  }

  li.done .bar {
    background: var(--ok);
  }
</style>
