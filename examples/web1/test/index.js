import { expect } from 'chai';

const widgetsRendered = new Promise((resolve, reject) => {
  setTimeout(
    () => reject(Error('timeout waiting for widgets to render')),
    5000
  ); // 5s timeout

  // The widgets may already have rendered by the time this test bundle is
  // loaded, so check the flag set by the page before waiting for its event.
  if (window.widgetsRendered) {
    resolve();
  } else {
    document.addEventListener('widgetsRendered', () => resolve(), {
      once: true,
    });
  }
});

describe('index.html', function () {
  this.timeout(10000);

  beforeEach(() => {
    return widgetsRendered;
  });

  describe('textArea', () => {
    it('exists', () => {
      expect(document.querySelector('textarea')).to.be.ok;
    });
    it('correct value', () => {
      expect(document.querySelector('textarea').value).to.equal(
        'test <b>text</b>'
      );
    });
  });
  describe('html', () => {
    it('exists', () => {
      expect(document.querySelector('div.widget-html')).to.be.ok;
    });
    it('correct value', () => {
      expect(
        document.querySelector('div.widget-html-content').innerHTML
      ).to.equal('test <b>text</b>');
    });
  });
});
