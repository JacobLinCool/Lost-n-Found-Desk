<script lang="ts">
  import Icon from './Icon.svelte';
  // The brand mark: a luggage tag on an ink chip, tilted like a real tag.
</script>

<span class="logo" aria-hidden="true">
  <Icon name="tag" size={18} />
</span>

<style>
  .logo {
    display: inline-grid;
    place-items: center;
    width: 2.1rem;
    height: 2.1rem;
    border-radius: var(--r-md);
    background: var(--btn-primary-bg);
    color: var(--btn-primary-ink);
    box-shadow: var(--shadow-1);
    flex: none;
  }

  .logo :global(svg) {
    transform: rotate(-8deg);
  }
</style>
