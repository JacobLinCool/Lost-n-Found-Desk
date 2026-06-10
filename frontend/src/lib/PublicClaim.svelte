<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { api, absoluteUrl, ApiError } from '../api';
  import { gradioClaimChat, gradioClaimAddPhoto } from '../gradioApi';
  import { navigate, claimPath, eventPublicPath } from '../router';
  import type {
    ChatMessage,
    Claim,
    ClaimChatResponse,
    ClaimPhotoResponse,
    ClaimResponse,
    EventPublic,
    PublicConfig,
    SubmitResponse,
  } from '../types';
  import Icon from './ui/Icon.svelte';
  import Logo from './ui/Logo.svelte';
  import Spinner from './ui/Spinner.svelte';
  import Skeleton from './ui/Skeleton.svelte';
  import Stepper from './ui/Stepper.svelte';
  import StatusBadge from './ui/StatusBadge.svelte';
  import CopyButton from './ui/CopyButton.svelte';
  import EmptyState from './ui/EmptyState.svelte';
  import ThemeToggle from './ui/ThemeToggle.svelte';

  export let eventId: string;
  export let claimId: string | null = null;
  export let config: PublicConfig = { app_name: 'Lost & Found Desk', prefer_gradio_client_for_models: false };

  let event: EventPublic | null = null;
  let eventError = '';
  let eventErrorTitle = '';
  let loading = true;

  let claim: Claim | null = null;
  let draft = '';
  let thinking = false;
  let photoBusy = false;
  let starting = false;
  let submitting = false;
  let refreshing = false;
  let editingContact = false;
  let error = '';
  let contactError = '';
  let submittedMessage = '';
  let resumeInput = '';
  let storedClaims: { claim_id: string; summary: string; status: string }[] = [];
  let seenStaffCount = 0;

  // "New staff message" is computed client-side by diffing how many staff
  // messages we've acknowledged against how many are in the conversation, so a
  // background poll never has to mutate server state to drive the banner.
  $: staffMsgCount = claim ? claim.conversation.filter((m) => m.role === 'staff').length : 0;
  $: hasNewStaff = staffMsgCount > seenStaffCount;

  // Merge messages and uploaded photos into one chronological timeline so an
  // uploaded photo appears in order (right before the assistant's reply about
  // it), not lumped together at the bottom.
  type TimelineItem =
    | { kind: 'message'; role: ChatMessage['role']; content: string; at: string }
    | { kind: 'photo'; url: string; at: string };
  $: timeline = (
    claim
      ? [
          ...claim.conversation.map(
            (m): TimelineItem => ({ kind: 'message', role: m.role, content: m.content, at: m.created_at || '' }),
          ),
          ...claim.claimant_photos.map(
            (p): TimelineItem => ({ kind: 'photo', url: p.photo_url, at: p.created_at || '' }),
          ),
        ].sort((a, b) => (a.at < b.at ? -1 : a.at > b.at ? 1 : 0))
      : []
  ) as TimelineItem[];

  // Where this report is in its lifecycle, for the progress stepper.
  const STEPS = ['Describe', 'Contact', 'Review', 'Pickup'];
  $: stepCurrent = !claim
    ? 0
    : claim.status === 'closed'
      ? 3
      : ['needs_more_info', 'ready_for_staff_review', 'matched'].includes(claim.status)
        ? 2
        : claim.readiness_state === 'ready_for_staff_review'
          ? 1
          : 0;
  $: stepDone = claim?.status === 'closed';

  function dismissStaff(): void {
    seenStaffCount = staffMsgCount;
    if (claimId) localStorage.setItem(`lfd_seen_staff_${claimId}`, String(seenStaffCount));
  }

  let chatBox: HTMLDivElement | null = null;
  let pollTimer: ReturnType<typeof setInterval> | undefined;

  const claimsKey = `lfd_claims_${eventId}`;

  function msg(e: unknown): string {
    return e instanceof Error ? e.message : String(e);
  }

  // --- local persistence so claimants can find their reports again (recognition
  // over recall): we remember claim ids + a short summary on this device. ---
  function loadLocalClaims(): { claim_id: string; summary: string; status: string }[] {
    try {
      return JSON.parse(localStorage.getItem(claimsKey) || '[]');
    } catch (_) {
      return [];
    }
  }
  function rememberClaim(c: Claim): void {
    const list = loadLocalClaims().filter((x) => x.claim_id !== c.claim_id);
    list.unshift({ claim_id: c.claim_id, summary: c.summary || '', status: c.status });
    localStorage.setItem(claimsKey, JSON.stringify(list.slice(0, 12)));
  }
  function extractClaimId(input: string): string {
    const m = input.match(/\/c\/([^/?#\s]+)/);
    return (m ? m[1] : input).trim();
  }

  $: contactLocked = !!claim && !!claim.contact_info && ['matched', 'closed'].includes(claim.status) && !editingContact;

  // The contact form binds local fields seeded once from the claim, so the
  // 20s background poll can never clobber text the claimant is still typing.
  let contactName = '';
  let contactInfo = '';
  let contactSeeded = false;
  $: if (claim && !contactSeeded) {
    contactName = claim.contact_name || '';
    contactInfo = claim.contact_info || '';
    contactSeeded = true;
  }

  function cancelContactEdit(): void {
    editingContact = false;
    contactError = '';
    contactName = claim?.contact_name || '';
    contactInfo = claim?.contact_info || '';
  }

  async function loadEvent(): Promise<void> {
    eventError = '';
    try {
      event = await api<EventPublic>(`/api/events/${eventId}`);
    } catch (e) {
      // A missing desk and a network blip need different advice.
      if (e instanceof ApiError && e.status === 404) {
        eventErrorTitle = "We couldn't find this desk";
        eventError = 'The link or desk code may be wrong — check it with the event organizers.';
      } else {
        eventErrorTitle = "We couldn't load this desk";
        eventError = msg(e);
      }
    }
  }

  async function loadClaim(silent = false): Promise<void> {
    if (!claimId) return;
    try {
      const res = await api<ClaimResponse>(`/api/events/${eventId}/claims/${claimId}`);
      claim = res.claim;
      rememberClaim(res.claim);
      if (!silent) scrollChat();
    } catch (_) {
      if (!silent)
        error =
          "We couldn't find this report — the link may be incomplete. Use the link you saved earlier, or start a new report.";
    }
  }

  function scrollChat(): void {
    // Honor reduced motion: an explicit 'smooth' would override the CSS guard.
    const behavior = window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
    setTimeout(() => chatBox?.scrollTo({ top: chatBox.scrollHeight, behavior }), 30);
  }

  async function startClaim(): Promise<void> {
    starting = true;
    error = '';
    try {
      const res = await api<ClaimResponse>(`/api/events/${eventId}/claims`, { method: 'POST' });
      rememberClaim(res.claim);
      navigate(claimPath(eventId, res.claim.claim_id));
    } catch (e) {
      error = msg(e);
      starting = false;
    }
  }

  function resumeClaim(event_: SubmitEvent): void {
    event_.preventDefault();
    const id = extractClaimId(resumeInput);
    if (id) navigate(claimPath(eventId, id));
  }

  async function send(event_: SubmitEvent): Promise<void> {
    event_.preventDefault();
    const text = draft.trim();
    if (!text || !claim || thinking) return;
    draft = '';
    error = '';
    // Optimistic echo so the claimant immediately sees their own message
    // (timestamped so it stays at the bottom of the merged timeline). Keep the
    // pre-send conversation so a failed send can be rolled back cleanly.
    const beforeSend = claim.conversation;
    claim = {
      ...claim,
      conversation: [...beforeSend, { role: 'user', content: text, created_at: new Date().toISOString() }],
    };
    thinking = true;
    scrollChat();
    try {
      const res = config.prefer_gradio_client_for_models
        ? ((await gradioClaimChat(eventId, claim.claim_id, text)) as ClaimChatResponse)
        : await api<ClaimChatResponse>(`/api/events/${eventId}/claims/${claim.claim_id}/chat`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ message: text }),
          });
      claim = res.claim;
      rememberClaim(res.claim);
      scrollChat();
    } catch (e) {
      // Roll back the optimistic bubble and hand the text back, so nothing the
      // claimant typed is ever lost and no message looks sent when it wasn't.
      if (claim) claim = { ...claim, conversation: beforeSend };
      draft = text;
      error = `Your message wasn't sent. ${msg(e)}`;
    } finally {
      thinking = false;
    }
  }

  async function uploadPhoto(event_: Event): Promise<void> {
    const input = event_.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !claim) return;
    photoBusy = true;
    error = '';
    try {
      let res: ClaimPhotoResponse;
      if (config.prefer_gradio_client_for_models) {
        res = (await gradioClaimAddPhoto(eventId, claim.claim_id, file)) as ClaimPhotoResponse;
      } else {
        const fd = new FormData();
        fd.append('photo', file);
        res = await api<ClaimPhotoResponse>(`/api/events/${eventId}/claims/${claim.claim_id}/photo`, {
          method: 'POST',
          body: fd,
        });
      }
      claim = res.claim;
      rememberClaim(res.claim);
      scrollChat();
    } catch (e) {
      error = msg(e);
    } finally {
      photoBusy = false;
      input.value = '';
    }
  }

  async function submit(event_: SubmitEvent): Promise<void> {
    event_.preventDefault();
    if (!claim) return;
    if (!contactInfo.trim()) {
      contactError = 'Leave at least one way to reach you — an email or phone number.';
      document.getElementById('cinfo')?.focus();
      return;
    }
    submitting = true;
    error = '';
    contactError = '';
    try {
      const res = await api<SubmitResponse>(`/api/events/${eventId}/claims/${claim.claim_id}/submit`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ contact_name: contactName.trim(), contact_info: contactInfo.trim() }),
      });
      claim = res.claim;
      rememberClaim(res.claim);
      submittedMessage = res.message;
      editingContact = false;
    } catch (e) {
      contactError = msg(e);
    } finally {
      submitting = false;
    }
  }

  async function refresh(): Promise<void> {
    refreshing = true;
    await loadClaim();
    refreshing = false;
  }

  async function silentPoll(): Promise<void> {
    if (!claim || thinking || photoBusy || submitting || document.hidden) return;
    await loadClaim(true);
  }

  async function retryEvent(): Promise<void> {
    loading = true;
    await loadEvent();
    if (event) await loadClaim();
    loading = false;
  }

  onMount(async () => {
    loading = true;
    storedClaims = loadLocalClaims();
    if (claimId) seenStaffCount = Number(localStorage.getItem(`lfd_seen_staff_${claimId}`) || 0);
    await loadEvent();
    if (event) await loadClaim();
    loading = false;
    // Pick up staff replies without a manual refresh while a claim is open.
    if (claimId) pollTimer = setInterval(silentPoll, 20000);
  });

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer);
  });
</script>

<div class="public">
  <header class="page-bar">
    <a
      class="back-link"
      href="/"
      on:click={(e) => {
        e.preventDefault();
        navigate('/');
      }}
    >
      <Logo />
      <span class="back-text">
        <span class="brand-name">{config.app_name}</span>
        {#if event}<span class="event-meta">{event.name} · desk code <code>{event.event_id}</code></span>{/if}
      </span>
    </a>
    <ThemeToggle />
  </header>

  <main tabindex="-1">
  {#if loading}
    <div class="grid load-grid" aria-hidden="true">
      <div class="card"><Skeleton lines={4} /></div>
      <div class="card"><Skeleton lines={3} /></div>
    </div>
    <p class="sr-only" role="status">Loading the desk…</p>
  {:else if eventError}
    <div class="card center-card">
      <EmptyState icon="search" title={eventErrorTitle} description={eventError}>
        <span class="actions">
          <button class="btn btn-secondary btn-sm" on:click={retryEvent}><Icon name="refresh" size={13} />Try again</button>
          <button class="btn btn-primary btn-sm" on:click={() => navigate('/')}>Go to the home page</button>
        </span>
      </EmptyState>
    </div>
  {:else if !claimId}
    <!-- Landing: start a new claim or resume an existing one -->
    <div class="card center-card landing">
      <span class="landing-icon"><Icon name="message" size={22} /></span>
      <h2>Report a lost item</h2>
      <p class="muted">
        Describe what you lost in a short chat. The desk team reviews possible items privately
        and replies to you right here.
      </p>
      {#if error}<div class="note note-danger" role="alert"><Icon name="error" size={16} />{error}</div>{/if}
      <button class="btn btn-primary btn-block" on:click={startClaim} disabled={starting}>
        {#if starting}<Spinner size={15} />Opening your report…{:else}Start a report<Icon name="arrow-right" size={15} />{/if}
      </button>

      {#if storedClaims.length}
        <hr class="rule" />
        <h3 class="section-title">Your reports on this device</h3>
        <div class="prev-list">
          {#each storedClaims as sc}
            <button class="list-card" on:click={() => navigate(claimPath(eventId, sc.claim_id))}>
              <span class="clamp-2 prev-summary">{sc.summary || 'No description yet'}</span>
              <span class="row"><StatusBadge status={sc.status} audience="claimant" /></span>
            </button>
          {/each}
        </div>
      {/if}

      <hr class="rule" />
      <form on:submit={resumeClaim} class="resume-form">
        <label for="resume">Reported from another device? Paste your saved report link</label>
        <div class="row">
          <input id="resume" bind:value={resumeInput} placeholder={`…/e/${eventId}/c/your-report-id`} />
          <button type="submit" class="btn btn-secondary" disabled={!resumeInput.trim()}>Resume</button>
        </div>
      </form>
    </div>
  {:else if claim}
    <!-- Active claim: conversation + status/submit -->
    <div class="public-grid">
      <section class="card chat-card">
        <div class="card-head">
          <h3><Icon name="message" size={18} />Describe your item</h3>
          <button class="btn btn-link btn-sm" on:click={refresh} disabled={refreshing}>
            {#if refreshing}<Spinner size={13} />Checking…{:else}<Icon name="refresh" size={13} />Check for updates{/if}
          </button>
        </div>

        {#if hasNewStaff}
          <div class="note note-warn staff-banner" role="status">
            <Icon name="alert" size={16} />
            <span class="grow">The desk team sent you a message — see the conversation below.</span>
            <button class="btn btn-link btn-sm" on:click={dismissStaff}>Got it</button>
          </div>
        {/if}

        <!-- svelte-ignore a11y_no_noninteractive_tabindex — a scrollable log must be
             focusable so keyboard users can scroll it (WCAG 2.1.1) -->
        <div class="chat" bind:this={chatBox} role="log" aria-label="Conversation with the desk assistant" tabindex="0">
          {#each timeline as item}
            {#if item.kind === 'photo'}
              <div class="bubble user photo-bubble"><img src={item.url} alt="Your lost item, as you uploaded it" /></div>
            {:else if item.role === 'staff'}
              <div class="bubble staff"><span class="who">Desk team</span>{item.content}</div>
            {:else if item.role === 'user'}
              <div class="bubble user">{item.content}</div>
            {:else}
              <div class="bubble assistant"><span class="who">Assistant</span>{item.content}</div>
            {/if}
          {/each}
          {#if thinking}
            <div class="bubble assistant">
              <span class="typing-dots" aria-hidden="true"><i></i><i></i><i></i></span>
              <span class="sr-only">The assistant is typing…</span>
            </div>
          {/if}
        </div>

        {#if error}<div class="note note-danger" role="alert"><Icon name="error" size={16} />{error}</div>{/if}

        <form class="chat-form" on:submit={send}>
          <input
            bind:value={draft}
            aria-label="Describe your lost item"
            placeholder="e.g. I lost a black water bottle…"
            disabled={thinking}
          />
          <button type="submit" class="btn btn-primary btn-icon" disabled={thinking || !draft.trim()} aria-label="Send message">
            <Icon name="send" size={16} />
          </button>
        </form>

        <div class="photo-row">
          <label class="file-btn">
            {#if photoBusy}<Spinner size={14} />Reading your photo…{:else}<Icon name="camera" size={14} />Add a photo of your item{/if}
            <input type="file" accept="image/*" aria-label="Upload a photo of your lost item" on:change={uploadPhoto} disabled={photoBusy} />
          </label>
          <span class="hint">Optional — a photo of your own item helps the desk team compare details.</span>
        </div>
      </section>

      <section class="side">
        <div class="card">
          <div class="card-head">
            <h3>Report status</h3>
            <StatusBadge status={claim.status} audience="claimant" />
          </div>
          <Stepper steps={STEPS} current={stepCurrent} done={stepDone} />
          <div class="summary-box">
            <p class="summary-text">{claim.summary || 'No description yet — it builds as you chat.'}</p>
            {#if claim.status === 'draft' && claim.readiness_state === 'ready_for_staff_review'}
              <p class="ready-note"><Icon name="check" size={14} />That's enough detail — add your contact info below and submit.</p>
            {/if}
            {#if claim.missing_info.length}
              <div class="row wrap">
                {#each claim.missing_info as info}
                  <span class="badge badge-warn"><span class="dot"></span>Add: {info}</span>
                {/each}
              </div>
            {/if}
          </div>
        </div>

        <div class="card save-card">
          <h3 class="section-title"><Icon name="link" size={15} />Save your report link</h3>
          <p class="hint">
            It's the only way to check replies from another device — we also remember it on this one.
            Treat it like a ticket stub: don't share it publicly.
          </p>
          <div class="row link-row">
            <code class="trunc">{absoluteUrl(claimPath(eventId, claim.claim_id))}</code>
            <CopyButton text={absoluteUrl(claimPath(eventId, claim.claim_id))} />
          </div>
        </div>

        <div class="card">
          {#if submittedMessage}
            <div class="note note-ok" role="status" aria-live="polite"><Icon name="check" size={16} />{submittedMessage}</div>
          {/if}

          {#if contactLocked}
            <h3 class="section-title">Your contact details</h3>
            <p class="contact-line">{claim.contact_name ? `${claim.contact_name} · ` : ''}{claim.contact_info}</p>
            <button class="btn btn-secondary btn-sm" on:click={() => (editingContact = true)}>Update contact details</button>
          {:else}
            <h3 class="section-title">Where can we reach you?</h3>
            <form on:submit={submit} novalidate>
              <label for="cname">Name <span class="optional">(as registered, optional)</span></label>
              <input id="cname" name="contact_name" bind:value={contactName} placeholder="The name you used at the event" />
              <label for="cinfo">Email or phone<span class="req" aria-hidden="true">*</span></label>
              <input
                id="cinfo"
                name="contact_info"
                bind:value={contactInfo}
                placeholder="So the desk team can reach you"
                aria-invalid={contactError ? 'true' : undefined}
                aria-describedby={contactError ? 'cinfo-error' : undefined}
                on:input={() => (contactError = '')}
              />
              {#if contactError}
                <p class="field-error" id="cinfo-error"><Icon name="error" size={13} />{contactError}</p>
              {/if}
              <div class="row submit-row">
                <button type="submit" class="btn btn-primary submit-btn" disabled={submitting}>
                  {#if submitting}<Spinner size={15} />Submitting…{:else}Submit to the desk team{/if}
                </button>
                {#if editingContact}
                  <button type="button" class="btn btn-ghost submit-btn" on:click={cancelContactEdit}>Cancel</button>
                {/if}
              </div>
            </form>
          {/if}
          <p class="trust-note">
            <Icon name="shield" size={14} />
            <span>The desk team reviews possible items privately and replies here.</span>
          </p>
        </div>
      </section>
    </div>
  {:else}
    <div class="card center-card">
      <EmptyState
        icon="search"
        title="We couldn't find this report"
        description={error || 'The link may be incomplete. Use the link you saved earlier, or start a new report.'}
      >
        <button class="btn btn-primary btn-sm" on:click={() => navigate(eventPublicPath(eventId))}>Back to the desk</button>
      </EmptyState>
    </div>
  {/if}
  </main>
</div>

<style>
  .public {
    max-width: 1040px;
    margin: 0 auto;
    padding: var(--s-4) var(--s-4) var(--s-7);
  }

  .back-text {
    display: grid;
    min-width: 0;
  }

  .event-meta {
    color: var(--ink-3);
    font-size: var(--text-xs);
  }

  .load-grid {
    grid-template-columns: 1.5fr 1fr;
    align-items: start;
  }

  .center-card {
    max-width: 34rem;
    margin: var(--s-6) auto;
  }

  .landing {
    display: grid;
    gap: var(--s-3);
    animation: fade-up var(--dur-3) var(--ease-out);
  }

  .landing-icon {
    display: grid;
    place-items: center;
    width: 2.8rem;
    height: 2.8rem;
    border-radius: var(--r-md);
    background: var(--accent-soft);
    color: var(--accent-on-soft);
  }

  .landing h2 {
    font-size: var(--text-xl);
  }

  .landing > .muted {
    line-height: 1.6;
  }

  .prev-list {
    display: grid;
    gap: var(--s-2);
  }

  .prev-summary {
    font-weight: 600;
    line-height: 1.4;
  }

  .resume-form label {
    margin-top: 0;
  }

  .resume-form .row {
    margin-top: var(--s-1);
    align-items: stretch;
  }

  .resume-form .btn {
    white-space: nowrap;
  }

  /* Active claim layout */
  .public-grid {
    display: grid;
    grid-template-columns: minmax(0, 1.5fr) minmax(0, 1fr);
    gap: var(--s-4);
    align-items: start;
  }

  .side {
    display: grid;
    /* minmax(0, …): never let a long report URL set the column's min width */
    grid-template-columns: minmax(0, 1fr);
    gap: var(--s-4);
  }

  .chat-card {
    display: flex;
    flex-direction: column;
  }

  .staff-banner {
    margin-bottom: var(--s-3);
    align-items: center;
  }

  .grow {
    flex: 1;
  }

  .chat {
    display: flex;
    flex-direction: column;
    gap: var(--s-2);
    height: min(56vh, 34rem);
    overflow-y: auto;
    padding: var(--s-1);
  }

  .chat-form {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: var(--s-2);
    margin-top: var(--s-3);
  }

  .chat-card .note {
    margin-top: var(--s-3);
  }

  .photo-row {
    display: flex;
    align-items: center;
    gap: var(--s-3);
    margin-top: var(--s-3);
    flex-wrap: wrap;
  }

  .photo-row .hint {
    flex: 1;
    min-width: 12rem;
    margin: 0;
  }

  /* Status card */
  .summary-box {
    margin-top: var(--s-4);
    padding: var(--s-4);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    background: var(--surface-2);
    display: grid;
    gap: var(--s-2);
  }

  .summary-text {
    line-height: 1.55;
    color: var(--ink-2);
    font-size: var(--text-sm);
  }

  .ready-note {
    display: flex;
    align-items: flex-start;
    gap: var(--s-1);
    color: var(--ok-on-soft);
    font-size: var(--text-sm);
    font-weight: 600;
    margin: 0;
  }

  .ready-note :global(svg) {
    flex: none;
    margin-top: 0.18rem;
    color: var(--ok);
  }

  .save-card .link-row {
    margin-top: var(--s-2);
    padding: var(--s-2) var(--s-3);
    background: var(--surface-2);
    border: 1px solid var(--line);
    border-radius: var(--r-md);
    justify-content: space-between;
  }

  .contact-line {
    color: var(--ink-2);
    margin-bottom: var(--s-3);
  }

  .submit-row {
    margin-top: var(--s-4);
  }

  .submit-row .submit-btn[type='submit'] {
    flex: 1;
  }

  .trust-note {
    display: flex;
    gap: var(--s-2);
    align-items: flex-start;
    margin-top: var(--s-4);
    color: var(--ink-3);
    font-size: var(--text-xs);
    line-height: 1.55;
  }

  .trust-note :global(svg) {
    flex: none;
    margin-top: 0.14rem;
  }

  @media (max-width: 880px) {
    .public-grid,
    .load-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .chat {
      height: min(48vh, 26rem);
    }
  }
</style>
