const postcss = require('postcss');
var path = require('path');
const rspack = require('@rspack/core');

module.exports = {
  mode: 'development',
  amd: {},
  devtool: 'source-map',
  entry: './lib/index.js',
  output: {
    filename: 'index.built.js',
    path: path.resolve(__dirname, 'built'),
  },
  module: {
    rules: [
      { test: /\.css$/i, use: ['style-loader', 'css-loader'] },
      // required to load font-awesome
      { test: /\.(woff|woff2|eot|ttf|otf)$/i, type: 'asset/resource' },
      { test: /\.svg$/i, type: 'asset' },
    ],
  },
  plugins: [
    new rspack.DefinePlugin({
      process: {
        cwd: () => '/',
        env: {},
      },
    }),
  ],
};
