<script lang="ts">
  import { claimantStatus, staffLabel, statusTone } from '../../status';

  export let status: string;
  /** Which label set to use — claimants never see staff terminology. */
  export let audience: 'claimant' | 'staff' = 'staff';

  $: label = audience === 'claimant' ? claimantStatus(status) : staffLabel(status);
  $: tone = statusTone(status);
</script>

<span class={`badge ${tone === 'neutral' ? '' : `badge-${tone}`}`}>
  <span class="dot"></span>
  {label}
</span>
