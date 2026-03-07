<script lang="ts">
  let { text = 'Loading...' }: { text?: string } = $props();
</script>

<p class="loading-text">{text}</p>

<style>
  .loading-text {
    color: var(--color-text-muted);
    text-align: center;
    padding: 2rem;
    font-size: 0.95rem;
  }
</style>
