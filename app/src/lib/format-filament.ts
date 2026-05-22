/**
 * Format total filament from API (kilograms).
 */
export function formatFilamentKg(kg: number): string {
  if (!kg || kg <= 0) {
    return '0 g'
  }
  if (kg < 1) {
    const grams = kg * 1000
    if (grams >= 100) {
      return `${Math.round(grams)} g`
    }
    return `${grams.toFixed(1)} g`
  }
  return `${kg.toFixed(2)} kg`
}
