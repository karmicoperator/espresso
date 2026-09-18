# Paper in Five, browser extension

One click on a paper's page builds its explainer in the Paper in Five app running on your
machine, and hands the app the PDF your browser can see. Publishers block programs, not
people: a PDF fetched from the page you are looking at carries your own access, so it
attaches even where the app's own fetch is refused.

Talks only to `localhost`. Nothing leaves the machine except what the page itself loads.

## Chrome, Edge, Brave
1. `chrome://extensions`, turn on Developer mode.
2. Load unpacked, choose this `extension` folder.
3. Open a PubMed, PMC or DOI page (or a PDF) and click the icon.

## Firefox
Firefox reads `manifest.firefox.json`: copy it over `manifest.json` in a copy of this
folder, then `about:debugging`, This Firefox, Load Temporary Add-on, pick `manifest.json`.
A temporary add-on lasts until Firefox restarts; a signed build needs an add-ons account.

## Safari
Safari runs the same WebExtension inside an app wrapper that Xcode builds:
`xcrun safari-web-extension-converter extension/`, then run the generated project once
and enable the extension in Safari, Settings, Extensions. Needs Xcode.

The popup's "Where the app runs" fields point at another port if the app chose one.
