/** Navigation intent and React.lazy use the same import functions. */
export const routeLoaders = {
  catalog: () => import('./catalog'),
  rankings: () => import('./rankings'),
  library: () => import('./library'),
  classicalEducation: () => import('./classicalEducation'),
  discovery: () => import('./discovery'),
  readingTrails: () => import('./readingTrails'),
  catalogAtlas: () => import('./catalogAtlas'),
  publishedComparison: () => import('./publishedComparison'),
  today: () => import('./today'),
  profile: () => import('./profile'),
  catalogReview: () => import('./catalogReview'),
  operations: () => import('./operations'),
}
