-- Application Tracker schema.
-- Run once against your Supabase project (SQL editor or `supabase db push`).
--
-- Access model: the FastAPI backend connects with the Supabase service-role
-- key, which bypasses RLS entirely. RLS below is defense-in-depth (in case
-- keys are ever exposed to a client) — no policies are granted to the
-- anon/authenticated roles, so those roles have zero access by default.
-- The actual per-user access control happens in the backend, which scopes
-- every query by the user_id derived from our own verified session.

create extension if not exists pgcrypto;

-- users: our own identity table, keyed by Google's stable subject id.
create table if not exists users (
  id uuid primary key default gen_random_uuid(),
  google_sub text unique not null,
  email text unique not null,
  name text,
  avatar_url text,
  google_refresh_token_encrypted text,   -- Fernet-encrypted; key lives in backend env only
  google_token_scope text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- applications: one row per job application per user.
create table if not exists applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  company text not null,
  job_title text,
  application_date date,
  status text not null default 'applied'
    check (status in ('applied', 'interview', 'offer', 'rejected', 'withdrawn', 'unknown')),
  source_email_id text not null,
  gmail_thread_id text not null,
  raw_snippet text,
  confidence numeric,
  manually_edited boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, gmail_thread_id)
);

create index if not exists idx_applications_user_id on applications(user_id);
create index if not exists idx_applications_status on applications(user_id, status);

-- sync_state: per-user Gmail sync bookkeeping (one row per user).
create table if not exists sync_state (
  user_id uuid primary key references users(id) on delete cascade,
  last_history_id text,
  watch_expiration timestamptz,
  watch_channel_id text,
  last_manual_sync_at timestamptz,
  updated_at timestamptz not null default now()
);

-- processed_emails: idempotency guard so the same Gmail message is never
-- re-processed (and never re-billed to Claude) twice.
create table if not exists processed_emails (
  user_id uuid not null references users(id) on delete cascade,
  gmail_message_id text not null,
  processed_at timestamptz not null default now(),
  classification text not null
    check (classification in ('job_application', 'not_job_application')),
  application_id uuid references applications(id),
  primary key (user_id, gmail_message_id)
);

alter table users enable row level security;
alter table applications enable row level security;
alter table sync_state enable row level security;
alter table processed_emails enable row level security;
-- Deny-by-default: intentionally no policies are created for anon/authenticated
-- roles. Only the service-role key (used exclusively by the backend) can read
-- or write these tables.

-- Interview details (also in migrations/002_interviews.sql for existing projects).
alter table applications add column if not exists interview_type text;
alter table applications add column if not exists assessment_platform text;
alter table applications add column if not exists interview_deadline date;
alter table applications add column if not exists team text;
alter table applications add column if not exists interview_prep jsonb;
alter table applications add column if not exists interview_prep_generated_at timestamptz;

alter table applications drop constraint if exists applications_interview_type_check;
alter table applications add constraint applications_interview_type_check
  check (interview_type is null or interview_type in (
    'online_assessment', 'video_interview', 'phone_screen',
    'technical_interview', 'behavioral_interview', 'final_round', 'other'
  ));
