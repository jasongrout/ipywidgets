var path = require('path');
var rspack = require('@rspack/core');
module.exports = {
  entry: ['./amd-public-path.js', './src/extension.js'],
  optimization: {
    minimizer: [
      // Extract license banner comments to a *.LICENSE.txt file, like
      // webpack's default terser configuration did
      new rspack.SwcJsMinimizerRspackPlugin({ extractComments: true }),
      new rspack.LightningCssMinimizerRspackPlugin(),
    ],
  },
  output: {
    filename: 'extension.js',
    path: path.resolve(__dirname, 'widgetsnbextension', 'static'),
    library: { type: 'amd' },
    publicPath: '', // Set in amd-public-path.js
  },
  devtool: 'source-map',
  // Process AMD define() calls in bundled modules (like webpack does by
  // default) so UMD wrappers such as jQuery's do not register stray AMD
  // modules at runtime when this bundle is loaded by requirejs.
  amd: {},
  module: {
    rules: [
      { test: /\.css$/, use: ['style-loader', 'css-loader'] },
      // required to load font-awesome
      { test: /\.(woff|woff2|eot|ttf|otf)$/i, type: 'asset/resource' },
      { test: /\.svg$/i, type: 'asset' },
    ],
  },
  // 'module' is the magic requirejs dependency used to set the publicPath
  externals: ['module'],
};
