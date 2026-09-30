<script lang="ts">
  let { message }: { message: string } = $props();
</script>

{#if message}
  <div class="alert alert-error fade-in" role="alert">{message}</div>
{/if}
