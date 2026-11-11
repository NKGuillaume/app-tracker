-- Interview details + cached AI prep tips. Safe to run more than once.
-- Run in the Supabase SQL editor (the backend's client can't run DDL).

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
