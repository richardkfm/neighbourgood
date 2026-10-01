<script lang="ts">
  let { text = 'Loading...' }: { text?: string } = $props();
</script>

<div class="skeleton-stack" role="status" aria-busy="true">
  <span class="sr-only">{text}</span>
  <span class="skeleton skeleton-line is-short" aria-hidden="true"></span>
  <span class="skeleton skeleton-card" aria-hidden="true"></span>
</div>
