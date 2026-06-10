// Shared domain types mirroring the FastAPI backend schemas
// (src/lost_found_desk/schemas.py). Kept intentionally close to the JSON the
// REST endpoints return.

export type ItemStatus = 'unclaimed' | 'candidate' | 'returned' | 'archived';
export type ClaimStatus =
  | 'draft'
  | 'ready_for_staff_review'
  | 'matched'
  | 'needs_more_info'
  | 'closed';
export type CandidateState =
  | 'strong_candidate'
  | 'weak_candidate'
  | 'needs_more_info'
  | 'no_match';
export type ChatRole = 'assistant' | 'user' | 'system' | 'staff';

export interface ChatMessage {
  role: ChatRole;
  content: string;
  created_at?: string;
}

export interface Item {
  item_id: string;
  event_id: string;
  caption: string;
  photo_url: string;
  photo_path?: string;
  found_location: string;
  staff_note?: string;
  privacy_note: string;
  status: ItemStatus;
  created_at: string;
  updated_at: string;
}

/** An item enriched client-side with an object-URL for its authenticated photo. */
export interface ItemWithPhoto extends Item {
  _photo_src?: string;
}

export interface ClaimantPhoto {
  photo_id: string;
  photo_url: string;
  caption: string;
  privacy_note: string;
  created_at: string;
}

export interface Claim {
  claim_id: string;
  event_id: string;
  conversation: ChatMessage[];
  summary: string;
  missing_info: string[];
  readiness_state: string;
  contact_name: string;
  contact_info: string;
  claimant_photos: ClaimantPhoto[];
  // Staff-only live match (stripped from the claimant-facing payload).
  candidates?: Candidate[];
  match_state?: string;
  status: ClaimStatus;
  has_unread_staff_message?: boolean;
  created_at: string;
  updated_at: string;
}

export interface Candidate {
  item_id: string;
  state: CandidateState;
  reason: string;
  staff_next_step: string;
  safe_claimant_message: string;
  score: number;
  item?: ItemWithPhoto | null;
}

export interface MatchResult {
  state: CandidateState;
  candidates: Candidate[];
}

/** A match result bound to the claim it was computed for (client-side view state). */
export interface MatchView extends MatchResult {
  claim_id: string;
}

export interface ReturnLog {
  log_id: string;
  event_id: string;
  item_id: string;
  claim_id: string;
  staff_note?: string;
  handoff_method?: string;
  created_at: string;
}

export interface Report {
  event_id: string;
  event_name: string;
  items_catalogued: number;
  unclaimed_items: number;
  returned_items: number;
  claims_received: number;
  claims_ready_for_review: number;
  claims_need_more_info: number;
  handoff_logs: number;
  auto_ownership_decisions: number;
  public_photo_exposures: number;
  claimant_visible_ranked_candidates: number;
  returns: ReturnLog[];
}

export interface PublicConfig {
  app_name: string;
  model_mode?: string;
  device?: string;
  zerogpu?: boolean;
  prefer_gradio_client_for_models: boolean;
}

export interface EventPublic {
  event_id: string;
  name: string;
  exists: boolean;
}

export interface CreatedEvent {
  event_id: string;
  name: string;
  staff_password: string;
  staff_url: string;
  claim_url: string;
  created_at: string;
}

export interface ItemsResponse {
  items: Item[];
}
export interface ClaimsResponse {
  claims: Claim[];
}
export interface ClaimResponse {
  claim: Claim;
}
export interface ClaimChatResponse {
  claim: Claim;
  assistant?: unknown;
}
export interface ClaimPhotoResponse {
  claim: Claim;
  photo: ClaimantPhoto;
}
export interface ItemResponse {
  item: Item;
}
export interface MessageResponse {
  message: string;
}
export interface SubmitResponse {
  claim: Claim;
  message: string;
}
export interface VerifyResponse {
  ok: boolean;
  event_id: string;
  name: string;
}
