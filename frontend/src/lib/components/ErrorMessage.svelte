<script lang="ts">
  let { message }: { message: string } = $props();
</script>

{#if message}
  <div class="alert alert-error fade-in">{message}</div>
{/if}

<style>
  .alert {
    padding: 0.65rem 1rem;
    border-radius: var(--radius);
    font-size: 0.9rem;
  }
  .alert-error {
    background: var(--color-error-bg);
    color: var(--color-error);
    border: 1px solid var(--color-error);
  }
</style>
