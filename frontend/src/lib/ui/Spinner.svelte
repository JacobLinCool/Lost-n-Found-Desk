<script lang="ts">
  export let size = 16;
</script>

<svg
  class="spinner"
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2.5"
  stroke-linecap="round"
  aria-hidden="true"
  focusable="false"
>
  <circle cx="12" cy="12" r="9" opacity="0.25" />
  <path d="M21 12a9 9 0 0 0-9-9" />
</svg>

<style>
  .spinner {
    flex: none;
    animation: spin 0.8s linear infinite;
  }
</style>
