// Canonical name key for cross-source comparison. The Yahoo DOM poller and the
// draftboard disagree on punctuation and casing ("Amon-Ra St. Brown" vs
// "Amon Ra St. Brown"), so:
//   - hyphens become a SPACE, not deleted — otherwise "Amon-Ra" -> "amonra"
//     would NOT match "Amon Ra" -> "amon ra" (the hyphen joins two tokens the
//     space keeps separate). Mapping "-" to " " makes both "amon ra".
//   - periods/apostrophes are dropped ("St." == "St", "Ja'Marr" == "JaMarr")
//   - runs of whitespace collapse to one, then trim.
export function normalizeName(name) {
  return (name || '')
    .toLowerCase()
    // Strip a trailing generational suffix ("James Cook III", "Etienne Jr.")
    // BEFORE punctuation removal, so "jr." is still recognizable. Run first.
    .replace(/\s+(jr\.?|sr\.?|ii|iii|iv|v)$/, '')
    // Hyphen -> SPACE (not deleted): "Amon-Ra" must equal the DOM's "Amon Ra".
    // Deleting it would give "amonra" != "amon ra" and re-break the filter.
    .replace(/-/g, ' ')
    // Drop periods/apostrophes ("St." == "St", "Le'Veon" == "LeVeon").
    .replace(/[.']/g, '')
    .replace(/\s+/g, ' ')
    .trim()
}
