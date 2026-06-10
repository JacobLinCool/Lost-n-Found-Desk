import { Client, handle_file } from '@gradio/client';
import type { Claim, ClaimantPhoto, Item } from './types';

let clientPromise: Promise<Client> | undefined;

function source(): string {
  return window.location.origin;
}

async function client(): Promise<Client> {
  if (!clientPromise) clientPromise = Client.connect(source());
  return clientPromise;
}

function unwrap<T>(result: unknown): T {
  if (result && Array.isArray((result as { data?: unknown[] }).data)) {
    return (result as { data: unknown[] }).data[0] as T;
  }
  return result as T;
}

export async function gradioCreateItem(
  event_id: string,
  file: File | Blob,
  found_location: string,
  staff_note: string,
  staff_password: string,
): Promise<{ item: Item }> {
  const app = await client();
  const result = await app.predict('/create_item', {
    event_id,
    image: handle_file(file),
    found_location,
    staff_note,
    staff_password,
  });
  return unwrap(result);
}

export async function gradioClaimChat(
  event_id: string,
  claim_id: string,
  user_message: string,
): Promise<{ claim: Claim; assistant?: unknown }> {
  const app = await client();
  const result = await app.predict('/claim_chat', { event_id, claim_id, user_message });
  return unwrap(result);
}

export async function gradioClaimAddPhoto(
  event_id: string,
  claim_id: string,
  file: File | Blob,
): Promise<{ claim: Claim; photo: ClaimantPhoto }> {
  const app = await client();
  const result = await app.predict('/claim_add_photo', {
    event_id,
    claim_id,
    image: handle_file(file),
  });
  return unwrap(result);
}

export async function gradioMatchClaim(
  event_id: string,
  claim_id: string,
  staff_password: string,
): Promise<{ state: string; candidates: unknown[] }> {
  const app = await client();
  const result = await app.predict('/match_claim', { event_id, claim_id, staff_password });
  return unwrap(result);
}

export async function gradioDraftMessage(
  event_id: string,
  claim_id: string,
  item_id: string,
  staff_password: string,
): Promise<{ message: string }> {
  const app = await client();
  const result = await app.predict('/draft_message', { event_id, claim_id, item_id, staff_password });
  return unwrap(result);
}
