create table responses (
  email text primary key,
  name text,
  data jsonb not null,
  created_at timestamptz default now()
);
alter table responses enable row level security;
-- Only a user who has verified the OTP for this email can insert a row for it.
create policy "insert own verified response" on responses
  for insert to authenticated
  with check (lower(auth.jwt() ->> 'email') = email);
