import type { InterviewType } from "./api/client";

export const INTERVIEW_TYPE_LABELS: Record<InterviewType, string> = {
  online_assessment: "Online assessment",
  video_interview: "Recorded video interview",
  phone_screen: "Phone screen",
  technical_interview: "Technical interview",
  behavioral_interview: "Behavioral interview",
  final_round: "Final round",
  other: "Other",
};

export const INTERVIEW_TYPES = Object.keys(INTERVIEW_TYPE_LABELS) as InterviewType[];
