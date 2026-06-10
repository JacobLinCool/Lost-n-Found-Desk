// Single source of truth for status -> human label + tone, so the claimant
// and staff surfaces never drift or leak a raw enum to a user.

const CLAIMANT: Record<string, string> = {
  draft: 'Gathering details',
  needs_more_info: 'Submitted — more detail will help',
  ready_for_staff_review: 'Submitted — awaiting desk team review',
  matched: 'Under desk team review',
  closed: 'Closed — pickup arranged',
};

const STAFF: Record<string, string> = {
  draft: 'Gathering details',
  needs_more_info: 'Needs more info',
  ready_for_staff_review: 'Ready for review',
  matched: 'Matched',
  closed: 'Closed',
  unclaimed: 'Unclaimed',
  returned: 'Returned',
  candidate: 'Candidate',
  archived: 'Archived',
  strong_candidate: 'Strong match',
  weak_candidate: 'Possible match',
  no_match: 'No match',
};

const HANDOFF: Record<string, string> = {
  offline_staff_confirmation: 'Confirmed in person',
};

/** Claimant-facing label. Never leaks a raw enum: unknown -> neutral 'In progress'. */
export function claimantStatus(status: string): string {
  return CLAIMANT[status] || 'In progress';
}

/** Staff-facing label for any status/state/handoff enum. */
export function staffLabel(value: string): string {
  return STAFF[value] || HANDOFF[value] || 'In progress';
}

export type StatusTone = 'neutral' | 'ok' | 'warn' | 'danger' | 'info';

/** Visual tone for a status badge. Badges always pair tone with a label and
 * dot, so color is never the only signal. */
export function statusTone(status: string): StatusTone {
  switch (status) {
    case 'returned':
    case 'closed':
    case 'strong_candidate':
      return 'ok';
    case 'ready_for_staff_review':
    case 'matched':
      return 'info';
    case 'needs_more_info':
    case 'weak_candidate':
      return 'warn';
    case 'no_match':
      return 'danger';
    default:
      return 'neutral';
  }
}
