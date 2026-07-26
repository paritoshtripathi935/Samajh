/**
 * Supabase clients, typed to the generated schema (lib/database.types.ts).
 *
 * - `supabaseBrowser()` — anon key, safe in client components (RLS applies).
 * - `supabaseAdmin()` — SERVER-ONLY. Uses the service-role key; bypasses RLS.
 *   Import only from route handlers / server actions.
 *
 * Pipeline tables (this team): documents · digitizations · extractions ·
 * translations. Most writes go through the Python backend (lib/api.ts); read
 * directly here when convenient.
 */
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import type { Database } from '@/lib/database.types';

export type TypedClient = SupabaseClient<Database>;

let _browser: TypedClient | null = null;

/** Browser/client-safe singleton (anon key). */
export function supabaseBrowser(): TypedClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anon = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !anon) {
    throw new Error('Missing NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_ANON_KEY');
  }
  if (!_browser) {
    _browser = createClient<Database>(url, anon);
  }
  return _browser;
}

/** SERVER-ONLY: full-access client (service role). Never import client-side. */
export function supabaseAdmin(): TypedClient {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const service = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !service) {
    throw new Error('Missing NEXT_PUBLIC_SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY');
  }
  return createClient<Database>(url, service, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
}
