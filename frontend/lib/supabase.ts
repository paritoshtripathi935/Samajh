/**
 * Supabase clients.
 *
 * - `supabaseBrowser()` — anon key, safe in client components (RLS applies).
 * - `supabaseAdmin()` — SERVER-ONLY. Uses the service-role key; bypasses RLS.
 *   Import only from route handlers / server actions.
 *
 * Schema (per IDEA_SCOPE §3):
 *   cases · documents{case_id,file_ref,digitised_json,pages}
 *   answers{case_id,question,answer,citations[],created_at} · corrections
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js';

let _browser: SupabaseClient | null = null;

/** Browser/client-safe singleton (anon key). */
export function supabaseBrowser(): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anon) {
    throw new Error('Missing NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY');
  }
  if (!_browser) {
    _browser = createClient(url, anon);
  }
  return _browser;
}

/** SERVER-ONLY: full-access client (service role). Never import client-side. */
export function supabaseAdmin(): SupabaseClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const service = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !service) {
    throw new Error('Missing NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY');
  }
  return createClient(url, service, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
