<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { api, absoluteUrl, authorizedImageSrc, staffHeaders, ApiError } from '../api';
  import { gradioCreateItem, gradioMatchClaim, gradioDraftMessage } from '../gradioApi';
  import { navigate, eventPublicPath } from '../router';
  import { staffLabel } from '../status';
  import type {
    Claim,
    ClaimsResponse,
    ItemResponse,
    ItemsResponse,
    ItemWithPhoto,
    MessageResponse,
    PublicConfig,
    Report,
    VerifyResponse,
  } from '../types';
  import Icon from './ui/Icon.svelte';
  import type { IconName } from './ui/Icon.svelte';
  import Logo from './ui/Logo.svelte';
  import Spinner from './ui/Spinner.svelte';
  import Skeleton from './ui/Skeleton.svelte';
  import StatusBadge from './ui/StatusBadge.svelte';
  import CopyButton from './ui/CopyButton.svelte';
  import EmptyState from './ui/EmptyState.svelte';
  import ThemeToggle from './ui/ThemeToggle.svelte';
  import { toasts } from './ui/toast';

  export let eventId: string;
  export let config: PublicConfig = { app_name: 'Lost & Found Desk', prefer_gradio_client_for_models: false };

  type Tab = 'dashboard' | 'intake' | 'inbox' | 'report';

  const pwKey = `lfd_staff_pw_${eventId}`;
  let password = localStorage.getItem(pwKey) || '';
  let authed = false;
  let authError = '';
  let authBusy = false;
  let checkingStored = !!password;
  let confirmingLogout = false;
  let eventName = '';

  let tab: Tab = 'dashboard';
  let items: ItemWithPhoto[] = [];
  let claims: Claim[] = [];
  let report: Partial<Report> = {};
  let dataLoaded = false;
  let loadError = '';
  let lastSyncAt = 0;
  let now = Date.now();
  let selectedClaimId: string | null = null;
  let intakeBusy = false;
  let intakeError = '';
  let intakeFile: File | null = null;
  let intakePreview = '';
  let matchingBusy = false;
  let draftingFor: string | null = null;
  let draftText = '';
  let staffMsg = '';
  let staffMsgBusy = false;
  let returnFor: string | null = null;
  let returnBusy = false;
  let returnNote = 'Confirmed in person at the desk.';
  let archiveFor: string | null = null;
  let pollTimer: ReturnType<typeof setInterval> | undefined;
  let tickTimer: ReturnType<typeof setInterval> | undefined;

  const imageUrlCache = new Map<string, string>();

  const NAV: ReadonlyArray<{ tab: Tab; icon: IconName; label: string }> = [
    { tab: 'dashboard', icon: 'dashboard', label: 'Overview' },
    { tab: 'intake', icon: 'camera', label: 'Add items' },
    { tab: 'inbox', icon: 'inbox', label: 'Claims' },
    { tab: 'report', icon: 'report', label: 'Report' },
  ];

  type ClaimFilter = 'all' | 'ready' | 'open' | 'matched' | 'closed';
  let claimFilter: ClaimFilter = 'all';
  const FILTERS: ReadonlyArray<{ key: ClaimFilter; label: string }> = [
    { key: 'all', label: 'All' },
    { key: 'ready', label: 'Ready for review' },
    { key: 'open', label: 'Gathering details' },
    { key: 'matched', label: 'Matched' },
    { key: 'closed', label: 'Closed' },
  ];

  function inFilter(c: Claim, f: ClaimFilter): boolean {
    if (f === 'all') return true;
    if (f === 'ready') return c.status === 'ready_for_staff_review';
    if (f === 'open') return c.status === 'draft' || c.status === 'needs_more_info';
    if (f === 'matched') return c.status === 'matched';
    return c.status === 'closed';
  }

  $: filterCounts = Object.fromEntries(
    FILTERS.map((f) => [f.key, claims.filter((c) => inFilter(c, f.key)).length]),
  ) as Record<ClaimFilter, number>;
  $: visibleClaims = claims.filter((c) => inFilter(c, claimFilter));

  // Keep the list and the detail pane in agreement: if the active filter
  // excludes the selected claim, fall over to the first visible one.
  $: if (dataLoaded && selectedClaimId && !visibleClaims.some((c) => c.claim_id === selectedClaimId)) {
    selectedClaimId = visibleClaims[0]?.claim_id ?? null;
  }

  $: pendingReviewCount = report.claims_ready_for_review ?? 0;

  function msg(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
  }

  const whenFormat = new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' });
  function formatWhen(iso: string): string {
    // The backend emits microsecond precision; trim to millis so every Date
    // parser accepts it and the raw-ISO fallback stays unreachable.
    const d = new Date(iso.replace(/(\.\d{3})\d+/, '$1'));
    return Number.isNaN(d.getTime()) ? iso : whenFormat.format(d);
  }
  function privacyNeedsReview(it: { privacy_note?: string }): boolean {
    return (it.privacy_note || '').toLowerCase().includes('identifying');
  }

  $: selectedClaim = claims.find((c) => c.claim_id === selectedClaimId) || visibleClaims[0] || null;

  // Candidates are matched live during the claimant's conversation and stored on
  // the claim, so staff see them automatically (no required button press). Join
  // each with the already-photo-loaded inventory item for display.
  $: enrichedCandidates = (selectedClaim?.candidates ?? []).map((c) => ({
    ...c,
    item: items.find((i) => i.item_id === c.item_id) ?? null,
  }));
  $: matchState = selectedClaim?.match_state ?? '';

  // Safety net: if the effective selection changes (manual click OR the 25s poll
  // re-sorting claims under an unpinned selection), drop any half-composed reply
  // so a message written for claimant A can never be sent to claimant B.
  let composeFor: string | null = null;
  $: if (selectedClaim && selectedClaim.claim_id !== composeFor) {
    composeFor = selectedClaim.claim_id;
    staffMsg = '';
    draftText = '';
    returnFor = null;
  }

  // Relative "last updated" readout, so the background sync is visible.
  $: syncAgo =
    lastSyncAt === 0
      ? ''
      : now - lastSyncAt < 15000
        ? 'just now'
        : `${Math.round((now - lastSyncAt) / 1000)}s ago`;

  function revokeImages(): void {
    for (const url of imageUrlCache.values()) URL.revokeObjectURL(url);
    imageUrlCache.clear();
  }

  async function attachItemPhoto(item: ItemWithPhoto): Promise<ItemWithPhoto> {
    if (!item?.photo_url) return item;
    const key = `${item.item_id}:${item.updated_at || ''}:${password}`;
    const cached = imageUrlCache.get(key);
    if (cached) return { ...item, _photo_src: cached };
    try {
      const src = await authorizedImageSrc(item.photo_url, password);
      imageUrlCache.set(key, src);
      return { ...item, _photo_src: src };
    } catch (_) {
      return { ...item, _photo_src: '' };
    }
  }

  async function loadStaffData(silent = true): Promise<void> {
    try {
      const [itemRes, claimRes, reportRes] = await Promise.all([
        api<ItemsResponse>(`/api/events/${eventId}/staff/items`, { headers: staffHeaders(password) }),
        api<ClaimsResponse>(`/api/events/${eventId}/staff/claims`, { headers: staffHeaders(password) }),
        api<Report>(`/api/events/${eventId}/staff/report`, { headers: staffHeaders(password) }),
      ]);
      items = await Promise.all((itemRes.items || []).map((i) => attachItemPhoto(i as ItemWithPhoto)));
      claims = claimRes.claims || [];
      report = reportRes || {};
      dataLoaded = true;
      loadError = '';
      lastSyncAt = Date.now();
      now = lastSyncAt;
      // Pin the selection so the background poll can't silently switch the
      // active claim out from under a staffer who is composing a reply.
      if (!selectedClaimId && claims.length) selectedClaimId = claims[0].claim_id;
      if (!silent) toasts.success('Up to date.');
    } catch (e) {
      // Never leave a first load failing silently into endless skeletons.
      if (!dataLoaded) loadError = msg(e);
      if (!silent) toasts.error(msg(e));
      throw e;
    }
  }

  type AuthResult = 'ok' | 'rejected' | 'unavailable';
  async function tryAuth(pw: string): Promise<AuthResult> {
    try {
      const res = await api<VerifyResponse>(`/api/events/${eventId}/staff/verify`, {
        method: 'POST',
        headers: staffHeaders(pw),
      });
      eventName = res.name;
      return 'ok';
    } catch (e) {
      // Only a 401 means the password is wrong; anything else is the network
      // or the server, and must not be blamed on the (unrecoverable) password.
      return e instanceof ApiError && e.status === 401 ? 'rejected' : 'unavailable';
    }
  }

  async function login(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    if (!password) {
      authError = 'Enter the staff password.';
      return;
    }
    authBusy = true;
    authError = '';
    const result = await tryAuth(password);
    if (result === 'ok') {
      localStorage.setItem(pwKey, password);
      authed = true;
      await loadStaffData(true).catch(() => {});
      startPolling();
    } else if (result === 'rejected') {
      authError = "That password doesn't match this desk. It was shown once when the desk was created.";
    } else {
      authError = "We couldn't verify right now — check your connection and try again. Your password wasn't rejected.";
    }
    authBusy = false;
  }

  function logout(): void {
    localStorage.removeItem(pwKey);
    password = '';
    authed = false;
    confirmingLogout = false;
    stopPolling();
    revokeImages();
  }

  function openTab(t: Tab): void {
    tab = t;
    if (t !== 'intake') loadStaffData(true).catch(() => {});
  }

  // Live front desk: refresh inbox/dashboard so new reports and claimant
  // replies appear without manual refresh.
  function startPolling(): void {
    stopPolling();
    pollTimer = setInterval(() => {
      if (authed && tab !== 'intake' && !document.hidden) loadStaffData(true).catch(() => {});
    }, 25000);
    tickTimer = setInterval(() => (now = Date.now()), 10000);
  }
  function stopPolling(): void {
    if (pollTimer) clearInterval(pollTimer);
    if (tickTimer) clearInterval(tickTimer);
    pollTimer = undefined;
    tickTimer = undefined;
  }

  function pickIntakePhoto(event: Event): void {
    const file = (event.target as HTMLInputElement).files?.[0] ?? null;
    intakeFile = file;
    intakeError = '';
    if (intakePreview) URL.revokeObjectURL(intakePreview);
    intakePreview = file ? URL.createObjectURL(file) : '';
  }

  function clearIntakePhoto(form: HTMLFormElement): void {
    form.reset();
    intakeFile = null;
    if (intakePreview) URL.revokeObjectURL(intakePreview);
    intakePreview = '';
  }

  async function addItem(event: SubmitEvent): Promise<void> {
    event.preventDefault();
    const form = event.currentTarget as HTMLFormElement;
    const found = (form.elements.namedItem('found_location') as HTMLInputElement)?.value ?? '';
    const note = (form.elements.namedItem('staff_note') as HTMLTextAreaElement)?.value ?? '';
    if (!intakeFile) {
      intakeError = 'Choose a photo of the item first.';
      return;
    }
    intakeBusy = true;
    intakeError = '';
    try {
      if (config.prefer_gradio_client_for_models) {
        await gradioCreateItem(eventId, intakeFile, found, note, password);
      } else {
        const fd = new FormData(form);
        await api<ItemResponse>(`/api/events/${eventId}/staff/items`, {
          method: 'POST',
          headers: staffHeaders(password),
          body: fd,
        });
      }
      await loadStaffData(true);
      clearIntakePhoto(form);
      toasts.success('Item added — the photo description is ready below.');
    } catch (e) {
      toasts.error(msg(e));
    } finally {
      intakeBusy = false;
    }
  }

  async function setItemStatus(itemId: string, status: string, doneMessage: string): Promise<void> {
    try {
      await api(`/api/events/${eventId}/staff/items/${itemId}`, {
        method: 'PATCH',
        headers: staffHeaders(password, { 'content-type': 'application/json' }),
        body: JSON.stringify({ status }),
      });
      archiveFor = null;
      await loadStaffData(true);
      toasts.success(doneMessage);
    } catch (e) {
      toasts.error(msg(e));
    }
  }

  const archiveItem = (itemId: string) =>
    setItemStatus(itemId, 'archived', 'Item archived and removed from suggested matches.');
  // Undo path for a mistaken archive (user control & freedom).
  const restoreItem = (itemId: string) => setItemStatus(itemId, 'unclaimed', 'Item restored to the inventory.');

  /** Focus an element by id on the next tick (after an {#if} swap re-renders). */
  function focusById(id: string): void {
    void tick().then(() => document.getElementById(id)?.focus());
  }

  function openArchiveConfirm(itemId: string): void {
    archiveFor = itemId;
    focusById(`archive-cancel-${itemId}`);
  }

  function cancelArchive(): void {
    const id = archiveFor;
    archiveFor = null;
    if (id) focusById(`archive-open-${id}`);
  }

  function openReturnConfirm(itemId: string): void {
    returnFor = itemId;
    focusById('return-note');
  }

  function cancelReturn(): void {
    const id = returnFor;
    returnFor = null;
    if (id) focusById(`return-open-${id}`);
  }

  function openLogoutConfirm(): void {
    confirmingLogout = true;
    focusById('logout-cancel');
  }

  function cancelLogout(): void {
    confirmingLogout = false;
    focusById('logout-open');
  }

  function selectClaim(c: Claim): void {
    selectedClaimId = c.claim_id;
    draftText = '';
    returnFor = null;
    staffMsg = '';
  }

  // Optional deeper re-match (uses the model in real mode + embedding shortlist).
  // Candidates already show automatically from the live conversation match; this
  // just refreshes them, e.g. after staff added new inventory.
  async function rematch(): Promise<void> {
    if (!selectedClaim) return;
    const cid = selectedClaim.claim_id;
    matchingBusy = true;
    try {
      if (config.prefer_gradio_client_for_models) {
        await gradioMatchClaim(eventId, cid, password);
      } else {
        await api(`/api/events/${eventId}/staff/claims/${cid}/match`, {
          method: 'POST',
          headers: staffHeaders(password),
        });
      }
      await loadStaffData(true);
    } catch (e) {
      toasts.error(msg(e));
    } finally {
      matchingBusy = false;
    }
  }

  async function draftMessage(itemId: string): Promise<void> {
    if (!selectedClaim) return;
    draftingFor = itemId;
    try {
      const res = config.prefer_gradio_client_for_models
        ? await gradioDraftMessage(eventId, selectedClaim.claim_id, itemId, password)
        : await api<MessageResponse>(`/api/events/${eventId}/staff/draft_message`, {
            method: 'POST',
            headers: staffHeaders(password, { 'content-type': 'application/json' }),
            body: JSON.stringify({ claim_id: selectedClaim.claim_id, item_id: itemId }),
          });
      // Show as a preview; never silently clobber a reply the staffer typed.
      draftText = res.message;
    } catch (e) {
      toasts.error(msg(e));
    } finally {
      draftingFor = null;
    }
  }

  function applyDraft(): void {
    staffMsg = staffMsg.trim() ? `${staffMsg.trim()}\n${draftText}` : draftText;
    draftText = '';
  }

  async function sendStaffMessage(): Promise<void> {
    if (!selectedClaim || !staffMsg.trim()) return;
    staffMsgBusy = true;
    try {
      await api(`/api/events/${eventId}/staff/claims/${selectedClaim.claim_id}/message`, {
        method: 'POST',
        headers: staffHeaders(password, { 'content-type': 'application/json' }),
        body: JSON.stringify({ message: staffMsg.trim() }),
      });
      staffMsg = '';
      await loadStaffData(true);
      toasts.success('Message sent — the owner will see it on their report page.');
    } catch (e) {
      toasts.error(msg(e));
    } finally {
      staffMsgBusy = false;
    }
  }

  async function confirmReturn(): Promise<void> {
    if (!selectedClaim || !returnFor || returnBusy) return;
    returnBusy = true;
    try {
      await api(`/api/events/${eventId}/staff/returns`, {
        method: 'POST',
        headers: staffHeaders(password, { 'content-type': 'application/json' }),
        body: JSON.stringify({ item_id: returnFor, claim_id: selectedClaim.claim_id, staff_note: returnNote }),
      });
      returnFor = null;
      await loadStaffData(true);
      toasts.success('Return recorded. The item is no longer suggested for claims.');
    } catch (e) {
      toasts.error(msg(e));
    } finally {
      returnBusy = false;
    }
  }

  // Esc backs out of any pending inline confirmation (user control & freedom),
  // returning focus to the control that opened it.
  function onKeydown(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      if (archiveFor) cancelArchive();
      if (returnFor) cancelReturn();
      if (confirmingLogout) cancelLogout();
    }
  }

  onMount(async () => {
    if (!password) {
      checkingStored = false;
      return;
    }
    const result = await tryAuth(password);
    checkingStored = false;
    if (result === 'ok') {
      authed = true;
      await loadStaffData(true).catch(() => {});
      startPolling();
    } else if (result === 'rejected') {
      // The stored password no longer matches — make the user re-enter it.
      password = '';
    } else {
      // Network/server problem: keep the stored password and say so, instead
      // of implying the (unrecoverable) password was wrong.
      authError = "We couldn't reach the desk to sign you back in — check your connection and try again.";
    }
  });
  onDestroy(() => {
    stopPolling();
    revokeImages();
    if (intakePreview) URL.revokeObjectURL(intakePreview);
  });
</script>

<svelte:window on:keydown={onKeydown} />

{#if !authed}
  <div class="gate">
    <header class="page-bar">
      <a
        class="back-link"
        href="/"
        on:click={(e) => {
          e.preventDefault();
          navigate('/');
        }}
      >
        <Logo /><span class="brand-name">{config.app_name}</span>
      </a>
      <ThemeToggle />
    </header>
    <main tabindex="-1">
    <div class="card gate-card">
      {#if checkingStored}
        <div class="row gate-checking"><Spinner size={16} /><span class="muted">Signing you back in…</span></div>
      {:else}
        <h2><Icon name="key" size={18} />Staff sign in</h2>
        <p class="muted">
          Desk <code>{eventId}</code> — enter the staff password from when this desk was created.
        </p>
        <form on:submit={login} novalidate>
          <label for="pw">Staff password</label>
          <input
            id="pw"
            type="password"
            bind:value={password}
            placeholder="Staff password"
            aria-invalid={authError ? 'true' : undefined}
            aria-describedby={authError ? 'pw-error' : undefined}
            on:input={() => (authError = '')}
          />
          {#if authError}
            <p class="field-error" id="pw-error"><Icon name="error" size={13} />{authError}</p>
          {/if}
          <button type="submit" class="btn btn-primary btn-block" disabled={authBusy}>
            {#if authBusy}<Spinner size={15} />Checking…{:else}Sign in{/if}
          </button>
        </form>
      {/if}
    </div>
    </main>
  </div>
{:else}
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">
        <Logo />
        <div class="brand-text">
          <h1 class="trunc">{eventName || 'Lost & Found'}</h1>
          <p>Staff console · <span class="mono">{eventId}</span></p>
        </div>
      </div>

      <nav class="nav" aria-label="Console sections">
        {#each NAV as item}
          <button
            class:active={tab === item.tab}
            aria-current={tab === item.tab ? 'page' : undefined}
            on:click={() => openTab(item.tab)}
          >
            <Icon name={item.icon} size={16} />
            <span class="nav-label">{item.label}</span>
            {#if item.tab === 'inbox' && pendingReviewCount > 0}
              <span class="nav-count" title={`${pendingReviewCount} ready for review`}>{pendingReviewCount}</span>
            {/if}
          </button>
        {/each}
      </nav>

      <div class="share-box">
        <strong><Icon name="link" size={14} />Public link for owners</strong>
        <p class="hint">Share it, or print it as a QR code at the desk.</p>
        <div class="row share-row">
          <code class="trunc">{absoluteUrl(eventPublicPath(eventId))}</code>
          <CopyButton text={absoluteUrl(eventPublicPath(eventId))} label="Copy" />
        </div>
      </div>

      <div class="sidebar-foot">
        <div class="row sync-row">
          <button class="btn btn-ghost btn-sm" on:click={() => loadStaffData(false).catch(() => {})}>
            <Icon name="refresh" size={13} />Refresh
          </button>
          <ThemeToggle />
        </div>
        {#if syncAgo}
          <p class="sync-note" role="status">Updated {syncAgo} · auto-refreshes</p>
        {/if}
        {#if confirmingLogout}
          <div class="inline-confirm">
            <p>You'll need the staff password to get back in.</p>
            <div class="actions">
              <button class="btn btn-danger btn-sm" on:click={logout}>Sign out</button>
              <button id="logout-cancel" class="btn btn-ghost btn-sm" on:click={cancelLogout}>Cancel</button>
            </div>
          </div>
        {:else}
          <button id="logout-open" class="btn btn-ghost btn-sm" on:click={openLogoutConfirm}>
            <Icon name="log-out" size={13} />Sign out
          </button>
        {/if}
      </div>
    </aside>

    <main class="content" tabindex="-1">
      {#if !dataLoaded && loadError}
        <div class="card load-error">
          <EmptyState icon="alert" title="We couldn't load the desk data" description={loadError}>
            <button class="btn btn-primary btn-sm" on:click={() => loadStaffData(false).catch(() => {})}>
              <Icon name="refresh" size={13} />Try again
            </button>
          </EmptyState>
        </div>
      {:else if tab === 'dashboard'}
        <div class="topbar">
          <div>
            <h2>Overview</h2>
            <p>Staff-run inventory, incoming claims, and in-person returns — at a glance.</p>
          </div>
          <div class="actions">
            <button class="btn btn-secondary" on:click={() => window.open(eventPublicPath(eventId), '_blank', 'noopener')}>
              <Icon name="external" size={15} />Open public page
            </button>
          </div>
        </div>

        {#if !dataLoaded}
          <div class="stats">
            {#each Array(4) as _}<div class="stat"><Skeleton height="3.4rem" /></div>{/each}
          </div>
        {:else}
          <div class="stats">
            <button class="stat" on:click={() => openTab('intake')}>
              <span class="stat-icon"><Icon name="package" size={16} /></span>
              <strong>{report.items_catalogued ?? items.length}</strong>
              <span>Items logged</span>
            </button>
            <button class="stat" on:click={() => openTab('inbox')}>
              <span class="stat-icon"><Icon name="inbox" size={16} /></span>
              <strong>{report.claims_received ?? claims.length}</strong>
              <span>Claims received</span>
            </button>
            <button class="stat" class:stat-attention={pendingReviewCount > 0} on:click={() => { claimFilter = 'ready'; openTab('inbox'); }}>
              <span class="stat-icon"><Icon name="clock" size={16} /></span>
              <strong>{pendingReviewCount}</strong>
              <span>Ready for review</span>
            </button>
            <button class="stat" on:click={() => openTab('report')}>
              <span class="stat-icon"><Icon name="check" size={16} /></span>
              <strong>{report.returned_items ?? 0}</strong>
              <span>Returned</span>
            </button>
          </div>
        {/if}

        <div class="grid grid-2 dash-grid">
          <section class="card">
            <div class="card-head">
              <h3>Recently logged items</h3>
              <button class="btn btn-link btn-sm" on:click={() => openTab('intake')}>Add items<Icon name="arrow-right" size={13} /></button>
            </div>
            <div class="stack">
              {#if !dataLoaded}
                <Skeleton height="5rem" /><Skeleton height="5rem" />
              {:else}
                {#each items.slice(0, 4) as item (item.item_id)}
                  <div class="item-row">
                    {#if item._photo_src}
                      <img src={item._photo_src} alt={item.caption || 'Item photo'} />
                    {:else}
                      <span class="thumb-fallback"><Icon name="package" size={18} /></span>
                    {/if}
                    <div class="item-info">
                      <p class="item-caption clamp-2">{item.caption || 'No description'}</p>
                      <div class="row wrap">
                        <StatusBadge status={item.status} />
                        {#if privacyNeedsReview(item)}<span class="badge badge-warn"><span class="dot"></span>Privacy check</span>{/if}
                      </div>
                      <p class="meta"><Icon name="pin" size={12} />{item.found_location || 'Location not recorded'}</p>
                    </div>
                  </div>
                {:else}
                  <EmptyState icon="camera" title="No items yet" description="Photograph found items as they come in — one photo per item.">
                    <button class="btn btn-primary btn-sm" on:click={() => openTab('intake')}>Add the first item</button>
                  </EmptyState>
                {/each}
              {/if}
            </div>
          </section>

          <section class="card">
            <div class="card-head">
              <h3>Open claims</h3>
              <button class="btn btn-link btn-sm" on:click={() => openTab('inbox')}>Open inbox<Icon name="arrow-right" size={13} /></button>
            </div>
            <div class="stack">
              {#if !dataLoaded}
                <Skeleton height="4rem" /><Skeleton height="4rem" />
              {:else}
                {#each claims.slice(0, 4) as claim (claim.claim_id)}
                  <button class="list-card" on:click={() => { selectClaim(claim); openTab('inbox'); }}>
                    <span class="clamp-2 claim-summary">{claim.summary || 'No description yet'}</span>
                    <span class="row wrap">
                      <StatusBadge status={claim.status} />
                      {#if claim.claimant_photos?.length}
                        <span class="badge"><Icon name="camera" size={11} />{claim.claimant_photos.length}</span>
                      {/if}
                      <span class="meta trunc">{claim.contact_info || 'No contact yet'}</span>
                    </span>
                  </button>
                {:else}
                  <EmptyState icon="inbox" title="No claims yet" description="Share the public link so owners can report what they lost." />
                {/each}
              {/if}
            </div>
          </section>
        </div>

        <div class="note note-info safety-banner">
          <Icon name="shield" size={16} />
          <span><strong>Private review:</strong> staff compare possible items behind the desk. Owners only see messages from the desk team, and the inventory stays private.</span>
        </div>

      {:else if tab === 'intake'}
        <div class="topbar">
          <div>
            <h2>Add items</h2>
            <p>One item, one photo. A searchable description is written automatically — you can archive items any time.</p>
          </div>
        </div>
        <div class="grid grid-2 intake-grid">
          <section class="card">
            <form on:submit={addItem} novalidate>
              <label for="ph">Item photo<span class="req" aria-hidden="true">*</span></label>
              {#if intakePreview}
                <div class="intake-preview">
                  <img src={intakePreview} alt="Preview of the chosen item" />
                </div>
              {/if}
              <label class="file-btn intake-file">
                <Icon name="camera" size={14} />{intakeFile ? `Change photo (${intakeFile.name})` : 'Choose a photo'}
                <input id="ph" name="photo" type="file" accept="image/*" on:change={pickIntakePhoto} />
              </label>
              {#if intakeError}
                <p class="field-error"><Icon name="error" size={13} />{intakeError}</p>
              {/if}

              <label for="loc">Where was it found?</label>
              <input id="loc" name="found_location" placeholder="e.g. Workshop Room B, Hall A seating" />

              <label for="sn">Staff note <span class="optional">(optional)</span></label>
              <textarea id="sn" name="staff_note" placeholder={'Context only, never ownership guesses — e.g. "under a chair by booth 7".'}></textarea>

              <button type="submit" class="btn btn-primary btn-block intake-submit" disabled={intakeBusy}>
                {#if intakeBusy}<Spinner size={15} />Describing the photo…{:else}<Icon name="sparkles" size={15} />Describe & add to inventory{/if}
              </button>
              {#if intakeBusy}<p class="hint">Writing a searchable photo description — this can take a few seconds.</p>{/if}
            </form>
          </section>

          <section class="card">
            <div class="card-head"><h3>Inventory <span class="count-chip">{items.length}</span></h3></div>
            <div class="stack inventory-list">
              {#if !dataLoaded}
                <Skeleton height="5.5rem" /><Skeleton height="5.5rem" /><Skeleton height="5.5rem" />
              {:else}
              {#each items as item (item.item_id)}
                <div class="item-row">
                  {#if item._photo_src}
                    <img src={item._photo_src} alt={item.caption || 'Item photo'} />
                  {:else}
                    <span class="thumb-fallback"><Icon name="package" size={18} /></span>
                  {/if}
                  <div class="item-info">
                    <p class="item-caption">{item.caption || 'No description'}</p>
                    <div class="row wrap">
                      <StatusBadge status={item.status} />
                      <span class="meta mono">{item.item_id}</span>
                    </div>
                    {#if item.privacy_note}<p class="meta">{item.privacy_note}</p>{/if}
                    {#if item.status === 'archived'}
                      <div class="actions">
                        <button class="btn btn-ghost btn-sm" on:click={() => restoreItem(item.item_id)}>
                          <Icon name="refresh" size={13} />Restore to inventory
                        </button>
                      </div>
                    {:else if archiveFor === item.item_id}
                      <div class="inline-confirm">
                        <p>Archiving removes this item from the inventory and suggested matches. You can restore it later.</p>
                        <div class="actions">
                          <button class="btn btn-danger btn-sm" on:click={() => archiveItem(item.item_id)}>Archive item</button>
                          <button id={`archive-cancel-${item.item_id}`} class="btn btn-ghost btn-sm" on:click={cancelArchive}>Cancel</button>
                        </div>
                      </div>
                    {:else}
                      <div class="actions">
                        <button id={`archive-open-${item.item_id}`} class="btn btn-ghost btn-sm" on:click={() => openArchiveConfirm(item.item_id)}>
                          <Icon name="archive" size={13} />Archive
                        </button>
                      </div>
                    {/if}
                  </div>
                </div>
              {:else}
                <EmptyState icon="package" title="Nothing in the inventory yet" description="Items you add will show up here with clear photo descriptions." />
              {/each}
              {/if}
            </div>
          </section>
        </div>

      {:else if tab === 'inbox'}
        <div class="topbar">
          <div>
            <h2>Claims</h2>
            <p>Review possible items privately, reply to owners, and record returns after confirming in person.</p>
          </div>
        </div>
        <div class="inbox-grid">
          <section class="card">
            <div class="card-head">
              <h3>Reports <span class="count-chip">{visibleClaims.length}</span></h3>
              <button class="btn btn-link btn-sm" on:click={() => loadStaffData(false).catch(() => {})}>
                <Icon name="refresh" size={13} />Refresh
              </button>
            </div>
            <div class="filter-row" role="group" aria-label="Filter claims">
              {#each FILTERS as f}
                <button
                  class="filter-chip"
                  class:active={claimFilter === f.key}
                  aria-pressed={claimFilter === f.key}
                  on:click={() => (claimFilter = f.key)}
                >
                  {f.label}
                  <span class="chip-count">{filterCounts[f.key]}</span>
                </button>
              {/each}
            </div>
            <div class="claim-list">
              {#if !dataLoaded}
                <Skeleton height="4.5rem" /><Skeleton height="4.5rem" /><Skeleton height="4.5rem" />
              {:else}
              {#each visibleClaims as claim (claim.claim_id)}
                <button
                  class="list-card"
                  class:active={selectedClaim?.claim_id === claim.claim_id}
                  on:click={() => selectClaim(claim)}
                >
                  <span class="clamp-2 claim-summary">{claim.summary || 'No description yet'}</span>
                  <span class="row wrap">
                    <StatusBadge status={claim.status} />
                    {#if claim.claimant_photos?.length}
                      <span class="badge"><Icon name="camera" size={11} />{claim.claimant_photos.length}</span>
                    {/if}
                  </span>
                  {#if claim.contact_name || claim.contact_info}
                    <span class="meta trunc">{claim.contact_name || ''} {claim.contact_info || ''}</span>
                  {/if}
                </button>
              {:else}
                <EmptyState
                  icon="inbox"
                  title={claimFilter === 'all' ? 'No claims yet' : 'Nothing matches this filter'}
                  description={claimFilter === 'all'
                    ? 'Share the public link so owners can report what they lost.'
                    : 'Try another filter, or clear it to see every report.'}
                >
                  {#if claimFilter !== 'all'}
                    <button class="btn btn-secondary btn-sm" on:click={() => (claimFilter = 'all')}>Show all claims</button>
                  {/if}
                </EmptyState>
              {/each}
              {/if}
            </div>
          </section>

          <section class="card detail-pane">
            {#if selectedClaim}
              <div class="card-head">
                <h3>Report details <StatusBadge status={selectedClaim.status} /></h3>
                <button class="btn btn-secondary btn-sm" on:click={rematch} disabled={matchingBusy}>
                  {#if matchingBusy}<Spinner size={13} />Checking…{:else}<Icon name="refresh" size={13} />Refresh suggestions{/if}
                </button>
              </div>
              <p class="detail-summary clamp-3">{selectedClaim.summary || 'No description yet'}</p>
              <p class="meta contact-meta">
                <Icon name="user" size={13} />
                {selectedClaim.contact_name || selectedClaim.contact_info
                  ? `${selectedClaim.contact_name || ''} ${selectedClaim.contact_info || ''}`.trim()
                  : 'No contact details yet'}
              </p>

              {#if selectedClaim.claimant_photos?.length}
                <div class="well claimant-photos">
                  <strong>Photos from the owner</strong>
                  {#each selectedClaim.claimant_photos as p (p.photo_id)}
                    <figure class="photo-item">
                      <img src={p.photo_url} alt={p.caption || "Owner's photo"} />
                      <figcaption class="clamp-3">{p.caption}</figcaption>
                    </figure>
                  {/each}
                </div>
              {/if}

              <details class="transcript">
                <summary><Icon name="chevron" size={14} />Conversation transcript</summary>
                <!-- svelte-ignore a11y_no_noninteractive_tabindex — a scrollable region must
                     be focusable so keyboard users can scroll it (WCAG 2.1.1) -->
                <div class="transcript-body" role="region" aria-label="Conversation transcript" tabindex="0">
                  {#each selectedClaim.conversation as m}
                    <div class={`bubble ${m.role}`}>
                      <span class="who">{m.role === 'staff' ? 'Staff' : m.role === 'user' ? 'Owner' : 'Assistant'}</span>{m.content}
                    </div>
                  {/each}
                </div>
              </details>

              <hr class="rule" />
              <div class="card-head">
                <h3>Possible items</h3>
                {#if matchState}<StatusBadge status={matchState} />{/if}
              </div>
              <p class="hint">This list updates as the owner adds details.</p>
              <div class="stack candidates">
                {#each enrichedCandidates as candidate (candidate.item_id)}
                  <div class="candidate-card">
                    {#if candidate.item?._photo_src}
                      <img class="candidate-thumb" src={candidate.item._photo_src} alt={candidate.item?.caption || 'Candidate item'} />
                    {:else}
                      <span class="candidate-thumb thumb-fallback"><Icon name="package" size={20} /></span>
                    {/if}
                    <div class="candidate-info">
                      <p class="item-caption">{candidate.item?.caption || candidate.item_id}</p>
                      <div class="row wrap">
                        <StatusBadge status={candidate.state} />
                        <span class="meta mono">{candidate.item_id}</span>
                      </div>
                      <p class="candidate-line"><strong>Details in common:</strong> {candidate.reason}</p>
                      <p class="candidate-line"><strong>Staff action:</strong> {candidate.staff_next_step}</p>
                      <div class="actions">
                        <button class="btn btn-secondary btn-sm" on:click={() => draftMessage(candidate.item_id)} disabled={draftingFor !== null}>
                          {#if draftingFor === candidate.item_id}<Spinner size={13} />Drafting…{:else}<Icon name="sparkles" size={13} />Draft a reply{/if}
                        </button>
                        <button id={`return-open-${candidate.item_id}`} class="btn btn-ghost btn-sm" on:click={() => openReturnConfirm(candidate.item_id)}>
                          <Icon name="check" size={13} />Mark as returned
                        </button>
                      </div>
                      {#if returnFor === candidate.item_id}
                        <div class="inline-confirm return-confirm">
                          <p>Only record a return after confirming ownership face to face.</p>
                          <label for="return-note">Handoff note</label>
                          <input id="return-note" bind:value={returnNote} />
                          <div class="actions">
                            <button class="btn btn-primary btn-sm" on:click={confirmReturn} disabled={returnBusy}>
                              {#if returnBusy}<Spinner size={13} />Recording…{:else}Record return{/if}
                            </button>
                            <button class="btn btn-ghost btn-sm" on:click={cancelReturn}>Cancel</button>
                          </div>
                        </div>
                      {/if}
                    </div>
                  </div>
                {:else}
                  <EmptyState
                    icon="search"
                    title={matchState === 'needs_more_info' ? 'Waiting on more detail' : 'No matching candidates yet'}
                    description={matchState === 'needs_more_info'
                      ? 'The description is still too vague — possible items appear once the owner adds more.'
                      : 'Nothing in the current inventory fits this description. New items are checked as you add them.'}
                  />
                {/each}
              </div>

              <hr class="rule" />
              <h3 class="reply-title">Reply to the owner</h3>
              <p class="hint">Your message appears on their report page. Use a draft for safe wording, then edit freely.</p>
              {#if draftText}
                <div class="well draft-box">
                  <strong><Icon name="sparkles" size={13} />Suggested draft</strong>
                  <p>{draftText}</p>
                  <div class="actions">
                    <button class="btn btn-secondary btn-sm" on:click={applyDraft}>Use this draft</button>
                    <button class="btn btn-ghost btn-sm" on:click={() => (draftText = '')}>Discard</button>
                  </div>
                </div>
              {/if}
              <textarea
                bind:value={staffMsg}
                aria-label="Reply to the owner"
                placeholder={'e.g. "Please come to the lost & found desk before 5pm today and bring an ID."'}
              ></textarea>
              <div class="actions reply-actions">
                <button class="btn btn-primary" on:click={sendStaffMessage} disabled={staffMsgBusy || !staffMsg.trim()}>
                  {#if staffMsgBusy}<Spinner size={15} />Sending…{:else}<Icon name="send" size={15} />Send to owner{/if}
                </button>
              </div>
            {:else}
              <EmptyState icon="inbox" title="Select a report" description="Pick a report from the list to review its details and possible items." />
            {/if}
          </section>
        </div>

      {:else if tab === 'report'}
        <div class="topbar">
          <div>
            <h2>Closeout report</h2>
            <p>How the desk did — items, claims, returns, and private-review promises kept.</p>
          </div>
          <div class="actions">
            <button class="btn btn-secondary" on:click={() => loadStaffData(false).catch(() => {})}>
              <Icon name="refresh" size={15} />Refresh
            </button>
          </div>
        </div>
        <div class="stats">
          <div class="stat static"><span class="stat-icon"><Icon name="package" size={16} /></span><strong>{report.items_catalogued ?? 0}</strong><span>Items logged</span></div>
          <div class="stat static"><span class="stat-icon"><Icon name="inbox" size={16} /></span><strong>{report.claims_received ?? 0}</strong><span>Claims received</span></div>
          <div class="stat static"><span class="stat-icon"><Icon name="check" size={16} /></span><strong>{report.returned_items ?? 0}</strong><span>Returned</span></div>
          <div class="stat static"><span class="stat-icon"><Icon name="shield" size={16} /></span><strong>{report.auto_ownership_decisions ?? 0}</strong><span>Automatic ownership decisions</span></div>
        </div>

        <div class="dash-grid">
          <section class="card">
            <h3 class="report-h">Return log</h3>
            <div class="stack">
              {#each report.returns || [] as log (log.log_id)}
                <div class="return-row">
                  <p class="mono return-ids">{log.item_id} → {log.claim_id}</p>
                  <p class="meta">{staffLabel(log.handoff_method || '')} · {formatWhen(log.created_at)}</p>
                </div>
              {:else}
                <EmptyState icon="check" title="No returns recorded yet" description="Confirmed handoffs will be logged here." />
              {/each}
            </div>
          </section>
        </div>

        <details class="card dev-details">
          <summary><Icon name="chevron" size={14} />Detailed report data</summary>
          <pre>{JSON.stringify(report, null, 2)}</pre>
        </details>
      {/if}
    </main>
  </div>
{/if}

<style>
  /* ---- Sign-in gate ---- */
  .gate {
    max-width: 1040px;
    margin: 0 auto;
    padding: var(--s-4);
  }

  .gate-card {
    max-width: 26rem;
    margin: var(--s-6) auto;
  }

  .gate-card h2 {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    font-size: var(--text-lg);
    margin-bottom: var(--s-1);
  }

  .gate-card h2 :global(svg) {
    color: var(--ink-3);
  }

  .gate-card .btn {
    margin-top: var(--s-4);
  }

  .gate-checking {
    justify-content: center;
    padding: var(--s-4) 0;
  }

  /* ---- Authed layout ---- */
  .layout {
    display: grid;
    grid-template-columns: 264px minmax(0, 1fr);
    min-height: 100vh;
  }

  .sidebar {
    position: sticky;
    top: 0;
    height: 100vh;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: var(--s-4);
    padding: var(--s-4);
    border-right: 1px solid var(--line);
    background: var(--surface);
  }

  .brand {
    display: flex;
    align-items: center;
    gap: var(--s-3);
    min-width: 0;
  }

  .brand-text {
    min-width: 0;
  }

  .brand h1 {
    font-size: var(--text-base);
    letter-spacing: -0.01em;
  }

  .brand p {
    margin: 0.1rem 0 0;
    color: var(--ink-3);
    font-size: var(--text-xs);
  }

  .nav {
    display: grid;
    gap: 0.25rem;
  }

  .nav button {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    width: 100%;
    text-align: left;
    border: 0;
    border-radius: var(--r-md);
    background: transparent;
    color: var(--ink-2);
    padding: 0.58rem 0.7rem;
    font-weight: 600;
    font-size: var(--text-sm);
    cursor: pointer;
    transition: background-color var(--dur-1) var(--ease-out), color var(--dur-1) var(--ease-out);
  }

  .nav button:hover {
    background: var(--surface-2);
    color: var(--ink);
  }

  .nav button.active {
    background: var(--accent-soft);
    color: var(--accent-on-soft);
    box-shadow: inset 2.5px 0 0 var(--accent);
  }

  .nav-label {
    flex: 1;
  }

  .nav-count {
    display: grid;
    place-items: center;
    min-width: 1.3rem;
    height: 1.3rem;
    padding: 0 0.3rem;
    border-radius: var(--r-pill);
    background: var(--warn-soft);
    color: var(--warn-on-soft);
    border: 1px solid color-mix(in srgb, var(--warn) 35%, transparent);
    font-size: var(--text-xs);
    font-weight: 700;
  }

  .share-box {
    display: grid;
    gap: var(--s-1);
    padding: var(--s-3);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: var(--surface-2);
  }

  .share-box strong {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    font-size: var(--text-sm);
  }

  .share-box strong :global(svg) {
    color: var(--ink-3);
  }

  .share-box .hint {
    margin: 0;
    font-size: var(--text-xs);
  }

  .share-row {
    justify-content: space-between;
    margin-top: var(--s-1);
  }

  .share-row code {
    font-size: var(--text-xs);
  }

  .sidebar-foot {
    margin-top: auto;
    display: grid;
    gap: var(--s-2);
    justify-items: start;
  }

  .sync-row {
    justify-content: space-between;
    width: 100%;
  }

  .sync-note {
    margin: 0;
    color: var(--ink-3);
    font-size: var(--text-xs);
  }

  .safety-note {
    display: flex;
    gap: var(--s-2);
    align-items: flex-start;
    margin: var(--s-2) 0 0;
    color: var(--ink-3);
    font-size: var(--text-xs);
    line-height: 1.5;
  }

  .safety-note :global(svg) {
    flex: none;
    margin-top: 0.12rem;
  }

  .content {
    padding: var(--s-5) clamp(var(--s-4), 4vw, var(--s-7)) var(--s-7);
    min-width: 0;
  }

  .load-error {
    max-width: 36rem;
    margin: var(--s-6) auto;
  }

  .topbar {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: var(--s-4);
    margin-bottom: var(--s-5);
    animation: fade-up var(--dur-3) var(--ease-out);
  }

  .topbar h2 {
    font-size: var(--text-xl);
    letter-spacing: -0.025em;
  }

  .topbar p {
    margin: var(--s-1) 0 0;
    max-width: 46rem;
    color: var(--ink-3);
    font-size: var(--text-sm);
  }

  /* ---- Stats ---- */
  .stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: var(--s-3);
    margin-bottom: var(--s-4);
  }

  .stat {
    display: grid;
    gap: 0.1rem;
    justify-items: start;
    text-align: left;
    padding: var(--s-4);
    border: 1px solid var(--line);
    border-radius: var(--r-lg);
    background: var(--surface);
    font: inherit;
    color: inherit;
    transition: border-color var(--dur-1) var(--ease-out), box-shadow var(--dur-1) var(--ease-out), transform var(--dur-1) var(--ease-out);
  }

  button.stat {
    cursor: pointer;
  }

  button.stat:hover {
    border-color: var(--line-strong);
    box-shadow: var(--shadow-2);
    transform: translateY(-1px);
  }

  .stat-icon {
    display: grid;
    place-items: center;
    width: 1.9rem;
    height: 1.9rem;
    border-radius: var(--r-sm);
    background: var(--surface-2);
    color: var(--ink-2);
    margin-bottom: var(--s-2);
  }

  .stat strong {
    font-size: var(--text-stat);
    letter-spacing: -0.04em;
    font-variant-numeric: tabular-nums;
    line-height: 1.1;
  }

  .stat > span:last-child {
    color: var(--ink-3);
    font-size: var(--text-sm);
  }

  .stat-attention {
    border-color: color-mix(in srgb, var(--warn) 45%, transparent);
  }

  .stat-attention .stat-icon {
    background: var(--warn-soft);
    color: var(--warn-on-soft);
  }

  .dash-grid {
    align-items: start;
    margin-bottom: var(--s-4);
  }

  /* ---- Item rows ---- */
  .item-row {
    display: grid;
    grid-template-columns: 92px minmax(0, 1fr);
    align-items: start;
    gap: var(--s-3);
  }

  .item-row img,
  .thumb-fallback {
    width: 92px;
    aspect-ratio: 1;
    object-fit: cover;
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: var(--surface-2);
  }

  .thumb-fallback {
    display: grid;
    place-items: center;
    color: var(--ink-3);
  }

  .item-info {
    display: grid;
    gap: 0.3rem;
    justify-items: start;
  }

  .item-caption {
    font-weight: 600;
    line-height: 1.4;
    font-size: var(--text-sm);
  }

  .meta :global(svg) {
    vertical-align: -0.12em;
    margin-right: 0.25rem;
  }

  .wrap {
    flex-wrap: wrap;
  }

  .count-chip {
    display: inline-grid;
    place-items: center;
    min-width: 1.4rem;
    padding: 0.05rem 0.4rem;
    border-radius: var(--r-pill);
    background: var(--surface-2);
    border: 1px solid var(--line);
    color: var(--ink-3);
    font-size: var(--text-xs);
    font-weight: 650;
  }

  .safety-banner {
    margin-top: var(--s-2);
  }

  /* ---- Intake ---- */
  .intake-grid {
    align-items: start;
  }

  .intake-preview img {
    width: 100%;
    max-height: 260px;
    object-fit: cover;
    border-radius: var(--r-md);
    border: 1px solid var(--line);
    margin-bottom: var(--s-2);
    animation: fade-up var(--dur-2) var(--ease-out);
  }

  .intake-file {
    width: 100%;
    justify-content: center;
    padding: var(--s-3);
  }

  .intake-submit {
    margin-top: var(--s-4);
  }

  .optional {
    font-weight: 400;
    color: var(--ink-3);
  }

  .inventory-list {
    max-height: 70vh;
    overflow-y: auto;
    padding-right: var(--s-1);
  }

  /* ---- Inbox ---- */
  .inbox-grid {
    display: grid;
    grid-template-columns: minmax(0, 21rem) minmax(0, 1fr);
    gap: var(--s-4);
    align-items: start;
  }

  .filter-row {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    margin-bottom: var(--s-3);
  }

  .filter-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    border: 1px solid var(--line);
    border-radius: var(--r-pill);
    background: var(--surface);
    color: var(--ink-2);
    font-size: var(--text-xs);
    font-weight: 600;
    padding: 0.28rem 0.62rem;
    cursor: pointer;
    transition: background-color var(--dur-1) var(--ease-out), border-color var(--dur-1) var(--ease-out), color var(--dur-1) var(--ease-out);
  }

  .filter-chip:hover {
    border-color: var(--line-strong);
    color: var(--ink);
  }

  .filter-chip.active {
    background: var(--accent-soft);
    border-color: var(--accent);
    color: var(--accent-on-soft);
  }

  .chip-count {
    /* Full-opacity muted ink: stays AA (≥4.5:1) at this 12px size. */
    color: var(--ink-3);
    font-variant-numeric: tabular-nums;
  }

  .filter-chip.active .chip-count {
    color: inherit;
  }

  .claim-list {
    display: grid;
    gap: var(--s-2);
    max-height: 64vh;
    overflow-y: auto;
    padding-right: var(--s-1);
  }

  .claim-summary {
    font-weight: 600;
    line-height: 1.4;
    font-size: var(--text-sm);
  }

  .detail-pane {
    min-width: 0;
  }

  .detail-summary {
    color: var(--ink-2);
    line-height: 1.55;
    margin-bottom: var(--s-2);
  }

  .contact-meta {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }

  .claimant-photos {
    margin-top: var(--s-3);
    display: grid;
    gap: var(--s-2);
  }

  .claimant-photos strong {
    font-size: var(--text-sm);
  }

  .photo-item {
    display: flex;
    gap: var(--s-3);
    align-items: flex-start;
    margin: 0;
  }

  .photo-item img {
    width: 92px;
    height: 92px;
    flex: none;
    object-fit: cover;
    border-radius: var(--r-md);
    border: 1px solid var(--line);
  }

  .photo-item figcaption {
    font-size: var(--text-sm);
    color: var(--ink-3);
    line-height: 1.5;
    min-width: 0;
  }

  .transcript {
    margin-top: var(--s-4);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: var(--surface);
  }

  .transcript summary {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    padding: var(--s-3) var(--s-4);
    cursor: pointer;
    font-weight: 600;
    font-size: var(--text-sm);
    color: var(--ink-2);
    list-style: none;
    border-radius: var(--r-md);
  }

  .transcript summary::-webkit-details-marker {
    display: none;
  }

  .transcript summary :global(svg) {
    transition: transform var(--dur-2) var(--ease-out);
  }

  .transcript[open] summary :global(svg) {
    transform: rotate(180deg);
  }

  .transcript-body {
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
    padding: 0 var(--s-4) var(--s-4);
    max-height: 20rem;
    overflow-y: auto;
  }

  .candidates {
    margin-top: var(--s-2);
  }

  .candidate-card {
    display: flex;
    gap: var(--s-4);
    align-items: flex-start;
    padding: var(--s-4);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: var(--surface);
    animation: fade-up var(--dur-3) var(--ease-out);
  }

  .candidate-thumb {
    width: 116px;
    height: 116px;
    flex: none;
    object-fit: cover;
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: var(--surface-2);
  }

  .candidate-info {
    min-width: 0;
    display: grid;
    gap: 0.35rem;
    justify-items: start;
  }

  .candidate-line {
    font-size: var(--text-sm);
    color: var(--ink-2);
    line-height: 1.5;
  }

  .return-confirm {
    border-color: color-mix(in srgb, var(--ok) 35%, transparent);
    background: var(--ok-soft);
    width: 100%;
  }

  .return-confirm p {
    color: var(--ok-on-soft);
  }

  .return-confirm label {
    margin-top: var(--s-2);
  }

  .reply-title {
    font-size: var(--text-md);
  }

  .draft-box {
    display: grid;
    gap: var(--s-2);
    justify-items: start;
    margin: var(--s-3) 0;
    animation: fade-up var(--dur-2) var(--ease-out);
  }

  .draft-box strong {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: var(--text-sm);
    color: var(--ink-2);
  }

  .draft-box p {
    color: var(--ink-2);
    font-size: var(--text-sm);
    line-height: 1.55;
  }

  .detail-pane textarea {
    margin-top: var(--s-3);
  }

  .reply-actions {
    margin-top: var(--s-3);
  }

  /* ---- Report ---- */
  .report-h {
    margin-bottom: var(--s-2);
  }

  .return-row {
    display: grid;
    gap: 0.2rem;
    padding: var(--s-3);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
  }

  .return-ids {
    font-size: var(--text-sm);
  }

  .dev-details {
    margin-top: var(--s-4);
  }

  .dev-details summary {
    display: flex;
    align-items: center;
    gap: var(--s-2);
    cursor: pointer;
    font-weight: 600;
    font-size: var(--text-sm);
    color: var(--ink-3);
    list-style: none;
  }

  .dev-details summary::-webkit-details-marker {
    display: none;
  }

  .dev-details summary :global(svg) {
    transition: transform var(--dur-2) var(--ease-out);
  }

  .dev-details[open] summary :global(svg) {
    transform: rotate(180deg);
  }

  .dev-details pre {
    margin-top: var(--s-3);
  }

  /* ---- Responsive ---- */
  @media (max-width: 960px) {
    .layout {
      grid-template-columns: 1fr;
    }

    .sidebar {
      position: static;
      height: auto;
      border-right: 0;
      border-bottom: 1px solid var(--line);
    }

    .nav {
      display: flex;
      overflow-x: auto;
      gap: var(--s-1);
      padding-bottom: var(--s-1);
    }

    .nav button {
      width: auto;
      white-space: nowrap;
    }

    .sidebar-foot {
      margin-top: 0;
    }

    /* Keep the mobile header compact: the data should appear within the first
       screen, so secondary guidance collapses to its essentials. */
    .share-box .hint,
    .safety-note,
    .sync-note {
      display: none;
    }

    .sidebar {
      gap: var(--s-3);
    }

    .stats {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .grid-2,
    .inbox-grid {
      grid-template-columns: 1fr;
    }

    .topbar {
      flex-direction: column;
      align-items: flex-start;
    }

    .claim-list,
    .inventory-list {
      max-height: 40vh;
    }
  }

  @media (max-width: 560px) {
    .stats {
      grid-template-columns: 1fr;
    }

    /* All four tabs stay visible — a horizontal scroller hides the last one. */
    .nav {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      overflow-x: visible;
    }

    .candidate-card {
      flex-direction: column;
    }

    .candidate-thumb {
      width: 100%;
      height: 160px;
    }
  }
</style>
