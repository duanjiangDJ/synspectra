<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    open,
    title,
    onClose,
    width = "640px",
    children,
  }: {
    open: boolean;
    title: string;
    onClose: () => void;
    width?: string;
    children?: Snippet;
  } = $props();
</script>

{#if open}
  <div
    class="modal-overlay"
    role="presentation"
    onclick={onClose}
    onkeydown={(event) => {
      if (event.key === "Escape") onClose();
    }}
  >
    <div
      class="modal"
      style:width={width}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      onmousedown={(event) => event.stopPropagation()}
    >
      <div class="modal-header">
        <h3 class="card-title">{title}</h3>
        <button type="button" class="icon-button" onclick={onClose} aria-label="close">
          ×
        </button>
      </div>
      <div class="modal-body">
        {@render children?.()}
      </div>
    </div>
  </div>
{/if}
