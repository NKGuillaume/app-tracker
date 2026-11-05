/* Date-only strings ("2026-08-01") are parsed as local dates on purpose:
   new Date("2026-08-01") reads as UTC midnight and can land on the previous
   day in western timezones. */
export function parseDate(value: string): Date {
  const dateOnly = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return dateOnly
    ? new Date(Number(dateOnly[1]), Number(dateOnly[2]) - 1, Number(dateOnly[3]))
    : new Date(value);
}

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});

export function formatDate(value: string): string {
  return dateFormatter.format(parseDate(value));
}

export function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}
