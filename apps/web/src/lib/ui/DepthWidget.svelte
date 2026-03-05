<script lang="ts">
  let {
    value = $bindable(1),
    min = 0,
    label = "Subgraph Depth",
  }: {
    value: number;
    min?: number;
    label?: string;
  } = $props();

  let inputValue = $state(value.toString());
  let isEditing = $state(false);

  function handleInput(e: Event) {
    const target = e.target as HTMLInputElement;
    inputValue = target.value;
  }

  function handleBlur() {
    isEditing = false;
    const numValue = parseInt(inputValue, 10);
    if (!isNaN(numValue) && numValue >= min) {
      value = numValue;
      inputValue = value.toString();
    } else {
      inputValue = value.toString();
    }
  }

  function handleFocus() {
    isEditing = true;
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === "Enter") {
      (e.target as HTMLInputElement).blur();
    }
  }

  $effect(() => {
    if (!isEditing) {
      inputValue = value.toString();
    }
  });
</script>

<div class="depth-widget">
  <span class="label">{label}</span>
  <div class="stepper">
    <button
      class="step-btn"
      disabled={value <= min}
      onclick={() => (value = Math.max(min, value - 1))}
      aria-label="Decrease depth"
    >
      &minus;
    </button>
    <input
      type="number"
      class="value-input"
      bind:value={inputValue}
      oninput={handleInput}
      onblur={handleBlur}
      onfocus={handleFocus}
      onkeydown={handleKeydown}
      {min}
      aria-label="Depth value"
    />
    <button
      class="step-btn"
      onclick={() => (value = value + 1)}
      aria-label="Increase depth"
    >
      +
    </button>
  </div>
</div>

<style>
  .depth-widget {
    display: flex;
    flex-direction: column;
    gap: 0.4rem;
  }

  .label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-muted);
  }

  .stepper {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0;
    background: var(--color-bg-elevated);
    border: 1px solid var(--color-border-default);
    border-radius: 0.35rem;
    overflow: hidden;
  }

  .step-btn {
    background: none;
    border: none;
    color: var(--color-text-secondary);
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    font-size: 0.9rem;
    transition:
      background 0.15s,
      color 0.15s;
    padding: 0;
  }

  .step-btn:hover:not(:disabled) {
    background: color-mix(in srgb, var(--color-brand-500) 12%, transparent);
    color: var(--color-brand-500);
  }

  .step-btn:disabled {
    opacity: 0.3;
    cursor: not-allowed;
  }

  .value-input {
    min-width: 28px;
    flex: 1;
    text-align: center;
    font-size: 0.82rem;
    font-weight: 600;
    color: var(--color-brand-500);
    font-variant-numeric: tabular-nums;
    background: transparent;
    border: none;
    outline: none;
    padding: 0;
    appearance: textfield;
    -moz-appearance: textfield;
  }

  .value-input::-webkit-outer-spin-button,
  .value-input::-webkit-inner-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }

  .value-input:focus {
    background: color-mix(in srgb, var(--color-brand-500) 8%, transparent);
  }
</style>
