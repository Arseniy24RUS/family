/** Load only the selected study. Shared modules remain native ES modules. */
export const projectRuntimes = Object.freeze(Object.fromEntries([
  ['youth_children', 'youth', 'youthPage'],
  ['personnel', 'personnel', 'personnelPage'],
  ['long_active_life', 'longlife', 'longlifePage'],
  ['health_technologies', 'healthtech', 'healthtechPage'],
  ['life_infrastructure', 'infrastructure', 'infrastructurePage'],
  ['environment', 'environment', 'environmentPage'],
  ['competitive_economy', 'competitive', 'renderCompetitive'],
  ['data_economy', 'dataeconomy', 'renderDataeconomy'],
  ['tourism', 'tourism', 'renderTourism'],
  ['efficient_transport', 'efficient_transport', 'renderEfficientTransport'],
  ['international_export', 'international_export', 'renderInternationalExport']
].map(([id, key, renderer]) => [id, Object.freeze({
  key, renderer, module: `../pages/${key}.js`, stylesheet: `./src/${key}.css`
})])));

const familyRenderers = Object.freeze({
  overview: ['research', 'overview'], framework: ['research', 'framework'],
  logic: ['research', 'logic'], audit: ['research', 'audit'],
  targets: ['research', 'targets'], finance: ['research', 'finance'],
  network: ['research', 'measures'], domains: ['research', 'domainPage'],
  causal: ['research', 'causal'], proposals: ['research', 'proposalPage'],
  map: ['atlas', 'atlas'], regions: ['regions', 'regionsPage'],
  texts: ['texts', 'textsPage'], lab: ['lab', 'lab'],
  explorer: ['tools', 'explorer'], library: ['tools', 'library'],
  updates: ['tools', 'updates'], projections: ['projections', 'indicatorProjections'],
  population: ['population', 'populationProjection'], authors: ['authors', 'authors']
});

/** Deduplicate concurrent CSS requests and discard failed links for retry. */
export function createStylesheetLoader(getDocument = () => globalThis.document) {
  const pending = new Map();
  return function loadStylesheet(href) {
    if (!pending.has(href)) {
      const promise = new Promise((resolve, reject) => {
        const document = getDocument();
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        link.dataset.projectStyle = href;
        link.addEventListener('load', () => resolve(link), {once: true});
        link.addEventListener('error', () => {
          link.remove();
          reject(Error('Не удалось загрузить оформление проекта. Повторите открытие страницы.'));
        }, {once: true});
        document.head.append(link);
      }).catch(error => { pending.delete(href); throw error; });
      pending.set(href, promise);
    }
    return pending.get(href);
  };
}

/** The injectable loaders let tests verify isolation, concurrent reuse and retry. */
export function createRuntimeLoader({
  importer = specifier => import(specifier),
  stylesheet = createStylesheetLoader()
} = {}) {
  const modules = new Map();
  function loadModule(specifier) {
    if (!modules.has(specifier)) modules.set(specifier,
      Promise.resolve().then(() => importer(specifier)).catch(error => {
        modules.delete(specifier); throw error;
      }));
    return modules.get(specifier);
  }
  return {
    async study(id) {
      const descriptor = projectRuntimes[id];
      if (!descriptor) throw Error('Неизвестный исследовательский проект: ' + id);
      const [module] = await Promise.all([
        loadModule(descriptor.module), stylesheet(descriptor.stylesheet)
      ]);
      if (typeof module[descriptor.renderer] !== 'function')
        throw Error('Не найден модуль страницы проекта: ' + id);
      return {key: descriptor.key, render: module[descriptor.renderer]};
    },
    async family(page) {
      const [moduleName, renderer] = familyRenderers[page] || familyRenderers.overview;
      const module = await loadModule(`../pages/${moduleName}.js`);
      return module[renderer];
    },
    async foundation() { return loadModule('../pages/project.js'); }
  };
}

export const runtime = createRuntimeLoader();
