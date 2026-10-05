export type BibliographyFormat = 'plain_text' | 'ris' | 'bibtex'

export const bibliographyFormats: Record<
  BibliographyFormat,
  { label: string; extension: string; mime: string }
> = {
  plain_text: { label: 'Plain references', extension: 'txt', mime: 'text/plain;charset=utf-8' },
  ris: { label: 'RIS', extension: 'ris', mime: 'application/x-research-info-systems;charset=utf-8' },
  bibtex: { label: 'BibTeX', extension: 'bib', mime: 'application/x-bibtex;charset=utf-8' },
}

export function bibliographyFile(result: Record<BibliographyFormat, string>, format: BibliographyFormat) {
  const choice = bibliographyFormats[format]
  return {
    name: `marginalia-bibliography.${choice.extension}`,
    mime: choice.mime,
    text: result[format],
  }
}
