<script lang="ts">
  let {
    checked,
    label,
    disabled = false,
    onChange,
  }: {
    checked: boolean;
    label: string;
    disabled?: boolean;
    onChange: (value: boolean) => void;
  } = $props();
</script>

<label class="check-row custom-check" class:disabled>
  <button
    type="button"
    class="checkbox"
    class:checked
    class:disabled
    role="checkbox"
    aria-checked={checked}
    disabled={disabled}
    onclick={() => onChange(!checked)}
  >
    {#if checked}
      <span class="check-mark">✓</span>
    {/if}
  </button>
  <span>{label}</span>
</label>
