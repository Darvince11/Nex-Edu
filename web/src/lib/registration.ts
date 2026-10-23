/** Choices for a school registration. Values match the API (control_plane.models). */

export const SCHOOL_TYPES = [
  { value: "basic", label: "KG, primary and JHS" },
  { value: "primary", label: "KG and primary (Basic 1-6)" },
  { value: "kg", label: "Kindergarten only" },
  { value: "jhs", label: "Junior High only" },
];

export const REGIONS = [
  ["ahafo", "Ahafo"],
  ["ashanti", "Ashanti"],
  ["bono", "Bono"],
  ["bono_east", "Bono East"],
  ["central", "Central"],
  ["eastern", "Eastern"],
  ["greater_accra", "Greater Accra"],
  ["north_east", "North East"],
  ["northern", "Northern"],
  ["oti", "Oti"],
  ["savannah", "Savannah"],
  ["upper_east", "Upper East"],
  ["upper_west", "Upper West"],
  ["volta", "Volta"],
  ["western", "Western"],
  ["western_north", "Western North"],
] as const;

/** "St. Mary's Basic School" → "st-marys-basic" */
export function suggestSlug(name: string): string {
  return name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/['’]/g, "")
    .replace(/\b(school|the|of|and|complex|ltd)\b/g, " ")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .replace(/^[^a-z]+/, "")
    .slice(0, 40)
    .replace(/-+$/, "");
}
