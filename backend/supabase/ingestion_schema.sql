-- Samajh ingestion schema proposal.
-- Apply after enabling pgvector in Supabase if it is not already enabled.

create extension if not exists vector;

alter table public.documents
  add column if not exists vector_ingestion_status text not null default 'not_started'
    check (vector_ingestion_status in ('not_started', 'queued', 'processing', 'ready', 'failed')),
  add column if not exists structured_ingestion_status text not null default 'not_started'
    check (structured_ingestion_status in ('not_started', 'queued', 'processing', 'ready', 'failed')),
  add column if not exists last_ingested_at timestamptz;

create table if not exists public.document_vector_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  chunk_index integer not null,
  page_start integer,
  page_end integer,
  source text not null default 'eng_extraction',
  chunk_text text not null,
  embedding vector(1536),
  embedding_model text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (document_id, source, chunk_index)
);

create index if not exists document_vector_chunks_document_id_idx
  on public.document_vector_chunks(document_id);

create index if not exists document_vector_chunks_embedding_idx
  on public.document_vector_chunks
  using ivfflat (embedding vector_cosine_ops)
  with (lists = 100);

create table if not exists public.chargesheet_structured_extractions (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references public.documents(id) on delete cascade,
  extraction_model text,
  schema_version text not null default 'chargesheet_v1',

  case_title text,
  case_number text,
  fir_number text,
  police_station text,
  district text,
  court_name text,
  filing_date date,
  incident_date date,
  investigating_officer text,

  complainants jsonb not null default '[]'::jsonb,
  accused jsonb not null default '[]'::jsonb,
  victims jsonb not null default '[]'::jsonb,
  witnesses jsonb not null default '[]'::jsonb,

  ipc_sections jsonb not null default '[]'::jsonb,
  other_statutes jsonb not null default '[]'::jsonb,
  allegations jsonb not null default '[]'::jsonb,
  chronology jsonb not null default '[]'::jsonb,
  evidence_items jsonb not null default '[]'::jsonb,
  seized_property jsonb not null default '[]'::jsonb,
  medical_findings jsonb not null default '[]'::jsonb,
  forensic_findings jsonb not null default '[]'::jsonb,
  procedural_steps jsonb not null default '[]'::jsonb,
  contradictions_or_gaps jsonb not null default '[]'::jsonb,
  bail_or_custody_status jsonb not null default '[]'::jsonb,

  short_summary text,
  prosecution_theory text,
  defence_angles jsonb not null default '[]'::jsonb,
  open_questions jsonb not null default '[]'::jsonb,
  confidence jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (document_id, schema_version)
);

create index if not exists chargesheet_structured_extractions_document_id_idx
  on public.chargesheet_structured_extractions(document_id);

comment on table public.document_vector_chunks is
  'Document-level vector chunks for RAG over raw/English legal filing text.';

comment on table public.chargesheet_structured_extractions is
  'Structured chargesheet facts extracted from English translation for future lawyer-agent workflows.';
