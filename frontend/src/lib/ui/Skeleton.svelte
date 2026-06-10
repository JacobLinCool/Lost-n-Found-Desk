<script lang="ts">
  /** Shimmer placeholder. `lines` renders stacked text rows; otherwise a block
   * with the given height is rendered (e.g. for cards and thumbnails). */
  export let lines = 0;
  export let height = '4rem';
  export let radius = 'var(--r-md)';
</script>

{#if lines > 0}
  <div class="lines" aria-hidden="true">
    {#each Array(lines) as _, i}
      <div class="skeleton line" style={`width:${i === lines - 1 ? 62 : 100 - i * 7}%`}></div>
    {/each}
  </div>
{:else}
  <div class="skeleton" style={`height:${height};border-radius:${radius}`} aria-hidden="true"></div>
{/if}

<style>
  .skeleton {
    background: linear-gradient(
      100deg,
      var(--surface-2) 40%,
      var(--surface-3) 50%,
      var(--surface-2) 60%
    );
    background-size: 200% 100%;
    animation: shimmer 1.6s linear infinite;
  }

  .lines {
    display: grid;
    gap: 0.55rem;
  }

  .line {
    height: 0.8rem;
    border-radius: var(--r-sm);
  }
</style>
