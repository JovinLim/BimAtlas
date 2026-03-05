<script lang="ts">
  interface Props {
    color: string;
    onchange: (color: string) => void;
  }

  let { color, onchange }: Props = $props();

  let open = $state(false);
  let hexInput = $state('');
  let rInput = $state(0);
  let gInput = $state(0);
  let bInput = $state(0);

  const PRESETS = [
    '#4A90D9', '#E67E22', '#2ECC71', '#E74C3C',
    '#9B59B6', '#1ABC9C', '#F1C40F', '#E91E63',
    '#3498DB', '#27AE60', '#8E44AD', '#D35400',
    '#16A085', '#C0392B', '#2980B9', '#F39C12',
  ];

  function hexToRgb(hex: string): [number, number, number] {
    const h = hex.replace('#', '');
    return [
      parseInt(h.substring(0, 2), 16) || 0,
      parseInt(h.substring(2, 4), 16) || 0,
      parseInt(h.substring(4, 6), 16) || 0,
    ];
  }

  function rgbToHex(r: number, g: number, b: number): string {
    const clamp = (v: number) => Math.max(0, Math.min(255, Math.round(v)));
    return '#' + [clamp(r), clamp(g), clamp(b)]
      .map(v => v.toString(16).padStart(2, '0'))
      .join('').toUpperCase();
  }

  function syncFromHex(hex: string) {
    const [r, g, b] = hexToRgb(hex);
    rInput = r;
    gInput = g;
    bInput = b;
  }

  function syncFromRgb() {
    const hex = rgbToHex(rInput, gInput, bInput);
    hexInput = hex;
    onchange(hex);
  }

  function handleHexChange(value: string) {
    hexInput = value;
    const clean = value.replace('#', '');
    if (/^[0-9A-Fa-f]{6}$/.test(clean)) {
      const hex = '#' + clean.toUpperCase();
      hexInput = hex;
      syncFromHex(hex);
      onchange(hex);
    }
  }

  function handlePreset(preset: string) {
    hexInput = preset;
    syncFromHex(preset);
    onchange(preset);
  }

  function handleNativeInput(e: Event) {
    const value = (e.target as HTMLInputElement).value.toUpperCase();
    hexInput = value;
    syncFromHex(value);
    onchange(value);
  }

  function toggle() {
    open = !open;
    if (open) {
      hexInput = color;
      syncFromHex(color);
    }
  }

  $effect(() => {
    hexInput = color;
    syncFromHex(color);
  });
</script>

<!-- svelte-ignore a11y_no_static_element_interactions a11y_click_events_have_key_events -->
<div class="color-picker-wrapper">
  <button
    type="button"
    class="color-swatch"
    style="background: {color}"
    title="Change color"
    onclick={toggle}
  ></button>

  {#if open}
    <div class="color-picker-backdrop" onclick={() => (open = false)}></div>
    <div class="color-picker-popover" onclick={(e) => e.stopPropagation()}>
      <div class="picker-section">
        <input
          type="color"
          class="native-picker"
          value={hexInput}
          oninput={handleNativeInput}
        />
      </div>
      <div class="preset-grid">
        {#each PRESETS as preset}
          <button
            type="button"
            class="preset-swatch"
            class:active={hexInput === preset}
            style="background: {preset}"
            title={preset}
            onclick={() => handlePreset(preset)}
          ></button>
        {/each}
      </div>
      <div class="input-row">
        <label class="input-label">
          <span>Hex</span>
          <input
            type="text"
            class="hex-input"
            value={hexInput}
            maxlength={7}
            oninput={(e) => handleHexChange(e.currentTarget.value)}
          />
        </label>
      </div>
      <div class="input-row rgb-row">
        <label class="input-label">
          <span>R</span>
          <input
            type="number"
            class="rgb-input"
            min="0"
            max="255"
            bind:value={rInput}
            oninput={syncFromRgb}
          />
        </label>
        <label class="input-label">
          <span>G</span>
          <input
            type="number"
            class="rgb-input"
            min="0"
            max="255"
            bind:value={gInput}
            oninput={syncFromRgb}
          />
        </label>
        <label class="input-label">
          <span>B</span>
          <input
            type="number"
            class="rgb-input"
            min="0"
            max="255"
            bind:value={bInput}
            oninput={syncFromRgb}
          />
        </label>
      </div>
    </div>
  {/if}
</div>

<style>
  .color-picker-wrapper {
    position: relative;
    display: inline-flex;
    align-items: center;
  }

  .color-swatch {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    border: 2px solid rgba(255, 255, 255, 0.2);
    cursor: pointer;
    padding: 0;
    flex-shrink: 0;
    transition: border-color 0.15s, transform 0.1s;
  }

  .color-swatch:hover {
    border-color: rgba(255, 255, 255, 0.5);
    transform: scale(1.1);
  }

  .color-picker-backdrop {
    position: fixed;
    inset: 0;
    z-index: 999;
  }

  .color-picker-popover {
    position: absolute;
    top: calc(100% + 6px);
    left: 0;
    z-index: 1000;
    background: #1e1e30;
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 0.5rem;
    padding: 0.6rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
    min-width: 210px;
  }

  .picker-section {
    display: flex;
    justify-content: center;
  }

  .native-picker {
    width: 100%;
    height: 36px;
    border: none;
    background: none;
    cursor: pointer;
    padding: 0;
  }

  .native-picker::-webkit-color-swatch-wrapper {
    padding: 0;
  }

  .native-picker::-webkit-color-swatch {
    border: 1px solid rgba(255, 255, 255, 0.15);
    border-radius: 0.3rem;
  }

  .preset-grid {
    display: grid;
    grid-template-columns: repeat(8, 1fr);
    gap: 4px;
  }

  .preset-swatch {
    width: 20px;
    height: 20px;
    border-radius: 3px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    cursor: pointer;
    padding: 0;
    transition: transform 0.1s, border-color 0.1s;
  }

  .preset-swatch:hover {
    transform: scale(1.15);
    border-color: rgba(255, 255, 255, 0.4);
  }

  .preset-swatch.active {
    border-color: #fff;
    box-shadow: 0 0 0 1px #fff;
  }

  .input-row {
    display: flex;
    gap: 0.4rem;
  }

  .rgb-row {
    gap: 0.3rem;
  }

  .input-label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
  }

  .input-label span {
    font-size: 0.6rem;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  .hex-input,
  .rgb-input {
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 0.25rem;
    color: #ddd;
    padding: 0.25rem 0.35rem;
    font-size: 0.72rem;
    outline: none;
    font-family: monospace;
    width: 100%;
    box-sizing: border-box;
  }

  .hex-input:focus,
  .rgb-input:focus {
    border-color: rgba(255, 136, 102, 0.4);
  }

  .rgb-input {
    -moz-appearance: textfield;
  }

  .rgb-input::-webkit-outer-spin-button,
  .rgb-input::-webkit-inner-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }
</style>
