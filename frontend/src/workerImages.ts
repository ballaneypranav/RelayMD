export function displayWorkerImage(
  key: string | undefined,
  displayNames: Record<string, string>,
): string {
  if (!key) {
    return "-";
  }
  return displayNames[key] ?? key;
}
