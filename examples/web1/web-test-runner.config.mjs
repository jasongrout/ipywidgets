export default {
  files: ['test/build/bundle.js'],
  // Load the example page's bundle with a classic script tag, like
  // index.html does, so that it runs before DOMContentLoaded fires.
  testRunnerHtml: (testFramework) => `<!DOCTYPE html>
<html>
  <body>
    <script src="/built/index.built.js"></script>
    <script type="module" src="${testFramework}"></script>
  </body>
</html>`,
};
