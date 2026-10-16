// Job profile as the API returns it -> form values (inputs need strings, not null).
export const profileToForm = (profile) => ({
  department: profile?.department ?? "",
  location: profile?.location ?? "",
  employment_type: profile?.employment_type ?? "full_time",
  min_experience_years: profile?.min_experience_years ?? "",
  application_deadline: profile?.application_deadline ?? "",
});

export const formToProfile = (form) => ({
  department: form.department.trim() || null,
  location: form.location.trim() || null,
  employment_type: form.employment_type,
  min_experience_years: form.min_experience_years === "" ? null : Number(form.min_experience_years),
  application_deadline: form.application_deadline || null,
});
