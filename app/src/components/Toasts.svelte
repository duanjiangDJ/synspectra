<script lang="ts">
  import { toasts, removeToast } from "../lib/ui";
</script>

<div class="toast-container" aria-live="polite">
  {#each $toasts as toast (toast.id)}
    <button
      type="button"
      class="toast toast-{toast.type}"
      onclick={() => removeToast(toast.id)}
    >
      {toast.message}
    </button>
  {/each}
</div>
