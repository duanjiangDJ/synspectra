<script lang="ts">
  import { t } from "../lib/i18n";
  import { answerConfirm, confirmState } from "../lib/ui";
  import Modal from "./Modal.svelte";

  let inputValue = $state("");

  $effect(() => {
    const value = $confirmState.request?.input?.value;
    if (value !== undefined && value !== inputValue) {
      inputValue = value;
    }
  });

  function openRequest(): boolean {
    return $confirmState.request !== null;
  }

  function confirm(): void {
    if ($confirmState.request?.input) {
      answerConfirm(inputValue);
    } else {
      answerConfirm(true);
    }
    inputValue = "";
  }

  function cancel(): void {
    answerConfirm(null);
    inputValue = "";
  }
</script>

<Modal
  open={openRequest()}
  title={$confirmState.request?.title ?? ""}
  onClose={cancel}
  width="460px"
>
  <p class="muted">{$confirmState.request?.message ?? ""}</p>
  {#if $confirmState.request?.input}
    <label class="inline-label modal-input-label">
      {$confirmState.request.input.label}
      <input
        type="text"
        class="modal-input"
        bind:value={inputValue}
        onkeydown={(event) => {
          if (event.key === "Enter") confirm();
        }}
      />
    </label>
  {/if}
  <div class="button-row modal-footer">
    <button type="button" class="button secondary" onclick={cancel}>
      {$confirmState.request?.cancelLabel ?? $t("common.cancel")}
    </button>
    <button
      type="button"
      class="button danger"
      disabled={$confirmState.request?.input && !inputValue.trim()}
      onclick={confirm}
    >
      {$confirmState.request?.confirmLabel ?? $t("common.confirm")}
    </button>
  </div>
</Modal>
