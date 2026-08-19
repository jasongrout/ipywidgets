var path = require('path');

module.exports = {
  mode: 'development',
  entry: './test/index.js',
  output: {
    filename: 'bundle.js',
    path: path.resolve(__dirname, 'build'),
  },
  bail: true,
};
