<script lang="ts">
    import { onMount } from "svelte";
    import { api, absoluteUrl, staffHeaders, ApiError } from "../api";
    import { navigate, staffPath, eventPublicPath } from "../router";
    import type { CreatedEvent, EventPublic, PublicConfig } from "../types";
    import Icon from "./ui/Icon.svelte";
    import Logo from "./ui/Logo.svelte";
    import Spinner from "./ui/Spinner.svelte";
    import CopyButton from "./ui/CopyButton.svelte";
    import ThemeToggle from "./ui/ThemeToggle.svelte";

    export let config: PublicConfig = { app_name: "Lost & Found Desk", prefer_gradio_client_for_models: false };

    let name = "";
    let customId = "";
    let creating = false;
    let createError = "";
    let nameError = "";
    let created: CreatedEvent | null = null;

    let staffCode = "";
    let staffPw = "";
    let staffBusy = false;
    let staffError = "";
    let myEvents: { event_id: string; name: string }[] = [];

    // Prefill the stored password as soon as the staffer types a known code, so
    // they never retype the once-shown random password on this device.
    $: if (staffCode.trim() && !staffPw) {
        const stored = localStorage.getItem(`lfd_staff_pw_${staffCode.trim().toLowerCase()}`);
        if (stored) staffPw = stored;
    }

    onMount(async () => {
        const ids = Object.keys(localStorage)
            .filter((k) => k.startsWith("lfd_staff_pw_"))
            .map((k) => k.slice("lfd_staff_pw_".length));
        myEvents = await Promise.all(
            ids.map(async (id) => {
                try {
                    const e = await api<EventPublic>(`/api/events/${id}`);
                    return { event_id: id, name: e.name };
                } catch (_) {
                    return { event_id: id, name: id };
                }
            }),
        );
    });

    let claimCode = "";
    let claimBusy = false;
    let claimError = "";

    function msg(e: unknown): string {
        return e instanceof Error ? e.message : String(e);
    }

    async function createEvent(event: SubmitEvent): Promise<void> {
        event.preventDefault();
        if (!name.trim()) {
            nameError = "Give your event a name first.";
            (document.getElementById("ev-name") as HTMLInputElement | null)?.focus();
            return;
        }
        creating = true;
        createError = "";
        nameError = "";
        try {
            created = await api<CreatedEvent>("/api/events", {
                method: "POST",
                headers: { "content-type": "application/json" },
                body: JSON.stringify({ name: name.trim(), event_id: customId.trim() }),
            });
            // Remember the password so entering the console later is frictionless.
            localStorage.setItem(`lfd_staff_pw_${created.event_id}`, created.staff_password);
        } catch (e) {
            createError = msg(e);
        } finally {
            creating = false;
        }
    }

    async function staffAccess(event: SubmitEvent): Promise<void> {
        event.preventDefault();
        const code = staffCode.trim().toLowerCase();
        if (!code || !staffPw) {
            staffError = "Enter both the desk code and the staff password.";
            return;
        }
        staffBusy = true;
        staffError = "";
        try {
            await api(`/api/events/${code}/staff/verify`, { method: "POST", headers: staffHeaders(staffPw) });
            localStorage.setItem(`lfd_staff_pw_${code}`, staffPw);
            navigate(staffPath(code));
        } catch (e) {
            // Only blame the credentials when the server actually rejected them.
            staffError =
                e instanceof ApiError && (e.status === 401 || e.status === 404) ? "That desk code and password don't match. Check both and try again." : msg(e);
        } finally {
            staffBusy = false;
        }
    }

    async function claimAccess(event: SubmitEvent): Promise<void> {
        event.preventDefault();
        const code = claimCode.trim().toLowerCase();
        if (!code) {
            claimError = "Enter the desk code from the venue.";
            return;
        }
        claimBusy = true;
        claimError = "";
        try {
            await api(`/api/events/${code}`);
            navigate(eventPublicPath(code));
        } catch (e) {
            claimError = e instanceof ApiError && e.status === 404 ? "We couldn't find a desk with that code. Double-check it with the organizers." : msg(e);
        } finally {
            claimBusy = false;
        }
    }
</script>

<div class="home">
    <header class="page-bar">
        <span class="row brand-row">
            <Logo />
            <span class="brand-name">{config.app_name}</span>
        </span>
        <ThemeToggle />
    </header>

    <main tabindex="-1">
        <section class="hero">
            <h1>The calm way to reunite people with their things</h1>
            <p>
                Run a private lost-and-found desk for your event. Staff photograph found items, owners describe what they lost, and AI quietly suggests matches
                — people make every decision.
            </p>
        </section>

        <ol class="steps" aria-label="How it works">
            <li>
                <span class="step-icon"><Icon name="camera" size={18} /></span>
                <strong>Staff log found items</strong>
                <span>One photo per item — a searchable description is written automatically.</span>
            </li>
            <li>
                <span class="step-icon"><Icon name="message" size={18} /></span>
                <strong>Owners describe what they lost</strong>
                <span>A short chat collects the details that matter, in the owner's own words.</span>
            </li>
            <li>
                <span class="step-icon"><Icon name="shield" size={18} /></span>
                <strong>Staff confirm in person</strong>
                <span>Matches are reviewed privately and every handoff happens face to face.</span>
            </li>
        </ol>

        <div class="home-grid">
            <!-- Create a new event -->
            <section class="card create-card">
                {#if !created}
                    <h2>Set up a desk</h2>
                    <p class="muted">Name your event and you're live — we'll generate a desk code to share and a staff password.</p>
                    <form on:submit={createEvent} novalidate>
                        <label for="ev-name">Event name<span class="req" aria-hidden="true">*</span></label>
                        <input
                            id="ev-name"
                            bind:value={name}
                            placeholder="e.g. Build Small Hackathon"
                            required
                            aria-invalid={nameError ? "true" : undefined}
                            aria-describedby={nameError ? "ev-name-error" : undefined}
                            on:input={() => (nameError = "")}
                        />
                        {#if nameError}
                            <p class="field-error" id="ev-name-error"><Icon name="error" size={13} />{nameError}</p>
                        {/if}

                        <label for="ev-id">Custom desk code <span class="optional">(optional)</span></label>
                        <input id="ev-id" bind:value={customId} placeholder="Leave blank for a random code" />
                        <p class="hint">
                            Lowercase letters, numbers, and hyphens — anything else converts automatically. It appears in the link you share, like <code
                                >/e/build-small</code
                            >.
                        </p>

                        {#if createError}
                            <div class="note note-danger" role="alert"><Icon name="error" size={16} />{createError}</div>
                        {/if}

                        <button type="submit" class="btn btn-primary btn-block" disabled={creating}>
                            {#if creating}<Spinner size={15} />Setting up your desk…{:else}Create the desk<Icon name="arrow-right" size={15} />{/if}
                        </button>
                    </form>
                {:else}
                    {@const ev = created}
                    <div class="created" role="status">
                        <div class="note note-ok">
                            <Icon name="check" size={16} />
                            <span><strong>{ev.name}</strong> is live. Save these details before you move on.</span>
                        </div>

                        <div class="cred">
                            <span class="cred-label">Desk code</span>
                            <span class="row">
                                <code class="cred-value">{ev.event_id}</code>
                                <CopyButton text={ev.event_id} />
                            </span>
                        </div>

                        <div class="pw-panel">
                            <p class="pw-warn">
                                <Icon name="alert" size={15} />
                                <span>This staff password is shown <strong>only once</strong> and can't be recovered — copy it somewhere safe now.</span>
                            </p>
                            <span class="row">
                                <code class="cred-value pw">{ev.staff_password}</code>
                                <CopyButton text={ev.staff_password} label="Copy password" />
                            </span>
                        </div>

                        <div class="cred">
                            <span class="cred-label">Public link for owners — share it or print it as a QR code</span>
                            <span class="row">
                                <code class="cred-value trunc">{absoluteUrl(ev.claim_url)}</code>
                                <CopyButton text={absoluteUrl(ev.claim_url)} />
                            </span>
                        </div>

                        <div class="stack">
                            <button class="btn btn-primary" on:click={() => navigate(staffPath(ev.event_id))}>
                                Open the staff console<Icon name="arrow-right" size={15} />
                            </button>
                            <button class="btn btn-secondary" on:click={() => navigate(eventPublicPath(ev.event_id))}> Preview the public page </button>
                        </div>
                    </div>
                {/if}
            </section>

            <div class="home-side">
                <!-- Claimant access -->
                <section class="card">
                    <h2><Icon name="search" size={18} />Lost something?</h2>
                    <p class="muted">Enter the desk code from the venue to report your item or check for replies.</p>
                    <form on:submit={claimAccess} novalidate>
                        <label for="cl-code">Desk code</label>
                        <input
                            id="cl-code"
                            bind:value={claimCode}
                            placeholder="e.g. a99vc8"
                            autocapitalize="none"
                            autocorrect="off"
                            aria-invalid={claimError ? "true" : undefined}
                            aria-describedby={claimError ? "cl-code-error" : undefined}
                            on:input={() => (claimError = "")}
                        />
                        {#if claimError}
                            <p class="field-error" id="cl-code-error"><Icon name="error" size={13} />{claimError}</p>
                        {/if}
                        <button type="submit" class="btn btn-primary btn-block" disabled={claimBusy}>
                            {#if claimBusy}<Spinner size={15} />Finding the desk…{:else}Report a lost item{/if}
                        </button>
                    </form>
                </section>

                <!-- Staff access -->
                <section class="card">
                    <h2><Icon name="key" size={18} />Staff sign in</h2>
                    <p class="muted">Use the desk code and the staff password from setup.</p>
                    {#if myEvents.length}
                        <div class="my-events">
                            <span class="hint">Desks you've managed on this device</span>
                            {#each myEvents as ev}
                                <button class="list-card my-event" on:click={() => navigate(staffPath(ev.event_id))}>
                                    <span class="row spread">
                                        <span class="trunc">{ev.name}</span>
                                        <Icon name="arrow-right" size={14} />
                                    </span>
                                </button>
                            {/each}
                        </div>
                    {/if}
                    <form on:submit={staffAccess} novalidate>
                        <label for="st-code">Desk code</label>
                        <input
                            id="st-code"
                            bind:value={staffCode}
                            placeholder="e.g. a99vc8"
                            autocapitalize="none"
                            autocorrect="off"
                            on:input={() => (staffError = "")}
                        />
                        <label for="st-pw">Staff password</label>
                        <input
                            id="st-pw"
                            type="password"
                            bind:value={staffPw}
                            placeholder="From when the desk was created"
                            aria-invalid={staffError ? "true" : undefined}
                            aria-describedby={staffError ? "st-error" : undefined}
                            on:input={() => (staffError = "")}
                        />
                        {#if staffError}
                            <p class="field-error" id="st-error"><Icon name="error" size={13} />{staffError}</p>
                        {/if}
                        <button type="submit" class="btn btn-secondary btn-block" disabled={staffBusy}>
                            {#if staffBusy}<Spinner size={15} />Checking…{:else}Open the console{/if}
                        </button>
                    </form>
                </section>
            </div>
        </div>
    </main>

    <footer class="home-foot">
        {#if config.model_mode === "mock"}
            <Icon name="shield" size={14} />
            <span> Running in demo (mock) mode. </span>
        {/if}
    </footer>
</div>

<style>
    .home {
        max-width: 1080px;
        margin: 0 auto;
        padding: var(--s-4) var(--s-4) var(--s-7);
    }

    .brand-row {
        gap: var(--s-3);
    }

    .hero {
        text-align: center;
        margin: var(--s-5) auto var(--s-6);
        max-width: 44rem;
        animation: fade-up var(--dur-3) var(--ease-out);
    }

    .hero h1 {
        font-size: var(--text-display);
        letter-spacing: -0.03em;
    }

    .hero p {
        margin: var(--s-4) auto 0;
        max-width: 38rem;
        color: var(--ink-2);
        line-height: 1.65;
    }

    .steps {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: var(--s-4);
        list-style: none;
        margin: 0 0 var(--s-6);
        padding: 0;
        counter-reset: step;
    }

    .steps li {
        display: grid;
        gap: 0.4rem;
        justify-items: start;
        padding: var(--s-4) var(--s-5);
        border: 1px solid var(--line);
        border-radius: var(--r-lg);
        background: var(--surface);
    }

    .step-icon {
        display: grid;
        place-items: center;
        width: 2.2rem;
        height: 2.2rem;
        border-radius: var(--r-md);
        background: var(--surface-2);
        color: var(--ink-2);
        margin-bottom: var(--s-1);
    }

    .steps strong {
        font-size: var(--text-base);
        letter-spacing: -0.01em;
    }

    .steps span:not(.step-icon) {
        color: var(--ink-3);
        font-size: var(--text-sm);
        line-height: 1.5;
    }

    .home-grid {
        display: grid;
        /* minmax(0, …): long links/codes in the created-desk card must truncate,
       never widen the page */
        grid-template-columns: minmax(0, 1.25fr) minmax(0, 1fr);
        gap: var(--s-4);
        align-items: start;
    }

    .home-side {
        display: grid;
        grid-template-columns: minmax(0, 1fr);
        gap: var(--s-4);
    }

    .card h2 {
        display: flex;
        align-items: center;
        gap: var(--s-2);
        font-size: var(--text-lg);
        margin-bottom: var(--s-1);
    }

    .card h2 :global(svg) {
        color: var(--ink-3);
    }

    .card > .muted {
        font-size: var(--text-sm);
        line-height: 1.55;
    }

    .card form .btn {
        margin-top: var(--s-4);
    }

    .card form .note {
        margin-top: var(--s-4);
    }

    /* Created-event credentials */
    .created {
        display: grid;
        gap: var(--s-4);
        animation: fade-up var(--dur-3) var(--ease-out);
    }

    .cred {
        display: grid;
        gap: 0.35rem;
    }

    .cred-label {
        color: var(--ink-3);
        font-size: var(--text-sm);
        font-weight: 550;
    }

    .cred-value {
        font-size: var(--text-md);
        padding: 0.3rem 0.6rem;
    }

    .pw-panel {
        display: grid;
        gap: var(--s-2);
        padding: var(--s-4);
        border: 1px solid color-mix(in srgb, var(--warn) 32%, transparent);
        border-radius: var(--r-md);
        background: var(--warn-soft);
    }

    .pw-warn {
        display: flex;
        gap: var(--s-2);
        margin: 0;
        color: var(--warn-on-soft);
        font-size: var(--text-sm);
        line-height: 1.5;
    }

    .pw-warn :global(svg) {
        flex: none;
        margin-top: 0.15rem;
    }

    .cred-value.pw {
        font-size: var(--text-md);
        letter-spacing: 0.04em;
    }

    .created .stack {
        margin-top: var(--s-2);
    }

    /* Staff: previously-managed desks */
    .my-events {
        display: grid;
        gap: var(--s-2);
        margin: var(--s-3) 0 var(--s-2);
    }

    .my-event {
        padding: var(--s-2) var(--s-3);
        font-weight: 600;
    }

    .spread {
        justify-content: space-between;
        width: 100%;
    }

    .home-foot {
        display: flex;
        justify-content: center;
        align-items: flex-start;
        gap: var(--s-2);
        text-align: center;
        color: var(--ink-3);
        font-size: var(--text-sm);
        margin-top: var(--s-6);
        line-height: 1.5;
    }

    .home-foot :global(svg) {
        flex: none;
        margin-top: 0.16rem;
    }

    @media (max-width: 880px) {
        .steps {
            grid-template-columns: 1fr;
        }

        .home-grid {
            grid-template-columns: minmax(0, 1fr);
        }

        .hero {
            margin-top: var(--s-2);
        }
    }
</style>
