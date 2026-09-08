create extension if not exists pgcrypto;

create table if not exists public.glove_samples (
  id uuid primary key default gen_random_uuid(),
  participant_id text not null check (participant_id ~ '^[a-zA-Z0-9_-]{2,40}$'),
  session_id text not null,
  label text not null,
  sample_rate_hz integer not null default 20,
  sequence_length integer not null default 40,
  feature_names jsonb not null,
  sequence jsonb not null,
  firmware_version text not null default 'unknown',
  status text not null default 'pending' check (status in ('pending', 'approved', 'rejected')),
  created_at timestamptz not null default now()
);

create index if not exists glove_samples_training_idx
  on public.glove_samples (status, label, created_at);

alter table public.glove_samples enable row level security;

grant usage on schema public to service_role;
grant select, insert, update on table public.glove_samples to service_role;

-- 브라우저에서는 DB에 직접 접근하지 않습니다. Render 서버의 service role만 접근합니다.
