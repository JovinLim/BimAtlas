<script lang="ts">
  import { client, IFC_PRODUCT_QUERY } from "$lib/api/client";
  import {
    ensureSchemaLoaded,
    isAttributeRequiredSync,
  } from "$lib/ifc/attributeSchema";

  interface ProductData {
    globalId: string;
    ifcClass: string;
    name: string | null;
    description: string | null;
    objectType: string | null;
    tag: string | null;
    containedIn: { globalId: string; ifcClass: string; name: string | null } | null;
    relations: {
      globalId: string;
      ifcClass: string;
      name: string | null;
      relationship: string;
    }[];
    predefinedType: string | null;
    attributes: Record<string, unknown> | null;
    representations: {
      globalId: string;
      representationIdentifier: string | null;
      representationType: string | null;
    }[];
    propertySets: Record<string, Record<string, unknown>> | null;
  }

  const props = $props<{
    branchId: string | null;
    revision: number | null;
    globalId: string | null;
    onSelectGlobalId?: (id: string | null) => void;
  }>();

  let product = $state<ProductData | null>(null);
  let loading = $state(false);
  let fetchError = $state<string | null>(null);

  let typeRelation = $state<ProductData["relations"][number] | null>(null);
  let attributeMeta = $state<Record<string, boolean | undefined>>({});

  async function copyValue(text: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // ignore clipboard errors
    }
  }

  function objectEntries<T extends Record<string, unknown>>(
    obj: T | null | undefined,
  ): [string, unknown][] {
    return obj ? Object.entries(obj) : [];
  }

  // Fetch product details whenever context changes
  $effect(() => {
    const gid = props.globalId;
    const bId = props.branchId;
    const rev = props.revision;
    if (!gid || !bId) {
      product = null;
      fetchError = null;
      return;
    }

    loading = true;
    fetchError = null;

    client
      .query(IFC_PRODUCT_QUERY, {
        branchId: bId,
        globalId: gid,
        revision: rev ?? undefined,
      })
      .toPromise()
      .then((result) => {
        if (result.error) {
          fetchError = result.error.message;
          product = null;
        } else if (result.data?.ifcProduct) {
          product = result.data.ifcProduct;
        } else {
          product = null;
        }
      })
      .catch(() => {
        fetchError = "Network error";
        product = null;
      })
      .finally(() => {
        loading = false;
      });
  });

  $effect(() => {
    typeRelation =
      product?.relations.find(
        (r: ProductData["relations"][number]) =>
          r.relationship === "IfcRelDefinesByType",
      ) ?? null;
  });

  $effect(() => {
    const p = product;
    if (!p?.attributes || Object.keys(p.attributes).length === 0) {
      attributeMeta = {};
      return;
    }
    ensureSchemaLoaded().then(() => {
      const meta: Record<string, boolean | undefined> = {};
      for (const key of Object.keys(p.attributes ?? {})) {
        meta[key] = isAttributeRequiredSync(p.ifcClass, key);
      }
      attributeMeta = meta;
    });
  });

  function handleSelectGlobalId(id: string | null) {
    props.onSelectGlobalId?.(id);
  }
</script>

{#if props.globalId}
  <div class="panel-body">
    {#if loading}
      <p class="status-msg">Loading details&hellip;</p>
    {:else if fetchError}
      <!-- Graceful degradation: show globalId even if API is down -->
      <div class="detail">
        <span class="label">GlobalId</span>
        <div class="value-row">
          <span class="value mono">{props.globalId}</span>
          <button
            type="button"
            class="copy-btn"
            title="Copy value"
            aria-label="Copy value"
            onclick={() => copyValue(props.globalId ?? "")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect
                x="9"
                y="9"
                width="13"
                height="13"
                rx="2"
                stroke="currentColor"
                stroke-width="2"
              />
              <path
                d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                stroke="currentColor"
                stroke-width="2"
              />
            </svg>
          </button>
        </div>
      </div>
      <p class="status-msg error">API unavailable</p>
    {:else if product}
      <div class="detail">
        <span class="label">Class</span>
        <div class="value-row">
          <span class="value badge">{product.ifcClass}</span>
          <button
            type="button"
            class="copy-btn"
            title="Copy value"
            aria-label="Copy value"
            onclick={() => copyValue(product!.ifcClass)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect
                x="9"
                y="9"
                width="13"
                height="13"
                rx="2"
                stroke="currentColor"
                stroke-width="2"
              />
              <path
                d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                stroke="currentColor"
                stroke-width="2"
              />
            </svg>
          </button>
        </div>
      </div>
      {#if product.predefinedType}
        <div class="detail">
          <span class="label">Predefined Type</span>
          <div class="value-row">
            <span class="value badge secondary">{product.predefinedType}</span>
          </div>
        </div>
      {/if}
      <div class="detail">
        <span class="label">GlobalId</span>
        <div class="value-row">
          <span class="value mono">{product.globalId}</span>
          <button
            type="button"
            class="copy-btn"
            title="Copy value"
            aria-label="Copy value"
            onclick={() => copyValue(product!.globalId)}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect
                x="9"
                y="9"
                width="13"
                height="13"
                rx="2"
                stroke="currentColor"
                stroke-width="2"
              />
              <path
                d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                stroke="currentColor"
                stroke-width="2"
              />
            </svg>
          </button>
        </div>
      </div>
      {#if product.name}
        <div class="detail">
          <span class="label">Name</span>
          <div class="value-row">
            <span class="value">{product.name}</span>
            <button
              type="button"
              class="copy-btn"
              title="Copy value"
              aria-label="Copy value"
              onclick={() => copyValue(product!.name ?? "")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect
                  x="9"
                  y="9"
                  width="13"
                  height="13"
                  rx="2"
                  stroke="currentColor"
                  stroke-width="2"
                />
                <path
                  d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                  stroke="currentColor"
                  stroke-width="2"
                />
              </svg>
            </button>
          </div>
        </div>
      {/if}
      {#if product.description}
        <div class="detail">
          <span class="label">Description</span>
          <div class="value-row">
            <span class="value">{product.description}</span>
            <button
              type="button"
              class="copy-btn"
              title="Copy value"
              aria-label="Copy value"
              onclick={() => copyValue(product!.description ?? "")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect
                  x="9"
                  y="9"
                  width="13"
                  height="13"
                  rx="2"
                  stroke="currentColor"
                  stroke-width="2"
                />
                <path
                  d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                  stroke="currentColor"
                  stroke-width="2"
                />
              </svg>
            </button>
          </div>
        </div>
      {/if}
      {#if product.objectType}
        <div class="detail">
          <span class="label">Type</span>
          <div class="value-row">
            <span class="value">{product.objectType}</span>
            <button
              type="button"
              class="copy-btn"
              title="Copy value"
              aria-label="Copy value"
              onclick={() => copyValue(product!.objectType ?? "")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect
                  x="9"
                  y="9"
                  width="13"
                  height="13"
                  rx="2"
                  stroke="currentColor"
                  stroke-width="2"
                />
                <path
                  d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                  stroke="currentColor"
                  stroke-width="2"
                />
              </svg>
            </button>
          </div>
        </div>
      {/if}
      {#if product.tag}
        <div class="detail">
          <span class="label">Tag</span>
          <div class="value-row">
            <span class="value mono">{product.tag}</span>
            <button
              type="button"
              class="copy-btn"
              title="Copy value"
              aria-label="Copy value"
              onclick={() => copyValue(product!.tag ?? "")}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect
                  x="9"
                  y="9"
                  width="13"
                  height="13"
                  rx="2"
                  stroke="currentColor"
                  stroke-width="2"
                />
                <path
                  d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                  stroke="currentColor"
                  stroke-width="2"
                />
              </svg>
            </button>
          </div>
        </div>
      {/if}
      {#if product.containedIn}
        <div class="detail">
          <span class="label">Container</span>
          <div class="value-row">
            <span class="value">
              <button
                class="link-btn"
                onclick={() => handleSelectGlobalId(product!.containedIn!.globalId)}
              >
                {product.containedIn.name ?? product.containedIn.ifcClass}
              </button>
            </span>
            <button
              type="button"
              class="copy-btn"
              title="Copy value"
              aria-label="Copy value"
              onclick={() =>
                copyValue(
                  product!.containedIn!.name ?? product!.containedIn!.ifcClass,
                )
              }
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect
                  x="9"
                  y="9"
                  width="13"
                  height="13"
                  rx="2"
                  stroke="currentColor"
                  stroke-width="2"
                />
                <path
                  d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                  stroke="currentColor"
                  stroke-width="2"
                />
              </svg>
            </button>
          </div>
        </div>
      {/if}
      {#if typeRelation}
        <div class="detail">
          <span class="label">Type Definition</span>
          <div class="value-row">
            <button
              class="link-btn"
              onclick={() => handleSelectGlobalId(typeRelation!.globalId)}
            >
              {typeRelation.name ?? typeRelation.ifcClass}
            </button>
            <button
              type="button"
              class="copy-btn"
              title="Copy type"
              aria-label="Copy type"
              onclick={() =>
                copyValue(typeRelation!.name ?? typeRelation!.ifcClass)}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
              </svg>
            </button>
          </div>
        </div>
      {/if}
      {#if product.representations?.length}
        <div class="relations-section">
          <span class="label">Representations ({product.representations.length})</span>
          <ul class="relation-list">
            {#each product.representations as rep}
              <li>
                <div class="relation-main">
                  <button
                    class="link-btn"
                    onclick={() => handleSelectGlobalId(rep.globalId)}
                  >
                    {rep.representationIdentifier ??
                      rep.representationType ??
                      "Shape Representation"}
                  </button>
                  {#if rep.representationType}
                    <span class="rel-type">{rep.representationType}</span>
                  {/if}
                </div>
                <button
                  type="button"
                  class="copy-btn"
                  title="Copy representation"
                  aria-label="Copy representation"
                  onclick={() =>
                    copyValue(
                      rep.representationIdentifier ??
                        rep.representationType ??
                        "Shape Representation",
                    )}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
                  </svg>
                </button>
              </li>
            {/each}
          </ul>
        </div>
      {/if}
      {#if product.attributes}
        <div class="relations-section">
          <span class="label">Attributes</span>
          <ul class="pset-props">
            {#each objectEntries(product.attributes ?? {}) as [key, value]}
              <li>
                <span class="pset-key">{key}</span>
                {#if attributeMeta[key] !== undefined}
                  <span
                    class="attr-badge"
                    class:required={attributeMeta[key] === true}
                    class:optional={attributeMeta[key] === false}
                  >
                    {attributeMeta[key] ? "Required" : "Optional"}
                  </span>
                {/if}
                {#if typeof value === "object" && value !== null}
                  <button
                    type="button"
                    class="view-btn"
                    onclick={() =>
                      document.getElementById("property-sets")?.scrollIntoView({
                        behavior: "smooth",
                      })
                    }
                  >
                    View
                  </button>
                {:else}
                  <div class="attr-value-row">
                    <span class="pset-value">{String(value)}</span>
                    <button
                      type="button"
                      class="copy-btn"
                      title="Copy value"
                      aria-label="Copy value"
                      onclick={() => copyValue(String(value))}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                        <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
                      </svg>
                    </button>
                  </div>
                {/if}
              </li>
            {/each}
          </ul>
        </div>
      {/if}
      {#if product.relations.length > 0}
        <div class="relations-section">
          <span class="label">Relations ({product.relations.length})</span>
          <ul class="relation-list">
            {#each product.relations as n}
              <li>
                <div class="relation-main">
                  <button
                    class="link-btn"
                    onclick={() => handleSelectGlobalId(n.globalId)}
                  >
                    {n.name ?? n.ifcClass}
                  </button>
                  <span class="rel-type">{n.relationship}</span>
                </div>
                <button
                  type="button"
                  class="copy-btn"
                  title="Copy relation"
                  aria-label="Copy relation"
                  onclick={() => copyValue(n.name ?? n.ifcClass)}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                    <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
                  </svg>
                </button>
              </li>
            {/each}
          </ul>
        </div>
      {/if}
      {#if product.propertySets}
        <div class="relations-section" id="property-sets">
          <span class="label">Property Sets</span>
          <div class="pset-list">
            {#each objectEntries(product.propertySets ?? {}) as [psetName, props]}
              <details>
                <summary class="pset-summary">
                  <span class="pset-summary-name">{psetName}</span>
                  <button
                    type="button"
                    class="copy-btn pset-copy-all"
                    title="Copy property set as JSON"
                    aria-label="Copy property set as JSON"
                    onclick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      copyValue(JSON.stringify(props, null, 2));
                    }}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
                    </svg>
                  </button>
                </summary>
                <ul class="pset-props">
                  {#each objectEntries(props as Record<string, unknown>) as [key, value]}
                    <li>
                      <span class="pset-key">{key}</span>
                      <div class="attr-value-row">
                        <span class="pset-value">{String(value)}</span>
                        <button
                          type="button"
                          class="copy-btn"
                          title="Copy value"
                          aria-label="Copy value"
                          onclick={() => copyValue(String(value))}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                            <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2" />
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" />
                          </svg>
                        </button>
                      </div>
                    </li>
                  {/each}
                </ul>
              </details>
            {/each}
          </div>
        </div>
      {/if}
    {:else}
      <div class="detail">
        <span class="label">GlobalId</span>
        <div class="value-row">
          <span class="value mono">{props.globalId}</span>
          <button
            type="button"
            class="copy-btn"
            title="Copy value"
            aria-label="Copy value"
            onclick={() => copyValue(props.globalId ?? "")}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <rect
                x="9"
                y="9"
                width="13"
                height="13"
                rx="2"
                stroke="currentColor"
                stroke-width="2"
              />
              <path
                d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                stroke="currentColor"
                stroke-width="2"
              />
            </svg>
          </button>
        </div>
      </div>
    {/if}
  </div>
{/if}

<style>
  .panel-body {
    flex: 1 1 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    overflow-x: hidden;
  }

  .panel-body .detail {
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
    margin-bottom: 0.6rem;
  }

  .value-row {
    display: flex;
    align-items: flex-start;
    gap: 0.35rem;
    min-width: 0;
  }

  .value-row .value {
    flex: 1;
    min-width: 0;
  }

  .copy-btn {
    flex-shrink: 0;
    background: none;
    border: none;
    color: var(--color-text-muted);
    cursor: pointer;
    padding: 0.2rem;
    line-height: 0;
    border-radius: 0.25rem;
  }

  .copy-btn:hover {
    color: var(--color-brand-500);
    background: color-mix(in srgb, var(--color-brand-500) 8%, transparent);
  }

  .label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--color-text-muted);
  }

  .value {
    font-size: 0.8rem;
    color: var(--color-text-primary);
    word-break: break-all;
  }

  .mono {
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 0.8rem;
  }

  .badge {
    display: inline-block;
    background: color-mix(in srgb, var(--color-brand-500) 10%, transparent);
    color: var(--color-brand-500);
    padding: 0.15rem 0.4rem;
    border-radius: 0.25rem;
    font-size: 0.8rem;
    width: fit-content;
  }

  .badge.secondary {
    background: color-mix(in srgb, var(--color-info) 12%, transparent);
    color: var(--color-info);
  }

  .link-btn {
    background: none;
    border: none;
    color: var(--color-info);
    cursor: pointer;
    padding: 0;
    font-size: 0.8rem;
    text-align: left;
  }

  .link-btn:hover {
    text-decoration: underline;
    color: color-mix(in srgb, var(--color-info) 70%, white);
  }

  .view-btn {
    background: color-mix(in srgb, var(--color-brand-500) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--color-brand-500) 20%, transparent);
    color: var(--color-brand-500);
    padding: 0.15rem 0.5rem;
    border-radius: 0.25rem;
    font-size: 0.8rem;
    cursor: pointer;
  }

  .view-btn:hover {
    background: color-mix(in srgb, var(--color-brand-500) 18%, transparent);
    border-color: color-mix(in srgb, var(--color-brand-500) 35%, transparent);
  }

  .relations-section {
    margin-top: 0.5rem;
    padding-top: 0.5rem;
    border-top: 1px solid var(--color-border-subtle);
  }

  .relation-list {
    list-style: none;
    padding: 0;
    margin: 0.3rem 0 0;
  }

  .relation-list li {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.5rem;
    padding: 0.2rem 0;
    min-height: 1.5em;
  }

  .relation-main {
    flex: 1;
    min-width: 0;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.5rem;
  }

  .relation-list li .link-btn {
    flex: 1;
    min-width: 0;
    word-break: break-word;
  }

  .rel-type {
    font-size: 0.7rem;
    color: var(--color-text-muted);
    text-align: right;
    white-space: normal;
    word-break: break-word;
    flex-shrink: 0;
    max-width: 55%;
  }

  .pset-list {
    margin-top: 0.4rem;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .pset-list details {
    background: var(--color-bg-elevated);
    border-radius: 0.25rem;
    padding: 0.25rem 0.4rem;
  }

  .pset-summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    cursor: pointer;
    font-size: 0.8rem;
    color: var(--color-text-secondary);
    list-style: none;
  }

  .pset-summary::-webkit-details-marker {
    display: none;
  }

  .pset-summary::before {
    content: "▸";
    font-size: 0.6rem;
    color: var(--color-text-muted);
    transition: transform 0.2s;
    flex-shrink: 0;
  }

  .pset-list details[open] .pset-summary::before {
    transform: rotate(90deg);
  }

  .pset-summary-name {
    flex: 1;
    min-width: 0;
  }

  .pset-copy-all {
    flex-shrink: 0;
  }

  .pset-props {
    list-style: none;
    padding: 0.25rem 0 0.35rem 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }

  .pset-props li {
    display: flex;
    align-items: flex-start;
    gap: 0.35rem;
  }

  .attr-value-row {
    display: flex;
    align-items: flex-start;
    gap: 0.35rem;
    min-width: 0;
    flex: 1;
  }

  .attr-value-row .pset-value {
    flex: 1;
    min-width: 0;
  }

  .pset-key {
    font-size: 0.7rem;
    color: var(--color-text-muted);
    margin-right: 0.4rem;
  }

  .attr-badge {
    font-size: 0.65rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    padding: 0.1rem 0.35rem;
    border-radius: 0.2rem;
    margin-left: 0.35rem;
  }

  .attr-badge.required {
    background: color-mix(in srgb, var(--color-danger) 12%, transparent);
    color: var(--color-danger);
  }

  .attr-badge.optional {
    background: color-mix(in srgb, var(--color-info) 10%, transparent);
    color: var(--color-info);
  }

  .pset-value {
    font-size: 0.8rem;
    color: var(--color-text-primary);
    word-break: break-all;
  }

  .panel-body .status-msg {
    flex-shrink: 0;
    color: var(--color-text-muted);
    margin: 0.5rem 0;
    font-size: 0.8rem;
  }

  .error {
    color: var(--color-danger);
  }
</style>

