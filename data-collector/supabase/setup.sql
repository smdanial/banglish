-- Banglish Voice: one-time Supabase setup.
-- Paste this whole file into Supabase -> SQL Editor -> New query, then press "Run".
-- Safe to run more than once.

-- 1) Metadata table -------------------------------------------------------
create table if not exists public.recordings (
  id              uuid primary key default gen_random_uuid(),
  speaker_id      text not null check (char_length(speaker_id) between 8 and 64),
  prompt_id       text not null check (char_length(prompt_id) between 1 and 32),
  prompt_text     text not null check (char_length(prompt_text) between 1 and 500),
  actual_text     text not null check (char_length(actual_text) between 1 and 1000),
  category        text check (char_length(category) <= 64),
  audio_path      text not null unique check (char_length(audio_path) between 1 and 300),
  duration_sec    real check (duration_sec >= 0 and duration_sec <= 120),
  mime_type       text check (char_length(mime_type) <= 100),
  user_agent      text check (char_length(user_agent) <= 500),
  age_range       text check (char_length(age_range) <= 32),
  region          text check (char_length(region) <= 64),
  phone_model     text check (char_length(phone_model) <= 100),
  consent_version text not null check (char_length(consent_version) between 1 and 32),
  created_at      timestamptz not null default now()
);

create index if not exists recordings_speaker_idx on public.recordings (speaker_id);
create index if not exists recordings_created_idx on public.recordings (created_at);

-- 2) Row-level security: the public (anon) key may INSERT only. -----------
alter table public.recordings enable row level security;

revoke all on public.recordings from anon, authenticated;
grant insert (speaker_id, prompt_id, prompt_text, actual_text, category, audio_path,
              duration_sec, mime_type, user_agent, age_range, region, phone_model,
              consent_version)
  on public.recordings to anon;

drop policy if exists "anon can insert recordings" on public.recordings;
create policy "anon can insert recordings"
  on public.recordings for insert to anon
  with check (audio_path like speaker_id || '/%');
-- No SELECT / UPDATE / DELETE policies => the public key cannot read, change or delete rows.

-- 3) Private storage bucket for audio --------------------------------------
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values ('recordings', 'recordings', false, 10485760,
        array['audio/webm', 'audio/mp4', 'audio/ogg', 'audio/mpeg', 'audio/aac', 'audio/wav'])
on conflict (id) do update
  set public = false,
      file_size_limit = excluded.file_size_limit,
      allowed_mime_types = excluded.allowed_mime_types;

-- Public key may upload new files into the bucket, nothing else (no list/read/overwrite/delete).
drop policy if exists "anon can upload recordings" on storage.objects;
create policy "anon can upload recordings"
  on storage.objects for insert to anon
  with check (bucket_id = 'recordings' and array_length(storage.foldername(name), 1) = 1);
